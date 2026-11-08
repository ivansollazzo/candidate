"""Compatibility report: the local model compares the position's skills with the profile and suggests
where to improve; the score is computed here from its judgements."""

from datetime import UTC, datetime

from sqlalchemy import null, update
from sqlmodel import Session

from app.i18n import t
from app.models import Application, Profile, TaskStatus
from app.schemas import Report, ReportExtraction, ReportSkill
from app.services.llm import generate_structured
from app.services.users import find_profile

# Score weight of required skills relative to nice-to-have ones
WEIGHTS = {"required": 2.0, "nice_to_have": 1.0}
CREDIT = {"match": 1.0, "partial": 0.5}

SENIOR_KEYWORDS = ("senior", "lead", "principal", "staff", "expert", "head", "architect")

SYSTEM_PROMPT = """Sei un career coach che valuta quanto un candidato è adatto a una posizione, per qualsiasi
mestiere (dal barista all'ingegnere). Ricevi le competenze richieste dall'annuncio e il profilo del candidato.
Rispondi in {language}.

Per ogni competenza dell'annuncio, nello stesso ordine, compila un elemento di "skills":
- skill: il nome esatto della competenza dell'annuncio.
- kind: "language" per le lingue, "soft" per le soft skill (lavoro di squadra, problem solving, comunicazione...),
  "technical" per tutto il resto (strumenti, tecnologie, mansioni, conoscenze del mestiere).
- reason: una frase breve che spiega il giudizio citando il profilo.
- matched_with: la competenza o la lingua del candidato che la copre, copiata esattamente dal profilo; null se nessuna.
- status:
  - "match" se il candidato la possiede, anche con un altro nome, o possiede una competenza più specifica che la
    include (es. PyTorch o scikit-learn coprono Machine Learning; "preparazione espresso" copre "caffetteria");
  - "partial" se ha una competenza simile o vicina che si può trasferire (es. TensorFlow per PyTorch), o se la
    usa solo nelle esperienze o nei progetti senza averla tra le competenze;
  - "missing" se nel profilo non c'è nulla di collegato.
Valuta con buon senso, senza essere troppo fiscale, ma non inventare competenze che il profilo non mostra.
Le lingue si confrontano solo con le lingue del candidato.

Poi:
- summary: 2-3 frasi sulla compatibilità complessiva.
- strengths: i punti di forza del candidato per questa posizione.
- improvements: per ogni competenza "missing" o "partial" importante, un'azione concreta per migliorare
  (corso, progetto pratico, certificazione, come valorizzare un'esperienza simile nel CV)."""


def build_prompt(app: Application, profile: Profile | None) -> str:
    profile = profile or Profile()

    def items(entries: list[dict], *keys: str) -> str:
        rows = []
        for entry in entries:
            text = " - ".join(str(entry[k]) for k in keys if entry.get(k))
            technologies = ", ".join(entry.get("technologies") or [])
            rows.append(f"  - {text}" + (f" (strumenti: {technologies})" if technologies else ""))
        return "\n".join(rows) or "  nessuna"

    languages = ", ".join(f"{lang.get('language')} ({lang.get('level') or '?'})" for lang in profile.languages)
    skills = "\n".join(
        f"  - {s['name']} ({'preferenziale' if s.get('importance') == 'nice_to_have' else 'richiesta'})"
        for s in app.skills if s.get("name")
    )
    return "\n".join([
        f"Posizione: {app.title or 'n/d'} presso {app.company or 'n/d'}"
        f" (seniority: {app.seniority or 'n/d'}, anni richiesti: {app.experience_years_min or 'n/d'})",
        "Competenze dell'annuncio:", skills,
        "Requisiti: " + ("; ".join(app.requirements or []) or "n/d"),
        "Preferenziali: " + ("; ".join(app.nice_to_have or []) or "n/d"),
        "Lingue richieste: " + (", ".join(app.languages or []) or "n/d"),
        "",
        f"Candidato: {profile.headline or 'n/d'}, {profile.years_of_experience or 'n/d'} anni di esperienza",
        f"Sintesi: {profile.summary or 'n/d'}",
        "Competenze del candidato (livello 1 base - 4 esperto):",
        "\n".join(f"  - {s['name']} (livello {s.get('level') or '?'})" for s in profile.skills if s.get("name"))
        or "  nessuna",
        "Lingue del candidato: " + (languages or "nessuna"),
        "Esperienze:", items(profile.experiences, "role", "company", "description"),
        "Progetti:", items(profile.projects, "name", "description"),
        "Formazione:", items(profile.education, "degree", "field_of_study", "details"),
        "Certificazioni:", items(profile.certifications, "name", "issuer"),
    ])


def _key(name: str | None) -> str:
    return " ".join((name or "").lower().split())


def build_report(app: Application, profile: Profile | None, result: ReportExtraction) -> Report:
    """Tie the model's judgements to the position's skills and compute the score."""
    profile = profile or Profile()
    judged = {_key(item.skill): item for item in result.skills}
    # The model may only cite what the profile really contains
    own_skills = {_key(s["name"]): s for s in profile.skills if s.get("name")}
    own_languages = {_key(lang.get("language")): lang["language"] for lang in profile.languages if lang.get("language")}
    senior = any(k in (app.seniority or "").lower() for k in SENIOR_KEYWORDS)

    skills = []
    for skill in app.skills:
        if not skill.get("name"):
            continue
        item = judged.get(_key(skill["name"]))
        row = ReportSkill(skill=skill["name"], importance=skill.get("importance") or "required",
                          kind=item.kind if item else "technical", status=item.status if item else "missing",
                          reason=item.reason if item else None)
        if item and item.matched_with:
            own = own_skills.get(_key(item.matched_with))
            if own:
                row.matched_with, row.level = own["name"], own.get("level")
            else:
                row.matched_with = own_languages.get(_key(item.matched_with))
        _apply_level(row, senior)
        skills.append(row)

    scored = [s for s in skills if s.kind != "soft"]
    total = sum(WEIGHTS.get(s.importance, 1.0) for s in scored)
    earned = sum(WEIGHTS.get(s.importance, 1.0) * CREDIT.get(s.status, 0.0) for s in scored)
    return Report(
        score=round(100 * earned / total) if total else 0,
        skills=skills,
        summary=result.summary,
        strengths=result.strengths,
        improvements=result.improvements,
        generated_at=datetime.now(UTC),
    )


def _apply_level(item: ReportSkill, senior: bool) -> None:
    """A skill present at too low a level for the position counts as partial."""
    if item.level is None or item.status != "match":
        return
    if item.level == 1 and item.importance == "required":
        item.status = "partial"
        item.note = t("level_basic")
    elif senior and item.level <= 2:
        item.status = "partial"
        item.note = t("level_too_low_senior", level=t(f"level_{item.level}"))


def prepare(session: Session, app: Application) -> tuple[str, str]:
    """System prompt and prompt for the model, built when the job starts."""
    profile = find_profile(session, app.user_id)
    return SYSTEM_PROMPT.format(language=t("report_language")), build_prompt(app, profile)


def ask_model(system: str, prompt: str) -> ReportExtraction:
    return generate_structured(system, prompt, ReportExtraction)


def save_result(session: Session, app: Application, result: ReportExtraction) -> None:
    report = build_report(app, find_profile(session, app.user_id), result)
    app.report, app.report_status, app.report_stale = report.model_dump(mode="json"), TaskStatus.DONE, False
    session.add(app)


def save_error(session: Session, app: Application, error: str) -> None:
    app.report, app.report_status = {"error": error}, TaskStatus.FAILED
    session.add(app)


def restore(app: Application) -> None:
    """A generation that won't finish (cancelled, interrupted): back to the previous report, if any."""
    app.report_status = TaskStatus.DONE if app.report and "score" in app.report else None


def mark_stale(session: Session, user_id: int) -> None:
    """The profile's skills changed: the user's reports should be regenerated."""
    session.exec(update(Application)
                 .where(Application.user_id == user_id, Application.report_status == TaskStatus.DONE)
                 .values(report_stale=True))


def clear_reports(session: Session) -> None:
    """AI turned off: reports are not kept."""
    session.exec(update(Application).values(report=null(), report_status=None, report_stale=False))


def profile_skills(profile: Profile) -> list[tuple[str, int]]:
    """What of the profile a report depends on."""
    return sorted((_key(s.get("name")), s.get("level") or 0) for s in profile.skills)

"""LLM usage: filling fields from job postings and CVs, and generating advice."""

import logging
import re

from sqlmodel import Session

from app.db import engine
from app.i18n import t
from app.models import Application, Profile, TaskStatus
from app.schemas import (
    AdviceExtraction,
    HistoryExtraction,
    JobCompensationExtraction,
    JobCoreExtraction,
    JobRequirementsExtraction,
    PersonalExtraction,
    SkillsExtraction,
)
from app.services.cv import apply_contact_fallbacks, total_experience_years
from app.services.llm import LLMError, generate_structured
from app.services.matching import compute_match
from app.services.salary import SalaryHint, parse_salary
from app.services.users import find_profile

log = logging.getLogger(__name__)

MAX_INPUT_CHARS = 16_000

# As with the CV, system prompt plus posting text form a shared prefix across all calls.
JOB_SYSTEM_PROMPT = """Sei un assistente che estrae dati strutturati da annunci di lavoro.
L'annuncio può essere in qualsiasi lingua, copiato da siti diversi (LinkedIn, Indeed, InfoJobs, siti aziendali)
e contenere testo di contorno come menu, pulsanti o annunci simili: ignoralo.
Regole generali:
- Usa solo informazioni presenti nel testo. Se un dato manca lascia null o una lista vuota, non inventare.
- Non tradurre: riporta i testi nella lingua originale dell'annuncio."""

JOB_CORE_TASK = """Compito: estrai i dati generali della posizione.
- title: il titolo del ruolo, senza sigle come (m/f) o (H/F).
- company: l'azienda che assume. Se l'annuncio è di un'agenzia per conto di un cliente non nominato, usa il nome dell'agenzia.
- location: città o sede; work_mode: "remote" per full remote, "hybrid" per ibrido o smart working parziale, "onsite" se in presenza.
- contract_type: tipo di contratto (es. tempo indeterminato, determinato, apprendistato, stage, P.IVA).
- seniority: junior, mid, senior o lead, se indicato o chiaramente deducibile dagli anni richiesti.
- experience_years_min: anni minimi di esperienza richiesti, come numero."""

JOB_COMPENSATION_TASK = """Compito: estrai retribuzione prevista e benefit. Leggi con attenzione tutto il testo: la
retribuzione compare spesso come "RAL", "retribuzione", "compenso", "stipendio", "salary", "pay range",
"inquadramento" o come importo con €, $ o "k", anche in fondo all'annuncio.
- salary: la retribuzione prevista come importo o range con la valuta, scritta in modo leggibile
  ("35-42k" -> "35.000 - 42.000 €"; "fino a 45k" -> "fino a 45.000 €"; "2.000 € per 14 mensilità" -> "2.000 € × 14 mensilità").
  Non convertire tra mensile e annuo. Se non c'è un importo ma una frase come "commisurata all'esperienza", riportala breve.
  Non usare come retribuzione buoni pasto, rimborsi, bonus una tantum o cifre che non sono stipendio.
- salary_period: "annual" se annua (RAL, annual salary, per year), "monthly" se mensile, "daily" se giornaliera,
  "hourly" se oraria; null se non indicato.
- salary_basis: "gross" se lorda (RAL è sempre lorda, gross, brutto), "net" se netta; null se non indicato.
- benefits: welfare, buoni pasto, smart working, formazione, assicurazioni e simili, una voce per benefit."""

JOB_REQUIREMENTS_TASK = """Compito: estrai mansioni e requisiti.
- responsibilities: le attività del ruolo, frasi brevi.
- requirements: i requisiti obbligatori, una frase breve per requisito.
- nice_to_have: i requisiti preferenziali ("costituisce titolo preferenziale", "nice to have", "gradito", "plus").
- skills: le singole competenze tecniche e trasversali con nomi brevi e canonici (es. "PostgreSQL", "Docker",
  "Comunicazione"), con importance "required" oppure "nice_to_have"."""

# System prompt and CV text are identical across calls, so Ollama reuses the processed prefix
# and every call after the first only pays for the trailing instructions.
CV_SYSTEM_PROMPT = """Sei un assistente che estrae dati strutturati da curriculum vitae.
Il CV può essere in qualsiasi lingua e con qualsiasi struttura: le sezioni possono chiamarsi in modi diversi
(es. Esperienza / Experience / Berufserfahrung, Istruzione / Formazione / Education) o mancare del tutto.
Il testo è estratto da PDF o Word: le colonne di un layout a più colonne sono riportate una dopo l'altra.
Regole generali:
- Usa solo informazioni presenti nel CV. Se un dato manca lascia null o una lista vuota, non inventare.
- Non tradurre: riporta nomi, titoli e descrizioni nella lingua originale del CV.
- Date in formato YYYY-MM se è indicato il mese, altrimenti YYYY. Se un'attività è in corso, end è null e current è true."""

PERSONAL_TASK = """Compito: estrai i dati personali.
- full_name, email, phone, location (città, paese) come scritti nel CV.
- headline: il ruolo o titolo professionale principale, breve.
- summary: 2-3 frasi che riassumono il profilo, nella lingua del CV. Se il CV ha una sezione tipo "About me" / "Profilo", basati su quella.
- links: LinkedIn, GitHub, portfolio e altri siti personali.
- languages: lingue parlate con il livello (madrelingua o CEFR)."""

HISTORY_TASK = """Compito: estrai il percorso del candidato, separando con cura le quattro categorie.
- experiences: SOLO esperienze lavorative (impiego, stage, tirocinio, collaborazione, freelance, attività retribuita o continuativa svolta per un'organizzazione o in proprio). Non inserire titoli di studio né progetti. In technologies le tecnologie e gli strumenti citati per quell'esperienza.
- education: SOLO percorsi di studio (laurea, master, dottorato, diploma, corsi lunghi). Esami, tesi, prove finali, specializzazioni e aree di studio vanno nei campi thesis e details del titolo a cui appartengono, mai come voci separate.
- projects: progetti personali, accademici o professionali descritti come progetti, con le tecnologie citate.
- certifications: SOLO certificazioni formali rilasciate da un ente (es. AWS Certified, Cisco CCNA, IELTS, PMP). Un esame universitario, una prova finale o un corso dentro una laurea NON è una certificazione: se non ci sono certificazioni lascia la lista vuota."""

SKILLS_TASK = """Compito: elenca le competenze del candidato e stima il livello di ciascuna.
- Includi le competenze della sezione skill e quelle chiaramente usate in esperienze, progetti e studi.
- Un nome per voce, breve e canonico (es. "PostgreSQL", "Docker", "Machine Learning"). Niente duplicati.
- category: il raggruppamento usato nel CV se presente, altrimenti uno generico (linguaggi, framework, database, cloud, strumenti, metodologie, soft skill).
- level, secondo questa scala:
  1 = base: solo citata o studiata, nessun uso concreto descritto.
  2 = intermedio: usata in progetti accademici o personali.
  3 = avanzato: usata in modo continuativo nel lavoro o in più progetti significativi.
  4 = esperto: anni di uso professionale documentato, ruolo di riferimento o certificazione avanzata.
- evidence: in poche parole dove compare l'uso (es. "progetto Roboverse, tesi magistrale")."""

ADVICE_SYSTEM_PROMPT = """Sei un career coach. Ricevi una posizione lavorativa, il profilo del candidato e
l'esito di un confronto automatico tra le skill. Rispondi in {language}, in modo concreto e sintetico:
- summary: 2-3 frasi sulla compatibilità complessiva.
- strengths: punti di forza del candidato per questa posizione.
- improvements: per ogni competenza mancante o parziale rilevante, un'azione concreta per migliorare
  (corso, progetto pratico, certificazione, come valorizzare esperienza simile nel CV)."""


def extract_job_fields(description: str) -> dict:
    """Fill application fields from the job posting text."""
    job = f"Annuncio di lavoro:\n<<<\n{description[:MAX_INPUT_CHARS]}\n>>>\n\n"
    hint = parse_salary(description)
    core = generate_structured(JOB_SYSTEM_PROMPT, job + JOB_CORE_TASK, JobCoreExtraction)
    compensation = generate_structured(
        JOB_SYSTEM_PROMPT, job + JOB_COMPENSATION_TASK + _salary_hint_note(hint), JobCompensationExtraction
    )
    requirements = generate_structured(JOB_SYSTEM_PROMPT, job + JOB_REQUIREMENTS_TASK, JobRequirementsExtraction)
    return {
        **core.model_dump(),
        **_reconcile_salary(compensation, hint).model_dump(),
        **requirements.model_dump(),
    }


def _salary_hint_note(hint: SalaryHint | None) -> str:
    if hint is None:
        return ""
    note = f'\n\nUn controllo automatico ha trovato questa riga sulla retribuzione: "{hint.text}"'
    details = [f"importo {hint.amount}"] if hint.amount else []
    details += [f"salary_period {hint.period}"] if hint.period else []
    details += [f"salary_basis {hint.basis}"] if hint.basis else []
    if details:
        note += f" (interpretata come {', '.join(details)})"
    return note + ". Verificala sul testo."


def _reconcile_salary(data: JobCompensationExtraction, hint: SalaryHint | None) -> JobCompensationExtraction:
    """Fall back to the deterministic parser when the model misses the salary or one of its attributes."""
    if hint is None:
        return data
    result = data.model_copy()
    llm_has_amount = bool(data.salary and re.search(r"\d", data.salary))
    if hint.has_amount and not llm_has_amount:
        result.salary = hint.amount
    result.salary_period = result.salary_period or hint.period
    result.salary_basis = result.salary_basis or hint.basis
    if not result.salary:
        # Without an amount, period and gross/net are meaningless
        result.salary_period = result.salary_basis = None
    return result


def extract_cv_fields(cv_text: str) -> dict:
    """Fill profile fields from the CV text."""
    cv = f"Curriculum vitae:\n<<<\n{cv_text[:MAX_INPUT_CHARS]}\n>>>\n\n"
    personal = generate_structured(CV_SYSTEM_PROMPT, cv + PERSONAL_TASK, PersonalExtraction)
    history = generate_structured(CV_SYSTEM_PROMPT, cv + HISTORY_TASK, HistoryExtraction)
    skills = generate_structured(CV_SYSTEM_PROMPT, cv + SKILLS_TASK, SkillsExtraction)
    return {
        **apply_contact_fallbacks(personal, cv_text).model_dump(),
        **history.model_dump(),
        "skills": _dedupe_skills(skills.model_dump()["skills"]),
        "years_of_experience": total_experience_years(history.experiences),
    }


def _dedupe_skills(skills: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for skill in skills:
        key = skill["name"].strip().lower()
        if key and (key not in seen or skill["level"] > seen[key]["level"]):
            seen[key] = skill
    return list(seen.values())


def generate_advice(application_id: int) -> None:
    with Session(engine) as session:
        app = session.get(Application, application_id)
        if app is None:
            return
        profile = find_profile(session, app.user_id)
        app.advice_status = TaskStatus.RUNNING
        session.add(app)
        session.commit()

        match = compute_match(app, profile)
        prompt = _advice_prompt(app, profile, match)
        try:
            advice = generate_structured(ADVICE_SYSTEM_PROMPT.format(language=t("advice_language")), prompt, AdviceExtraction)
        except LLMError as exc:
            app.advice_status = TaskStatus.FAILED
            app.advice = {"error": str(exc)}
            session.add(app)
            session.commit()
            return

        app.advice = {**advice.model_dump(), "score": match.score}
        app.advice_status = TaskStatus.DONE
        session.add(app)
        session.commit()


def _advice_prompt(app: Application, profile: Profile | None, match) -> str:
    def fmt(items) -> str:
        return ", ".join(i.skill for i in items) or "nessuna"

    lines = [
        f"Posizione: {app.title or 'n/d'} presso {app.company or 'n/d'} ({app.seniority or 'seniority n/d'})",
        "Requisiti: " + "; ".join(app.requirements or []),
        "Preferenziali: " + "; ".join(app.nice_to_have or []),
        "",
    ]
    if profile is not None:
        lines += [
            f"Candidato: {profile.headline or 'n/d'}, {profile.years_of_experience or 'n/d'} anni di esperienza",
            f"Sintesi: {profile.summary or 'n/d'}",
            "Skill del candidato (livello 1-4): "
            + ", ".join(f"{s.get('name')} ({s.get('level') or '?'})" for s in profile.skills),
            "Esperienze: " + "; ".join(
                f"{e.get('role') or ''} @ {e.get('company') or ''}" for e in profile.experiences
            ),
            "",
        ]
    lines += [
        f"Compatibilità stimata: {match.score}%",
        f"Skill compatibili: {fmt(match.matched)}",
        f"Skill parzialmente compatibili: {fmt(match.partial)}",
        f"Skill mancanti: {fmt(match.missing)}",
    ]
    return "\n".join(lines)

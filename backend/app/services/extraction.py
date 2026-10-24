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
# The prompts are strict on purpose: small models without reasoning follow fixed rules and an example much
# better than general guidance.
JOB_SYSTEM_PROMPT = """Sei un estrattore di dati da annunci di lavoro. Leggi l'annuncio tra <<< e >>> e compila i campi richiesti.
L'annuncio può essere in qualsiasi lingua ed essere copiato da siti diversi (LinkedIn, Indeed, InfoJobs, siti aziendali).

Regole valide per ogni campo:
1. Usa solo ciò che è scritto nell'annuncio. Non dedurre, non completare, non usare conoscenze esterne.
2. Se un dato non è scritto, metti null o una lista vuota. Un campo vuoto è sempre meglio di un dato inventato.
3. Riporta i testi nella lingua dell'annuncio, senza tradurli.
4. Ignora il testo che non fa parte dell'annuncio: menu, pulsanti, cookie, altri annunci, "candidati ora", note legali.
5. Nelle liste metti una voce per elemento, breve, senza duplicati e senza simboli di elenco.
6. Rispondi solo con il JSON richiesto."""

JOB_CORE_TASK = """Compito: compila i dati generali della posizione.
- title: il titolo del ruolo, senza sigle come (m/f), (H/F), (m/w/d).
- company: l'azienda che assume. Se un'agenzia cerca per un cliente non nominato, il nome dell'agenzia.
- location: la città della sede (o "città, paese" se il paese è scritto). Niente indirizzi o CAP.
- work_mode: "remote" se interamente da remoto, "hybrid" se in parte da remoto o smart working, "onsite" se scritto
  che è in presenza; null se non indicato.
- contract_type: il tipo di contratto come scritto, breve (es. "tempo indeterminato", "stage", "P.IVA").
- seniority: "junior", "mid", "senior" o "lead" solo se il livello è scritto (anche come "neolaureato" = junior,
  "esperto" = senior, "team leader" = lead). Non ricavarlo dagli anni di esperienza.
- education_required: il titolo di studio richiesto, breve (es. "Laurea in Informatica").
- experience_years_min: il numero minimo di anni di esperienza richiesti, solo il numero ("almeno 3 anni" -> 3).
- languages: le lingue richieste con il livello se scritto (es. "Inglese B2").
- contact_name, contact_email: la persona e l'email a cui candidarsi, solo se scritte.

Esempio di annuncio: "Rossi Srl cerca Sviluppatore Java (m/f) per la sede di Torino, ibrido. Tempo indeterminato.
Almeno 3 anni di esperienza, laurea in Informatica, inglese B2. CV a hr@rossi.it"
Risposta: {"title": "Sviluppatore Java", "company": "Rossi Srl", "location": "Torino", "work_mode": "hybrid",
"contract_type": "tempo indeterminato", "seniority": null, "education_required": "Laurea in Informatica",
"experience_years_min": 3, "languages": ["Inglese B2"], "contact_name": null, "contact_email": "hr@rossi.it"}"""

JOB_COMPENSATION_TASK = """Compito: compila retribuzione e benefit. Leggi tutto il testo: la retribuzione compare spesso come
"RAL", "retribuzione", "compenso", "stipendio", "salary", "pay range", "inquadramento" o come importo con €, $ o "k",
anche in fondo all'annuncio.
- salary: l'importo o il range dello stipendio con la valuta, scritto per esteso
  ("35-42k" -> "35.000 - 42.000 €"; "fino a 45k" -> "fino a 45.000 €"; "2.000 € per 14 mensilità" -> "2.000 € × 14 mensilità").
  Non convertire tra mensile e annuo. Se non c'è un importo ma una frase come "commisurata all'esperienza", riportala breve.
  Buoni pasto, rimborsi, bonus una tantum e premi non sono lo stipendio.
- salary_period: "annual" se annuo (RAL, annual salary, per year), "monthly" se mensile, "daily" se giornaliero,
  "hourly" se orario; null se non scritto.
- salary_basis: "gross" se lordo (la RAL è sempre lorda, gross, brutto), "net" se netto; null se non scritto.
- benefits: welfare, buoni pasto, smart working, formazione, assicurazioni e simili, una voce per benefit.

Esempio di annuncio: "... Offriamo RAL 35-42k, buoni pasto da 8 €, assicurazione sanitaria."
Risposta: {"salary": "35.000 - 42.000 €", "salary_period": "annual", "salary_basis": "gross",
"benefits": ["Buoni pasto da 8 €", "Assicurazione sanitaria"]}"""

JOB_REQUIREMENTS_TASK = """Compito: compila mansioni, requisiti e competenze.
- responsibilities: le attività del ruolo, una frase breve per attività (massimo 12).
- requirements: i requisiti obbligatori, una frase breve per requisito (massimo 12).
- nice_to_have: i requisiti preferenziali ("titolo preferenziale", "nice to have", "gradito", "plus"), massimo 8.
- skills: ogni competenza tecnica o trasversale nominata nei requisiti, con un nome breve e canonico
  ("PostgreSQL", non "ottima conoscenza di database PostgreSQL") e importance "required" se è tra i requisiti
  obbligatori, "nice_to_have" se è tra quelli preferenziali. Una competenza compare una volta sola.

Esempio di annuncio: "Svilupperai API REST. Requisiti: ottima conoscenza di Python e PostgreSQL. Gradita esperienza con Docker."
Risposta: {"responsibilities": ["Sviluppo di API REST"], "requirements": ["Ottima conoscenza di Python e PostgreSQL"],
"nice_to_have": ["Esperienza con Docker"], "skills": [{"name": "Python", "importance": "required"},
{"name": "PostgreSQL", "importance": "required"}, {"name": "Docker", "importance": "nice_to_have"}]}"""

# System prompt and CV text are identical across calls, so Ollama reuses the processed prefix
# and every call after the first only pays for the trailing instructions.
CV_SYSTEM_PROMPT = """Sei un estrattore di dati da curriculum vitae. Leggi il CV tra <<< e >>> e compila i campi richiesti.
Il CV può essere in qualsiasi lingua e con qualsiasi struttura: le sezioni possono chiamarsi in modi diversi
(es. Esperienza / Experience / Berufserfahrung, Istruzione / Formazione / Education) o mancare del tutto.
Il testo è estratto da PDF o Word: le colonne di un layout a più colonne sono riportate una dopo l'altra.

Regole valide per ogni campo:
1. Usa solo ciò che è scritto nel CV. Non dedurre, non completare, non usare conoscenze esterne.
2. Se un dato non è scritto, metti null o una lista vuota. Un campo vuoto è sempre meglio di un dato inventato.
3. Riporta nomi, titoli e descrizioni nella lingua del CV, senza tradurli.
4. Date nel formato YYYY-MM se il mese è scritto, altrimenti YYYY. Se un'attività è in corso, end è null e current è true.
5. Nelle liste metti una voce per elemento, senza duplicati e senza simboli di elenco.
6. Rispondi solo con il JSON richiesto."""

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


def clean_posting(text: str) -> str:
    """Shorter context for the model: spaces collapsed, no repeated lines (menus and footers copied twice)
    and no runs of empty lines."""
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = re.sub(r"[ \t\u00a0]+", " ", raw).strip()
        if line:
            if line.lower() in seen:
                continue
            seen.add(line.lower())
        elif not lines or not lines[-1]:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def extract_job_fields(description: str) -> dict:
    """Fill application fields from the job posting text."""
    job = f"Annuncio di lavoro:\n<<<\n{clean_posting(description)[:MAX_INPUT_CHARS]}\n>>>\n\n"
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

"""Filling the profile from the CV with the local model, plus deterministic checks so we don't rely on the model alone."""

import logging
import re
from datetime import date

from app.features.profile.schemas import (
    CVExperience,
    CVLink,
    HistoryExtraction,
    PersonalExtraction,
    SkillsExtraction,
)
from app.shared.llm import MAX_INPUT_CHARS, generate_structured

log = logging.getLogger(__name__)


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


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


PHONE_RE = re.compile(r"(?<![\w/])\+?\d[\d\s().-]{7,}\d(?![\w/])")


LINK_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com|gitlab\.com)/[\w\-./]+", re.I)


DATE_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?")


def apply_contact_fallbacks(personal: PersonalExtraction, text: str) -> PersonalExtraction:
    """Fill in email, phone and links when the model missed them."""
    data = personal.model_copy(deep=True)
    if not data.email and (m := EMAIL_RE.search(text)):
        data.email = m.group(0)
    if not data.phone:
        # At least 9 digits so year ranges like "2018 - 2023" aren't taken for a phone number
        phones = [m.group(0).strip() for m in PHONE_RE.finditer(text)]
        data.phone = next((p for p in phones if sum(c.isdigit() for c in p) >= 9), None)
    known = {link.url.lower().removeprefix("https://").removeprefix("www.") for link in data.links}
    for m in LINK_RE.finditer(text):
        url = m.group(0).rstrip(".")
        bare = url.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
        if bare not in known:
            known.add(bare)
            label = "LinkedIn" if "linkedin" in bare else "GitHub" if "github" in bare else "GitLab"
            data.links.append(CVLink(label=label, url=url if url.startswith("http") else f"https://{url}"))
    return data


def _month_index(value: str | None, *, end: bool) -> int | None:
    if not value or not (m := DATE_RE.match(value.strip())):
        return None
    year, month = int(m.group(1)), m.group(2)
    return year * 12 + (int(month) - 1 if month else (11 if end else 0))


def total_experience_years(experiences: list[CVExperience]) -> float | None:
    """Years of work experience, counting overlapping periods once."""
    today = date.today()
    now = today.year * 12 + today.month - 1
    spans = []
    for exp in experiences:
        start = _month_index(exp.start, end=False)
        stop = now if exp.current or not exp.end else _month_index(exp.end, end=True)
        if start is not None and stop is not None and stop >= start:
            spans.append((start, min(stop, now)))
    if not spans:
        return None
    spans.sort()
    months, (cur_start, cur_end) = 0, spans[0]
    for start, stop in spans[1:]:
        if start > cur_end + 1:
            months += cur_end - cur_start + 1
            cur_start, cur_end = start, stop
        else:
            cur_end = max(cur_end, stop)
    months += cur_end - cur_start + 1
    return round(months / 12, 1)

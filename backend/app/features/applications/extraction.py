"""Filling an application from its job posting with the local model."""

import logging
import re

from app.features.applications.salary import SalaryHint, parse_salary
from app.features.applications.schemas import (
    JobCompensationExtraction,
    JobCoreExtraction,
    JobRequirementsExtraction,
)
from app.shared.llm import MAX_INPUT_CHARS, generate_structured

log = logging.getLogger(__name__)


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

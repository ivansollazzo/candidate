"""Application contracts, and the structured outputs asked to the model when reading a job posting."""

from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.applications.models import ApplicationStatus, EventType


class ExtractedSkill(BaseModel):
    name: str = Field(description="Nome breve della competenza, es. 'Python', 'Docker', 'Project management'")
    importance: str = Field(description="'required' se obbligatoria, 'nice_to_have' se preferenziale")


class JobCoreExtraction(BaseModel):
    title: str | None = Field(None, description="Titolo della posizione")
    company: str | None = Field(None, description="Azienda che assume (non l'agenzia, se indicata anche quella)")
    location: str | None = Field(None, description="Città o sede di lavoro")
    work_mode: str | None = Field(None, description="onsite, hybrid oppure remote")
    contract_type: str | None = Field(None, description="es. tempo indeterminato, determinato, stage, P.IVA")
    seniority: str | None = Field(None, description="es. junior, mid, senior, lead")
    education_required: str | None = None
    experience_years_min: float | None = Field(None, description="Anni minimi di esperienza richiesti")
    languages: list[str] = Field([], description="Lingue richieste con il livello, es. 'Inglese B2'")
    contact_name: str | None = None
    contact_email: str | None = None


SALARY_PERIODS = {"annual", "monthly", "daily", "hourly"}


SALARY_BASES = {"gross", "net"}


def _normalize_choice(value, allowed: set[str], synonyms: dict[str, str]):
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    key = synonyms.get(key, key)
    return key if key in allowed else None


PERIOD_SYNONYMS = {"annua": "annual", "annuale": "annual", "yearly": "annual", "year": "annual", "anno": "annual",
                   "mensile": "monthly", "month": "monthly", "mese": "monthly",
                   "giornaliera": "daily", "day": "daily", "giorno": "daily",
                   "oraria": "hourly", "hour": "hourly", "ora": "hourly"}


BASIS_SYNONYMS = {"lorda": "gross", "lordo": "gross", "brutto": "gross", "netta": "net", "netto": "net"}


class SalaryFields(BaseModel):
    """Shared period and gross/net validation, for both LLM output and manual edits."""

    @field_validator("salary_period", mode="before", check_fields=False)
    @classmethod
    def _period(cls, value):
        return _normalize_choice(value, SALARY_PERIODS, PERIOD_SYNONYMS)

    @field_validator("salary_basis", mode="before", check_fields=False)
    @classmethod
    def _basis(cls, value):
        return _normalize_choice(value, SALARY_BASES, BASIS_SYNONYMS)


class JobCompensationExtraction(SalaryFields):
    salary: str | None = Field(None, description="Retribuzione prevista: importo o range con valuta, es. "
                                                  "'35.000 - 42.000 €', '1.600 €', 'fino a 45.000 €'")
    salary_period: Literal["annual", "monthly", "daily", "hourly"] | None = None
    salary_basis: Literal["gross", "net"] | None = None
    benefits: list[str] = []


class JobRequirementsExtraction(BaseModel):
    responsibilities: list[str] = []
    requirements: list[str] = []
    nice_to_have: list[str] = []
    skills: list[ExtractedSkill] = []


class ApplicationUpdate(SalaryFields):
    # Job posting text, read again when the AI fills the application (see POST /api/applications/{id}/fills)
    description: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    work_mode: str | None = None
    contract_type: str | None = None
    seniority: str | None = None
    salary: str | None = None
    salary_period: str | None = None
    salary_basis: str | None = None
    responsibilities: list[str] | None = None
    requirements: list[str] | None = None
    nice_to_have: list[str] | None = None
    benefits: list[str] | None = None
    skills: list[ExtractedSkill] | None = None
    languages: list[str] | None = None
    education_required: str | None = None
    experience_years_min: float | None = None
    source_url: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    status: ApplicationStatus | None = None
    applied_on: date | None = None
    notes: str | None = None


class EventCreate(BaseModel):
    application_id: int
    type: EventType = EventType.NOTE
    occurred_on: date
    starts_at: time | None = None
    ends_at: time | None = None
    title: str = Field(min_length=1)
    details: str | None = None
    completed: bool = False


class EventUpdate(BaseModel):
    type: EventType | None = None
    occurred_on: date | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    title: str | None = Field(default=None, min_length=1)
    details: str | None = None
    completed: bool | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    type: str
    occurred_on: date
    starts_at: time | None
    ends_at: time | None
    title: str
    details: str | None
    completed: bool
    created_at: datetime


class AgendaEvent(EventRead):
    """Event with its application data, for the agenda and overview."""

    application_title: str | None
    application_company: str | None


class ApplicationsUpdate(BaseModel):
    """Several applications moved to one status at once."""

    ids: Annotated[list[int], Field(min_length=1, max_length=1000)]
    status: ApplicationStatus


class ApplicationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    company: str | None
    location: str | None
    work_mode: str | None
    salary: str | None
    salary_period: str | None
    salary_basis: str | None
    status: str
    applied_on: date | None
    created_at: datetime
    updated_at: datetime


class ApplicationListItem(ApplicationSummary):
    # Date of the latest agenda event (status changes excluded), for sorting the list
    last_event_on: date | None = None
    # Score of the compatibility report, when one has been generated
    match_score: int | None = None
    # The report should be regenerated
    report_stale: bool = False
    # Skills of the posting the report found missing from the profile (soft skills excluded)
    missing_skills: list[str] = []


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str | None
    size: int
    created_at: datetime


class ApplicationRead(ApplicationSummary):
    contract_type: str | None
    seniority: str | None
    responsibilities: list[str]
    requirements: list[str]
    nice_to_have: list[str]
    benefits: list[str]
    skills: list[dict]
    languages: list[str]
    education_required: str | None
    experience_years_min: float | None
    source_url: str | None
    contact_name: str | None
    contact_email: str | None
    notes: str | None
    has_description: bool = Field(description="True se è salvato il testo dell'annuncio, per compilare con l'LLM")
    # Report, or {"error": ...} when the generation failed
    report: dict | None
    report_status: str | None
    # The skills changed after the report was generated
    report_stale: bool
    events: list[EventRead]
    attachments: list[AttachmentRead]

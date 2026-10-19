from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ApplicationStatus, EventType


# Structured outputs requested from the LLM

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


class CVSkill(BaseModel):
    name: str = Field(description="Nome breve e canonico della competenza, es. 'Python', 'Docker'")
    category: str | None = Field(None, description="Categoria, es. linguaggi, framework, database, cloud, soft skill")
    level: int = Field(2, ge=1, le=4, description="1 base, 2 intermedio, 3 avanzato, 4 esperto")
    evidence: str | None = Field(None, description="Dove è stata usata secondo il CV (lavoro, progetto, corso)")

    @field_validator("level", mode="before")
    @classmethod
    def _clamp_level(cls, value):
        try:
            return min(4, max(1, int(value)))
        except (TypeError, ValueError):
            return 2


class ProfileSkill(CVSkill):
    """Skill stored in the profile; level may be missing until the user sets it."""

    level: int | None = Field(None, ge=1, le=4)

    @field_validator("level", mode="before")
    @classmethod
    def _clamp_level(cls, value):
        return None if value is None else CVSkill._clamp_level(value)


class CVExperience(BaseModel):
    role: str | None = None
    company: str | None = None
    location: str | None = None
    employment_type: str | None = Field(None, description="es. tempo pieno, part-time, stage, freelance")
    start: str | None = Field(None, description="Data di inizio, formato YYYY-MM oppure YYYY")
    end: str | None = Field(None, description="Data di fine, formato YYYY-MM oppure YYYY; null se in corso")
    current: bool = False
    description: str | None = None
    technologies: list[str] = Field([], description="Tecnologie, strumenti e metodologie usati")


class CVEducation(BaseModel):
    degree: str | None = Field(None, description="Titolo, es. Laurea magistrale, Master's Degree, Diploma")
    field_of_study: str | None = None
    institution: str | None = None
    location: str | None = None
    start: str | None = Field(None, description="YYYY-MM oppure YYYY")
    end: str | None = Field(None, description="YYYY-MM oppure YYYY; null se in corso")
    grade: str | None = Field(None, description="Voto finale, es. 110/110 cum laude")
    thesis: str | None = None
    details: str | None = Field(None, description="Specializzazione, esami, aree o corsi rilevanti")


class CVProject(BaseModel):
    name: str
    context: str | None = Field(None, description="personale, accademico, professionale o altro")
    team: str | None = Field(None, description="es. individuale, team di 4 persone")
    start: str | None = None
    end: str | None = None
    description: str | None = None
    technologies: list[str] = []


class CVCertification(BaseModel):
    name: str
    issuer: str | None = Field(None, description="Ente che ha rilasciato la certificazione")
    issued_on: str | None = Field(None, description="YYYY-MM oppure YYYY")
    expires_on: str | None = None
    credential_id: str | None = None
    url: str | None = None


class CVLanguage(BaseModel):
    language: str
    level: str | None = Field(None, description="Madrelingua oppure livello CEFR (A1-C2) se indicato")


class CVLink(BaseModel):
    label: str | None = Field(None, description="es. LinkedIn, GitHub, Portfolio")
    url: str


class PersonalExtraction(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = Field(None, description="Ruolo o titolo professionale sintetico")
    summary: str | None = Field(None, description="Sintesi del profilo in 2-3 frasi")
    links: list[CVLink] = []
    languages: list[CVLanguage] = []


class HistoryExtraction(BaseModel):
    experiences: list[CVExperience] = []
    education: list[CVEducation] = []
    projects: list[CVProject] = []
    certifications: list[CVCertification] = []


class SkillsExtraction(BaseModel):
    skills: list[CVSkill] = []


class SkillImprovement(BaseModel):
    skill: str
    suggestion: str = Field(description="Azione concreta per colmare il gap")


class AdviceExtraction(BaseModel):
    summary: str = Field(description="Valutazione sintetica della compatibilità con la posizione")
    strengths: list[str] = []
    improvements: list[SkillImprovement] = []


# API

class ApplicationUpdate(SalaryFields):
    # Job posting text returned by /api/ai/job-posting, kept for re-running the LLM fill
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
    title: str = Field(min_length=1)
    details: str | None = None
    completed: bool = False


class EventUpdate(BaseModel):
    type: EventType | None = None
    occurred_on: date | None = None
    starts_at: time | None = None
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
    title: str
    details: str | None
    completed: bool
    created_at: datetime


class AgendaEvent(EventRead):
    """Event with its application data, for the agenda and overview."""

    application_title: str | None
    application_company: str | None


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
    advice: dict | None
    advice_status: str | None
    events: list[EventRead]


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = None
    years_of_experience: float | None = None
    links: list[CVLink] | None = None
    skills: list[ProfileSkill] | None = None
    experiences: list[CVExperience] | None = None
    education: list[CVEducation] | None = None
    projects: list[CVProject] | None = None
    certifications: list[CVCertification] | None = None
    languages: list[CVLanguage] | None = None


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str | None
    email: str | None
    phone: str | None
    location: str | None
    headline: str | None
    summary: str | None
    years_of_experience: float | None
    links: list[dict]
    skills: list[dict]
    experiences: list[dict]
    education: list[dict]
    projects: list[dict]
    certifications: list[dict]
    languages: list[dict]
    cv_filename: str | None
    updated_at: datetime


class SkillMatchItem(BaseModel):
    skill: str
    importance: str
    status: str  # match | partial | missing
    matched_with: str | None = None
    similarity: float | None = None
    level: int | None = None  # skill level in the profile
    note: str | None = None


class MatchResult(BaseModel):
    score: int = Field(description="Percentuale di compatibilità 0-100")
    matched: list[SkillMatchItem]
    partial: list[SkillMatchItem]
    missing: list[SkillMatchItem]
    has_profile: bool


class SettingsRead(BaseModel):
    """System settings; user preferences (language, theme) live on UserRead."""

    model_config = ConfigDict(from_attributes=True)

    llm_enabled: bool
    llm_accelerator: str
    update_branch: str | None
    update_check_hours: int
    password_min_length: int
    password_require_uppercase: bool
    password_require_digit: bool
    password_require_symbol: bool
    session_hours: int
    max_login_attempts: int
    lockout_minutes: int


class SettingsUpdate(BaseModel):
    llm_enabled: bool | None = None
    llm_accelerator: Literal["auto", "cuda", "rocm", "vulkan", "cpu"] | None = None
    # Empty string: follow the branch that is checked out
    update_branch: str | None = Field(default=None, max_length=200)
    update_check_hours: Literal[0, 1, 6, 12, 24, 168] | None = None
    password_min_length: int | None = Field(default=None, ge=8, le=128)
    password_require_uppercase: bool | None = None
    password_require_digit: bool | None = None
    password_require_symbol: bool | None = None
    session_hours: int | None = Field(default=None, ge=1, le=720)
    max_login_attempts: int | None = Field(default=None, ge=0, le=100)
    lockout_minutes: int | None = Field(default=None, ge=1, le=1440)


class PasswordPolicy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    password_min_length: int
    password_require_uppercase: bool
    password_require_digit: bool
    password_require_symbol: bool


# Users

Username = Annotated[str, Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")]
Email = Annotated[str, Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Role = Literal["admin", "user"]
Language = Literal["it", "en"]
Theme = Literal["light", "dark", "system"]
ApplicationSort = Literal["applied", "status", "name", "event"]
# Upper bound so we never hash huge inputs
Secret = Annotated[str, Field(max_length=256)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    language: str
    theme: str
    application_sort: str
    onboarded: bool
    has_avatar: bool
    created_at: datetime
    updated_at: datetime


class UserWithKey(BaseModel):
    """Newly created or recovered user, with the recovery key to show only once."""

    user: UserRead
    recovery_key: str


class SetupRequest(BaseModel):
    username: Username
    email: Email
    password: Secret
    language: Language = "it"


class LoginRequest(BaseModel):
    username: Annotated[str, Field(max_length=50)]
    password: Secret


class ResetRequest(BaseModel):
    username: Annotated[str, Field(max_length=50)]
    recovery_key: Secret
    new_password: Secret


class AuthStatus(BaseModel):
    setup_required: bool
    password_policy: PasswordPolicy


class MeUpdate(BaseModel):
    username: Username | None = None
    email: Email | None = None
    language: Language | None = None
    theme: Theme | None = None
    application_sort: ApplicationSort | None = None
    onboarded: bool | None = None


class PasswordChange(BaseModel):
    current_password: Secret
    new_password: Secret


class PasswordConfirm(BaseModel):
    password: Secret


class UserCreate(BaseModel):
    username: Username
    email: Email
    password: Secret
    role: Role = "user"
    language: Language = "it"


class UserUpdate(BaseModel):
    username: Username | None = None
    email: Email | None = None
    role: Role | None = None
    password: Secret | None = None


class AITaskRead(BaseModel):
    id: str
    status: str
    result: dict | None = None
    error: str | None = None
    # Job posting text read from text, link or file
    source_text: str | None = None


class UpdateStatus(BaseModel):
    # unavailable (no updater or not a Git clone), idle, checking, updating
    status: str
    # fetch, build, cleanup
    step: str | None = None
    version: str
    build: str


class BranchRelease(BaseModel):
    name: str
    version: str
    build: str
    commit: str
    newer: bool


class UpdateResult(BaseModel):
    # ok, failed
    result: str
    # fetch, branch, local_changes, checkout, build
    error: str = ""
    detail: str = ""
    restart_required: bool = False
    finished_at: str


class UpdatesRead(UpdateStatus):
    # Checked out, and followed for updates
    branch: str | None = None
    followed_branch: str | None = None
    commit: str | None = None
    checked_at: str | None = None
    branches: list[BranchRelease]
    update_available: bool
    last: UpdateResult | None = None


"""Profile contracts, and the structured outputs asked to the model when reading a CV."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    # Null until the profile is saved for the first time
    id: int | None
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
    updated_at: datetime | None

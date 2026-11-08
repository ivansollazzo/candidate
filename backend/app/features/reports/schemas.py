"""Profile match report: the model output and the stored report."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class SkillImprovement(BaseModel):
    skill: str
    suggestion: str = Field(description="Azione concreta per colmare il gap")


class SkillAssessment(BaseModel):
    # Every field is required, so a small model can't answer with an empty object
    skill: str = Field(description="Competenza dell'annuncio, scritta esattamente come nell'elenco ricevuto")
    kind: Literal["technical", "language", "soft"] = Field(
        description="technical: competenza tecnica o di mestiere; language: lingua; soft: soft skill")
    reason: str = Field(description="Motivazione in una frase breve, basata sul profilo")
    matched_with: str | None = Field(
        description="Competenza o lingua del candidato che la copre, scritta esattamente come nel profilo; "
                    "null se nessuna")
    status: Literal["match", "partial", "missing"] = Field(
        description="match: il candidato la possiede; partial: ha qualcosa di simile o vicino; missing: non la possiede")


class ReportExtraction(BaseModel):
    skills: list[SkillAssessment]
    summary: str = Field(description="Valutazione sintetica della compatibilità con la posizione")
    strengths: list[str]
    improvements: list[SkillImprovement]


class ApplicationReports(BaseModel):
    """Profile match reports to (re)generate for several applications."""

    ids: Annotated[list[int], Field(min_length=1, max_length=1000)]


class ReportsQueued(BaseModel):
    queued: int
    # Applications skipped: without the position's skills, or with a report already waiting or running
    without_skills: int
    already_queued: int


class ReportSkill(BaseModel):
    skill: str
    importance: str
    kind: str  # technical | language | soft
    status: str  # match | partial | missing
    matched_with: str | None = None
    level: int | None = None  # skill level in the profile
    reason: str | None = None
    note: str | None = None


class Report(BaseModel):
    """Compatibility report stored on the application."""

    score: int = Field(description="Percentuale di compatibilità 0-100, soft skill escluse")
    skills: list[ReportSkill]
    summary: str
    strengths: list[str]
    improvements: list[SkillImprovement]
    generated_at: datetime

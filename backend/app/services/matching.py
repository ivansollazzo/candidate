"""Compare a position's required skills against the profile's."""

import logging
import re
from functools import lru_cache

import numpy as np

from app.config import get_settings
from app.i18n import t
from app.models import Application, Profile
from app.schemas import MatchResult, SkillMatchItem

log = logging.getLogger(__name__)

# Score weight of required skills relative to nice-to-have ones
WEIGHTS = {"required": 2.0, "nice_to_have": 1.0}

SENIOR_KEYWORDS = ("senior", "lead", "principal", "staff", "expert", "head", "architect")

# Common synonyms, so we don't rely on embeddings alone
ALIASES = {
    "postgres": "postgresql",
    "js": "javascript",
    "ts": "typescript",
    "k8s": "kubernetes",
    "golang": "go",
    "react.js": "react",
    "reactjs": "react",
    "node": "node.js",
    "nodejs": "node.js",
    "ml": "machine learning",
    "gcp": "google cloud",
    "aws": "amazon web services",
}


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer

    name = get_settings().embedding_model
    log.info("Caricamento modello di embedding %s", name)
    return SentenceTransformer(name, device="cpu")


def embed(texts: list[str]) -> np.ndarray:
    # e5 models need the "query: " prefix for symmetric comparisons
    vectors = _model().encode([f"query: {t}" for t in texts], normalize_embeddings=True)
    return np.asarray(vectors)


def normalize(skill: str) -> str:
    key = re.sub(r"\s+", " ", skill.strip().lower())
    return ALIASES.get(key, key)


def compute_match(app: Application, profile: Profile | None) -> MatchResult:
    job_skills = [s for s in (app.skills or []) if s.get("name")]
    profile_skills = [s["name"] for s in (profile.skills if profile else []) if s.get("name")]

    if not job_skills:
        return MatchResult(score=0, matched=[], partial=[], missing=[], has_profile=bool(profile_skills))
    if not profile_skills:
        missing = [
            SkillMatchItem(skill=s["name"], importance=s.get("importance") or "required", status="missing")
            for s in job_skills
        ]
        return MatchResult(score=0, matched=[], partial=[], missing=missing, has_profile=False)

    settings = get_settings()
    normalized_profile = {normalize(name): name for name in profile_skills}

    # Exact match first, then embeddings only for the remaining skills
    items: list[SkillMatchItem | None] = []
    pending: list[int] = []
    for i, skill in enumerate(job_skills):
        importance = skill.get("importance") or "required"
        exact = normalized_profile.get(normalize(skill["name"]))
        if exact:
            items.append(SkillMatchItem(skill=skill["name"], importance=importance, status="match",
                                        matched_with=exact, similarity=1.0))
        else:
            items.append(None)
            pending.append(i)

    similarities = None
    if pending:
        try:
            job_vectors = embed([job_skills[i]["name"] for i in pending])
            profile_vectors = embed(profile_skills)
            similarities = job_vectors @ profile_vectors.T
        except Exception:
            # Model unavailable (e.g. first run offline): exact match only
            log.exception("Embeddings non disponibili, uso solo il confronto esatto")
    for i in pending:
        if similarities is None:
            items[i] = SkillMatchItem(skill=job_skills[i]["name"],
                                      importance=job_skills[i].get("importance") or "required", status="missing")
    if similarities is not None:
        for row, i in enumerate(pending):
            best = int(np.argmax(similarities[row]))
            score = float(similarities[row][best])
            if score >= settings.match_threshold:
                status = "match"
            elif score >= settings.partial_match_threshold:
                status = "partial"
            else:
                status = "missing"
            items[i] = SkillMatchItem(
                skill=job_skills[i]["name"],
                importance=job_skills[i].get("importance") or "required",
                status=status,
                matched_with=profile_skills[best] if status != "missing" else None,
                similarity=round(score, 3),
            )

    resolved = [item for item in items if item is not None]
    levels = {s["name"]: s.get("level") for s in profile.skills if s.get("name")}
    senior = any(k in (app.seniority or "").lower() for k in SENIOR_KEYWORDS)
    for item in resolved:
        if item.matched_with is None:
            continue
        item.level = levels.get(item.matched_with)
        _apply_level(item, senior)
    total = sum(WEIGHTS.get(i.importance, 1.0) for i in resolved)
    earned = sum(
        WEIGHTS.get(i.importance, 1.0) * {"match": 1.0, "partial": 0.5}.get(i.status, 0.0) for i in resolved
    )
    return MatchResult(
        score=round(100 * earned / total) if total else 0,
        matched=[i for i in resolved if i.status == "match"],
        partial=[i for i in resolved if i.status == "partial"],
        missing=[i for i in resolved if i.status == "missing"],
        has_profile=True,
    )


def _apply_level(item: SkillMatchItem, senior: bool) -> None:
    """A skill present at too low a level for the position counts as partial."""
    if item.level is None or item.status != "match":
        return
    if item.level == 1 and item.importance == "required":
        item.status = "partial"
        item.note = t("level_basic")
    elif senior and item.level <= 2:
        item.status = "partial"
        item.note = t("level_too_low_senior", level=t(f"level_{item.level}"))

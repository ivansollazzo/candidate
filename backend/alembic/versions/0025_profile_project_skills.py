"""profile: technologies of projects and experiences become skills once here, no longer when the profile is read

Profiles saved before skills were taken from projects and experiences get them now; since then every write of the
profile adds them (app.services.profiles.apply_profile_changes).

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-08
"""
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Same texts as app.core.i18n (skill_from_project, skill_from_experience)
EVIDENCE = {"it": ("Progetto {name}", "Esperienza {name}"), "en": ("Project {name}", "Experience {name}")}


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT profile.id, profile.skills, profile.projects, profile.experiences, app_user.language "
        "FROM profile LEFT JOIN app_user ON app_user.id = profile.user_id"
    )).all()
    for profile_id, skills, projects, experiences, language in rows:
        project_text, experience_text = EVIDENCE.get(language or "it", EVIDENCE["it"])
        known = {skill["name"].strip().lower() for skill in skills or []}
        sources = [(p, project_text.format(name=p.get("name") or "")) for p in projects or []]
        sources += [(e, experience_text.format(name=" · ".join(filter(None, (e.get("role"), e.get("company"))))))
                    for e in experiences or []]
        added = []
        for entry, evidence in sources:
            for tech in entry.get("technologies") or []:
                name = tech.strip()
                if name and name.lower() not in known:
                    known.add(name.lower())
                    added.append({"name": name, "category": None, "level": None, "evidence": evidence})
        if added:
            bind.execute(sa.text("UPDATE profile SET skills = CAST(:skills AS jsonb) WHERE id = :id"),
                         {"skills": json.dumps([*(skills or []), *added]), "id": profile_id})


def downgrade() -> None:
    pass

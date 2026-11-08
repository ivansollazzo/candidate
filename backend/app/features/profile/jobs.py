"""Filling the profile from the CV, as a background job."""

from sqlmodel import Session

from app.core.i18n import t
from app.features.background_jobs.models import Job
from app.features.background_jobs.service import JobHandler, split_result
from app.features.profile.extraction import extract_cv_fields
from app.features.profile.service import apply_profile_changes, find_profile
from app.shared.llm import LLMError


class ProfileFill(JobHandler):
    def prepare(self, session: Session, job: Job):
        profile = find_profile(session, job.user_id)
        if profile is None or not profile.cv_text:
            raise LLMError(t("upload_first_cv"))
        cv_text = profile.cv_text
        return lambda: extract_cv_fields(cv_text)

    def finish(self, session: Session, job: Job, result) -> None:
        profile = find_profile(session, job.user_id)
        fill, job.proposal = split_result(profile.model_dump(), result)
        apply_profile_changes(session, profile, fill)

    def accept(self, session: Session, job: Job) -> None:
        if profile := find_profile(session, job.user_id):
            apply_profile_changes(session, profile, job.proposal)

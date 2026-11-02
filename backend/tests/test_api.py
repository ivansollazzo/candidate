import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    ExtractedSkill,
    HistoryExtraction,
    JobCompensationExtraction,
    JobCoreExtraction,
    JobRequirementsExtraction,
    PersonalExtraction,
    ReportExtraction,
    SkillAssessment,
    SkillsExtraction,
)
from app.services import extraction, jobs, report, sources
from app.services.llm import LLMError

JOB_TEXT = "Cerchiamo un Backend Developer Python a Milano, RAL 35-42k. Requisiti: Python, Postgres, Docker. Gradito Kubernetes."


def fake_llm(system, user, schema):
    if schema is JobCoreExtraction:
        return JobCoreExtraction(title="Backend Developer", company="ACME", location="Milano")
    if schema is JobCompensationExtraction:
        # The model skips the salary: it must come from the deterministic parser
        assert "RAL 35-42k" in user
        return JobCompensationExtraction(benefits=["Buoni pasto"])
    if schema is JobRequirementsExtraction:
        return JobRequirementsExtraction(
            requirements=["Python", "PostgreSQL", "Docker"],
            skills=[ExtractedSkill(name="Python", importance="required"),
                    ExtractedSkill(name="Postgres", importance="required"),
                    ExtractedSkill(name="Docker", importance="required"),
                    ExtractedSkill(name="Kubernetes", importance="nice_to_have")],
        )
    if schema is PersonalExtraction:
        # The model "forgets" email and phone: they must come from the deterministic fallback
        return PersonalExtraction(full_name="Ivan Rossi", headline="Software engineer")
    if schema is HistoryExtraction:
        return HistoryExtraction(
            experiences=[{"role": "Dev", "company": "A", "start": "2020-01", "end": "2021-12"},
                         {"role": "Dev", "company": "B", "start": "2021-06", "end": "2022-12"}],
            education=[{"degree": "Laurea", "institution": "UniPA", "details": "Esame finale: Docker"}],
        )
    if schema is SkillsExtraction:
        return SkillsExtraction(skills=[{"name": "Python", "level": 3}, {"name": "PostgreSQL", "level": 2},
                                        {"name": "Docker Compose", "level": 3}, {"name": "python", "level": 9}])
    raise AssertionError(schema)


# How the fake model judges a skill: (kind, status, profile skill it cites)
JUDGEMENTS = {
    "python": ("technical", "match", "python"),
    "postgres": ("technical", "match", "PostgreSQL"),
    "docker": ("technical", "match", "Docker Compose"),
    "machine learning": ("technical", "match", "PyTorch"),
    "english": ("language", "match", "Inglese"),
    "teamwork": ("soft", "missing", None),
    "rust": ("technical", "partial", "Non nel profilo"),
}


def fake_report_llm(system, user, schema):
    assert schema is ReportExtraction
    listed = user.split("Competenze dell'annuncio:\n")[1].split("\nRequisiti:")[0]
    names = [line.removeprefix("  - ").rsplit(" (", 1)[0] for line in listed.splitlines()]
    skills = []
    for name in names:
        kind, status, matched = JUDGEMENTS.get(name.lower(), ("technical", "missing", None))
        skills.append(SkillAssessment(skill=name.upper(), kind=kind, reason="perché sì", matched_with=matched,
                                      status=status))
    return ReportExtraction(skills=skills, summary="Buona compatibilità", strengths=["Python"],
                            improvements=[{"skill": "Kubernetes", "suggestion": "Corso CKAD"}])


@pytest.fixture(autouse=True)
def mocks(monkeypatch):
    monkeypatch.setattr(extraction, "generate_structured", fake_llm)
    monkeypatch.setattr(report, "generate_structured", fake_report_llm)


def run_jobs():
    """The worker thread doesn't run in tests: process the queue now."""
    jobs.run_all()


def create_with_ai(client, **kwargs) -> dict:
    r = client.post("/api/applications/ai", **kwargs)
    assert r.status_code == 201, r.text
    return r.json()


def request_report(client, app_id: int) -> None:
    assert client.post(f"/api/applications/{app_id}/report").status_code == 202
    run_jobs()


def test_manual_application_lifecycle(client):
    r = client.post("/api/applications", json={"title": "Backend Developer", "company": "ACME"})
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "applied" and data["applied_on"] is not None
    assert data["has_description"] is False and "description" not in data
    app_id = data["id"]

    r = client.patch(f"/api/applications/{app_id}", json={"status": "interview", "notes": "Inviata via LinkedIn"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "interview"
    assert body["events"][0]["type"] == "status_change"

    r = client.post("/api/events", json={"application_id": app_id, "type": "interview", "occurred_on": "2026-10-20",
                                         "starts_at": "15:00", "title": "Colloquio tecnico"})
    assert r.status_code == 201
    assert len(client.get(f"/api/applications/{app_id}").json()["events"]) == 2

    assert [a["id"] for a in client.get("/api/applications").json()] == [app_id]
    assert client.delete(f"/api/applications/{app_id}").status_code == 204


def test_ai_creates_application_in_background(client):
    app = create_with_ai(client, data={"text": JOB_TEXT})
    # Saved right away with its posting, filled in later
    assert app["title"] is None and app["has_description"]
    [job] = client.get("/api/jobs").json()
    assert (job["kind"], job["status"], job["position"], job["new_application"]) == ("application", "pending", 1, True)
    assert job["application_id"] == app["id"]

    run_jobs()
    data = client.get(f"/api/applications/{app['id']}").json()
    assert (data["title"], data["company"]) == ("Backend Developer", "ACME")
    assert (data["salary"], data["salary_period"], data["salary_basis"]) == ("35.000 – 42.000 €", "annual", "gross")
    assert data["benefits"] == ["Buoni pasto"] and data["skills"][0]["name"] == "Python"
    [job] = client.get("/api/jobs").json()
    assert (job["status"], job["proposal"], job["position"]) == ("done", None, None)
    assert job["application_title"] == "Backend Developer"
    # Finished jobs stay listed until dismissed
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get("/api/jobs").json() == []
    assert client.get(f"/api/applications/{app['id']}").status_code == 200

    # Filling again from the saved posting: empty fields are filled, different values only proposed
    client.patch(f"/api/applications/{app['id']}", json={"title": "Dev", "location": None})
    r = client.post(f"/api/applications/{app['id']}/fill")
    assert r.status_code == 202 and r.json()["new_application"] is False
    assert client.post(f"/api/applications/{app['id']}/fill").status_code == 409
    run_jobs()
    data = client.get(f"/api/applications/{app['id']}").json()
    assert (data["title"], data["location"]) == ("Dev", "Milano")
    [job] = client.get("/api/jobs").json()
    assert job["proposal"] == {"title": "Backend Developer"}
    assert client.post(f"/api/jobs/{job['id']}/apply").status_code == 204
    assert client.get(f"/api/applications/{app['id']}").json()["title"] == "Backend Developer"
    assert client.get("/api/jobs").json() == []


def test_report_queued_after_fill(client):
    client.patch("/api/profile", json={"skills": [{"name": "Python", "level": 3}]})
    app = create_with_ai(client, data={"text": JOB_TEXT, "report": "true"})
    [job] = client.get("/api/jobs").json()
    assert job["then_report"] is True
    run_jobs()
    data = client.get(f"/api/applications/{app['id']}").json()
    assert data["report_status"] == "done" and data["report"]["score"] > 0
    assert [j["kind"] for j in client.get("/api/jobs").json()] == ["application", "report"]
    item = next(a for a in client.get("/api/applications").json() if a["id"] == app["id"])
    assert item["match_score"] == data["report"]["score"] and item["report_stale"] is False
    assert item["last_event_on"] is None and item["last_activity_on"] is None
    client.patch(f"/api/applications/{app['id']}", json={"status": "interview"})
    item = next(a for a in client.get("/api/applications").json() if a["id"] == app["id"])
    assert item["last_event_on"] is None and item["last_activity_on"] is not None
    assert item["missing_skills"] == [s["skill"] for s in data["report"]["skills"]
                                      if s["status"] == "missing" and s["kind"] != "soft"]


def test_event_end_time(client):
    app_id = client.post("/api/applications", json={"title": "Dev"}).json()["id"]
    base = {"application_id": app_id, "type": "interview", "occurred_on": "2026-11-10", "title": "Colloquio"}
    assert client.post("/api/events", json={**base, "ends_at": "16:00"}).status_code == 422
    assert client.post("/api/events", json={**base, "starts_at": "15:00", "ends_at": "14:00"}).status_code == 422
    event = client.post("/api/events", json={**base, "starts_at": "15:00", "ends_at": "16:30"}).json()
    assert (event["starts_at"], event["ends_at"]) == ("15:00:00", "16:30:00")
    assert client.patch(f"/api/events/{event['id']}", json={"starts_at": None}).status_code == 422
    event = client.patch(f"/api/events/{event['id']}", json={"starts_at": None, "ends_at": None}).json()
    assert event["ends_at"] is None
    assert client.get("/api/events").json()[0]["ends_at"] is None


def test_user_preferences_report_and_overview(client):
    me = client.get("/api/me").json()
    assert me["report_after_fill"] is False and me["overview_layout"] is None
    assert client.patch("/api/me", json={"report_after_fill": True}).json()["report_after_fill"] is True
    layout = [{"id": "events", "size": "full"}, {"id": "top_matches", "size": "half"}]
    assert client.patch("/api/me", json={"overview_layout": layout}).json()["overview_layout"] == layout
    assert client.patch("/api/me", json={"overview_layout": [{"id": "weather"}]}).status_code == 422
    assert client.patch("/api/me", json={"overview_layout": [{"id": "events"}, {"id": "events"}]}).status_code == 422
    assert client.patch("/api/me", json={"overview_layout": []}).json()["overview_layout"] == []
    assert client.patch("/api/me", json={"reset_overview": True}).json()["overview_layout"] is None


def test_ai_reads_link_and_file(client, monkeypatch):
    from app.services.webpage import FetchError

    monkeypatch.setattr(sources, "fetch_job_posting", lambda url: JOB_TEXT)
    app = create_with_ai(client, data={"url": "https://example.com/job/1"})
    assert app["source_url"] == "https://example.com/job/1"

    def blocked(url):
        raise FetchError("Il sito ha bloccato lo scaricamento automatico")
    monkeypatch.setattr(sources, "fetch_job_posting", blocked)
    r = client.post("/api/applications/ai", data={"url": "https://example.com/job/2"})
    assert r.status_code == 422 and "bloccato" in r.json()["detail"]

    assert client.post("/api/applications/ai", files={"file": ("a.png", b"xxx", "image/png")}).status_code == 422
    assert client.post("/api/applications/ai", data={"text": "corto"}).status_code == 422
    assert client.post("/api/applications/ai").status_code == 422
    # Only the first one was created
    assert len(client.get("/api/applications").json()) == 1


def test_cancel_jobs(client):
    # A new application not filled yet goes away with its job
    app = create_with_ai(client, data={"text": JOB_TEXT})
    [job] = client.get("/api/jobs").json()
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(f"/api/applications/{app['id']}").status_code == 404

    # A cancelled report goes back to the previous one
    client.patch("/api/profile", json={"skills": [{"name": "Python", "level": 3}]})
    skills = [{"name": "Python", "importance": "required"}]
    app_id = client.post("/api/applications", json={"title": "Dev", "skills": skills}).json()["id"]
    request_report(client, app_id)
    for job in client.get("/api/jobs").json():
        client.delete(f"/api/jobs/{job['id']}")
    assert client.post(f"/api/applications/{app_id}/report").status_code == 202
    assert client.post(f"/api/applications/{app_id}/report").status_code == 409
    assert client.get(f"/api/applications/{app_id}").json()["report_status"] == "pending"
    [job] = client.get("/api/jobs").json()
    client.delete(f"/api/jobs/{job['id']}")
    data = client.get(f"/api/applications/{app_id}").json()
    assert data["report_status"] == "done" and data["report"]["score"] == 100

    # Deleting an application removes its jobs
    request_report(client, app_id)
    client.delete(f"/api/applications/{app_id}")
    assert client.get("/api/jobs").json() == []


def test_failed_job_keeps_new_application_and_can_be_retried(client, monkeypatch):
    def offline(system, user, schema):
        raise LLMError("Ollama non risponde")
    monkeypatch.setattr(extraction, "generate_structured", offline)
    app = create_with_ai(client, data={"text": JOB_TEXT})
    run_jobs()
    [job] = client.get("/api/jobs").json()
    assert (job["status"], job["error"]) == ("failed", "Ollama non risponde")
    # The application stays, with its posting, to be filled in by hand or retried
    assert client.get(f"/api/applications/{app['id']}").json()["has_description"]
    assert client.post(f"/api/jobs/{job['id']}/apply").status_code == 409

    monkeypatch.setattr(extraction, "generate_structured", fake_llm)
    assert client.post(f"/api/jobs/{job['id']}/retry").json()["status"] == "pending"
    run_jobs()
    assert client.get(f"/api/applications/{app['id']}").json()["title"] == "Backend Developer"
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 409


def test_jobs_are_private_and_queued_for_everyone(client):
    create_with_ai(client, data={"text": JOB_TEXT})
    client.post("/api/users", json={"username": "anna", "email": "anna@example.com", "password": "Password123",
                                    "role": "user", "language": "it"})
    other = TestClient(app)
    other.post("/api/auth/login", json={"username": "anna", "password": "Password123"})
    create_with_ai(other, data={"text": JOB_TEXT})
    [mine] = client.get("/api/jobs").json()
    [theirs] = other.get("/api/jobs").json()
    # One queue for everyone: the second job waits for the first
    assert (mine["position"], theirs["position"]) == (1, 2)
    assert other.delete(f"/api/jobs/{mine['id']}").status_code == 404


def test_llm_disabled_blocks_ai_features(client):
    assert client.get("/api/settings").json()["llm_enabled"] is True
    assert client.patch("/api/settings", json={"llm_enabled": False}).json()["llm_enabled"] is False
    health = client.get("/api/health").json()
    assert health["llm"] == {"enabled": False, "hardware": None}
    assert (health["version"], health["build"]) == ("2.0", "20261102.1943")

    r = client.post("/api/applications/ai", data={"text": JOB_TEXT})
    assert r.status_code == 409 and "disattivate" in r.json()["detail"]
    app_id = client.post("/api/applications", json={"title": "Manuale"}).json()["id"]
    assert client.post(f"/api/applications/{app_id}/report").status_code == 409
    assert client.post(f"/api/applications/{app_id}/fill").status_code == 409
    assert client.post("/api/profile/fill").status_code == 409


def test_turning_ai_off_drops_waiting_jobs(client):
    app = create_with_ai(client, data={"text": JOB_TEXT})
    client.patch("/api/settings", json={"llm_enabled": False})
    assert client.get("/api/jobs").json() == []
    # The new application stays, with its posting, to be filled in by hand
    assert client.get(f"/api/applications/{app['id']}").json()["has_description"]


def test_cv_upload_ai_fill_and_match(client):
    doc = Document()
    doc.add_paragraph("Ivan Rossi - Software engineer. Python, PostgreSQL, Docker Compose.")
    doc.add_paragraph("ivan.rossi@example.com · +39 333 123 4567 · github.com/ivanrossi · 2018 - 2023")
    buf = io.BytesIO()
    doc.save(buf)
    r = client.post("/api/profile/cv", files={"file": ("cv.docx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["cv_filename"] == "cv.docx"
    # Uploading alone fills nothing in
    assert r.json()["full_name"] is None

    client.patch("/api/profile", json={"full_name": "Ivan R."})
    assert client.post("/api/profile/fill").status_code == 202
    assert client.post("/api/profile/fill").status_code == 409
    run_jobs()
    fields = client.get("/api/profile").json()
    # A field already filled is only proposed
    assert fields["full_name"] == "Ivan R."
    [job] = client.get("/api/jobs").json()
    assert (job["kind"], job["proposal"]) == ("profile", {"full_name": "Ivan Rossi"})
    client.post(f"/api/jobs/{job['id']}/apply")
    fields = client.get("/api/profile").json()
    assert fields["full_name"] == "Ivan Rossi"
    assert fields["email"] == "ivan.rossi@example.com"
    assert fields["phone"] == "+39 333 123 4567"
    assert fields["links"] == [{"label": "GitHub", "url": "https://github.com/ivanrossi"}]
    assert fields["certifications"] == []
    assert fields["years_of_experience"] == 3.0  # 2020-01..2022-12, overlap counted once
    # Duplicates removed (highest level kept), levels clamped to 1-4
    assert {s["name"].lower(): s["level"] for s in fields["skills"]}["python"] == 4

    app_id = create_with_ai(client, data={"text": JOB_TEXT})["id"]
    run_jobs()
    # No report until it is requested
    assert client.get(f"/api/applications/{app_id}").json()["report"] is None
    request_report(client, app_id)
    data = client.get(f"/api/applications/{app_id}").json()
    assert data["report_status"] == "done" and data["report_stale"] is False
    result = data["report"]
    by_skill = {s["skill"]: s for s in result["skills"]}
    assert {k for k, s in by_skill.items() if s["status"] == "match"} == {"Python", "Postgres", "Docker"}
    assert by_skill["Kubernetes"]["status"] == "missing"
    # Cited skills are the profile's own names
    assert by_skill["Docker"]["matched_with"] == "Docker Compose" and by_skill["Python"]["level"] == 4
    assert result["score"] == 86  # 6 of 7 points
    assert result["improvements"][0]["skill"] == "Kubernetes" and result["summary"]
    assert {a["id"]: a["match_score"] for a in client.get("/api/applications").json()} == {app_id: 86}


def test_ai_cv_requires_upload(client):
    assert client.post("/api/profile/fill").status_code == 409


def test_skill_level_affects_match(client):
    client.patch("/api/profile", json={"skills": [{"name": "Python", "level": 1},
                                                  {"name": "Docker Compose", "level": 2}]})
    skills = [{"name": n, "importance": "required"} for n in ("Python", "Docker")]
    app_id = client.post("/api/applications", json={"title": "Dev", "skills": skills}).json()["id"]
    request_report(client, app_id)
    skills = {s["skill"]: s for s in client.get(f"/api/applications/{app_id}").json()["report"]["skills"]}
    assert skills["Python"]["status"] == "partial" and "base" in skills["Python"]["note"]
    assert skills["Docker"]["status"] == "match"

    client.patch(f"/api/applications/{app_id}", json={"seniority": "Senior"})
    request_report(client, app_id)
    skills = client.get(f"/api/applications/{app_id}").json()["report"]["skills"]
    assert {s["status"] for s in skills} == {"partial"}


def test_report_soft_skills_languages_and_unknown_citations(client):
    client.patch("/api/profile", json={"skills": [{"name": "PyTorch", "level": 3}],
                                       "languages": [{"language": "Inglese", "level": "C1"}]})
    skills = [{"name": n, "importance": "required"} for n in ("Machine Learning", "English", "Teamwork", "Rust")]
    app_id = client.post("/api/applications", json={"title": "ML", "skills": skills}).json()["id"]
    request_report(client, app_id)
    result = client.get(f"/api/applications/{app_id}").json()["report"]
    by_skill = {s["skill"]: s for s in result["skills"]}
    assert (by_skill["English"]["kind"], by_skill["English"]["matched_with"]) == ("language", "Inglese")
    assert by_skill["Teamwork"]["kind"] == "soft"
    # A profile skill the model made up is not shown
    assert by_skill["Rust"]["matched_with"] is None
    # Soft skills don't count: ML and English match, Rust partial -> 2.5 of 3
    assert result["score"] == 83


def test_report_goes_stale_and_is_cleared_without_ai(client):
    client.patch("/api/profile", json={"skills": [{"name": "Python", "level": 3}], "phone": "1"})
    skills = [{"name": "Python", "importance": "required"}]
    app_id = client.post("/api/applications", json={"title": "Dev", "skills": skills}).json()["id"]
    other_id = client.post("/api/applications", json={"title": "Altro"}).json()["id"]
    request_report(client, app_id)
    stale = lambda i: client.get(f"/api/applications/{i}").json()["report_stale"]  # noqa: E731

    # Changes that don't touch skills leave the report as it is
    client.patch("/api/profile", json={"phone": "2"})
    client.patch(f"/api/applications/{app_id}", json={"notes": "x"})
    assert stale(app_id) is False

    client.patch("/api/profile", json={"skills": [{"name": "Python", "level": 4}]})
    assert stale(app_id) is True and stale(other_id) is False
    request_report(client, app_id)
    assert stale(app_id) is False
    client.patch(f"/api/applications/{app_id}", json={"requirements": ["Laurea"]})
    assert stale(app_id) is True

    client.patch("/api/settings", json={"llm_enabled": False})
    data = client.get(f"/api/applications/{app_id}").json()
    assert (data["report"], data["report_status"], data["report_stale"]) == (None, None, False)


def test_profile_sections_editable(client):
    payload = {
        "certifications": [{"name": "AWS Certified Developer", "issuer": "Amazon", "issued_on": "2025-03"}],
        "projects": [{"name": "Roboverse", "context": "accademico", "technologies": ["ROS 2"]}],
        "languages": [{"language": "Inglese", "level": "B2"}],
    }
    profile = client.patch("/api/profile", json=payload).json()
    assert profile["certifications"][0]["issuer"] == "Amazon"
    assert profile["projects"][0]["technologies"] == ["ROS 2"]
    profile = client.patch("/api/profile", json={"certifications": []}).json()
    assert profile["certifications"] == [] and profile["projects"]


def test_settings_and_language(client):
    settings = client.get("/api/settings").json()
    assert (settings["llm_enabled"], settings["llm_accelerator"], settings["password_min_length"]) == (True, "auto", 10)
    assert "secret_key" not in settings
    assert client.patch("/api/settings", json={"llm_accelerator": "vulkan"}).json()["llm_accelerator"] == "vulkan"
    assert client.patch("/api/settings", json={"llm_accelerator": "tpu"}).status_code == 422
    assert client.patch("/api/settings", json={"session_hours": 0}).status_code == 422

    me = client.get("/api/me").json()
    assert (me["language"], me["theme"], me["onboarded"]) == ("it", "system", False)
    me = client.patch("/api/me", json={"language": "en", "theme": "dark", "onboarded": True}).json()
    assert (me["language"], me["theme"], me["onboarded"]) == ("en", "dark", True)
    assert client.patch("/api/me", json={"theme": "blue"}).status_code == 422
    assert me["application_sort"] == "applied"
    assert client.patch("/api/me", json={"application_sort": "event"}).json()["application_sort"] == "event"
    assert client.patch("/api/me", json={"application_sort": "salary"}).status_code == 422
    assert me["application_filter"] == "all"
    assert client.patch("/api/me", json={"application_filter": "interview"}).json()["application_filter"] == "interview"
    assert client.patch("/api/me", json={"application_filter": "all"}).json()["application_filter"] == "all"
    assert client.patch("/api/me", json={"application_filter": "draft"}).status_code == 422

    # Messages follow the interface language
    assert client.get("/api/applications/999", headers={"Accept-Language": "en"}).json()["detail"] == "Application not found"
    assert client.get("/api/applications/999", headers={"Accept-Language": "it-IT,it;q=0.9"}).json()["detail"] == \
        "Candidatura non trovata"


def test_status_change_stored_as_codes(client):
    app_id = client.post("/api/applications", json={"title": "Dev"}).json()["id"]
    events = client.patch(f"/api/applications/{app_id}", json={"status": "offer"}).json()["events"]
    assert events[0]["title"] == "applied>offer"


def test_scheduled_events(client):
    app_id = client.post("/api/applications", json={"title": "Backend Developer", "company": "ACME"}).json()["id"]
    client.patch(f"/api/applications/{app_id}", json={"status": "interview"})
    assert client.post("/api/events", json={"application_id": 999, "occurred_on": "2099-10-20", "title": "x"}).status_code == 404

    event = client.post("/api/events", json={"application_id": app_id, "type": "interview", "occurred_on": "2099-10-20",
                                             "starts_at": "15:30", "title": "Colloquio tecnico", "details": "Con il CTO"}).json()
    assert (event["completed"], event["starts_at"]) == (False, "15:30:00")
    client.post("/api/events", json={"application_id": app_id, "type": "follow_up", "occurred_on": "2099-10-18",
                                     "title": "Scrivere al recruiter"})

    # The agenda excludes status changes and includes the application
    agenda = client.get("/api/events").json()
    assert [e["title"] for e in agenda] == ["Scrivere al recruiter", "Colloquio tecnico"]
    assert (agenda[0]["application_title"], agenda[0]["application_company"]) == ("Backend Developer", "ACME")

    updated = client.patch(f"/api/events/{event['id']}", json={"completed": True, "details": "Andato bene"}).json()
    assert (updated["completed"], updated["details"], updated["title"]) == (True, "Andato bene", "Colloquio tecnico")
    assert client.patch(f"/api/events/{event['id']}", json={"title": None}).status_code == 422

    assert client.delete(f"/api/events/{event['id']}").status_code == 204
    assert client.delete(f"/api/events/{event['id']}").status_code == 404
    assert len(client.get("/api/events").json()) == 1
    # Status changes have already happened
    status_change = client.get(f"/api/applications/{app_id}").json()["events"][0]
    assert (status_change["type"], status_change["completed"]) == ("status_change", True)


def test_project_technologies_become_skills(client):
    client.patch("/api/profile", json={"skills": [{"name": "Python", "level": 3}]})
    profile = client.patch("/api/profile", json={"projects": [
        {"name": "Assistente", "technologies": ["Large Language Models", "python", " "]},
    ]}).json()
    # Existing skills (case-insensitive) aren't repeated; new ones come without a level
    assert [(s["name"], s["level"]) for s in profile["skills"]] == [("Python", 3), ("Large Language Models", None)]
    assert profile["skills"][1]["evidence"] == "Progetto Assistente"

    # Level stays empty until the user sets it
    skills = [profile["skills"][0], {**profile["skills"][1], "level": 2}]
    assert client.patch("/api/profile", json={"skills": skills}).json()["skills"][1]["level"] == 2


def test_profile_open_adds_missing_project_skills(client):
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Profile

    client.get("/api/profile")
    with Session(engine) as session:
        profile = session.exec(select(Profile)).one()
        profile.projects = [{"name": "Vecchio", "technologies": ["ROS 2"]}]
        session.add(profile)
        session.commit()
    assert [s["name"] for s in client.get("/api/profile").json()["skills"]] == ["ROS 2"]


def test_experience_technologies_become_skills(client):
    profile = client.patch("/api/profile", json={"experiences": [
        {"role": "Robotics engineer", "company": "Acme", "technologies": ["ROS 2"]},
    ]}).json()
    assert profile["skills"] == [{"name": "ROS 2", "category": None, "level": None,
                                  "evidence": "Esperienza Robotics engineer · Acme"}]


def test_list_reports_last_event(client):
    first = client.post("/api/applications", json={"title": "A"}).json()["id"]
    second = client.post("/api/applications", json={"title": "B"}).json()["id"]
    for day in ("2026-03-01", "2026-05-10"):
        client.post("/api/events", json={"application_id": first, "type": "interview", "occurred_on": day, "title": "x"})
    # Status changes don't count as events
    client.patch(f"/api/applications/{second}", json={"status": "inactive"})
    last = {a["id"]: a["last_event_on"] for a in client.get("/api/applications").json()}
    assert last == {first: "2026-05-10", second: None}


def test_bulk_status_and_delete(client):
    ids = [client.post("/api/applications", json={"title": f"Job {i}"}).json()["id"] for i in range(3)]

    r = client.post("/api/applications/bulk", json={"ids": ids[:2], "action": "status", "status": "interview"})
    assert r.status_code == 204
    statuses = {a["id"]: a["status"] for a in client.get("/api/applications").json()}
    assert statuses == {ids[0]: "interview", ids[1]: "interview", ids[2]: "applied"}
    events = client.get(f"/api/applications/{ids[0]}").json()["events"]
    assert [(e["type"], e["title"]) for e in events] == [("status_change", "applied>interview")]

    # Same status again: no new history entry
    client.post("/api/applications/bulk", json={"ids": [ids[0]], "action": "status", "status": "interview"})
    assert len(client.get(f"/api/applications/{ids[0]}").json()["events"]) == 1

    assert client.post("/api/applications/bulk", json={"ids": ids, "action": "status"}).status_code == 422
    assert client.post("/api/applications/bulk", json={"ids": [], "action": "delete"}).status_code == 422

    # An unknown id fails the whole request
    assert client.post("/api/applications/bulk", json={"ids": [ids[0], 999999], "action": "delete"}).status_code == 404
    assert len(client.get("/api/applications").json()) == 3

    assert client.post("/api/applications/bulk", json={"ids": ids[:2], "action": "delete"}).status_code == 204
    assert [a["id"] for a in client.get("/api/applications").json()] == [ids[2]]


def test_bulk_ignores_other_users_applications(client):
    other_id = client.post("/api/applications", json={"title": "Admin job"}).json()["id"]
    assert client.post("/api/users", json={"username": "mario", "email": "m@example.com",
                                           "password": "Segreta1234"}).status_code == 201
    mario = TestClient(app)
    assert mario.post("/api/auth/login", json={"username": "mario", "password": "Segreta1234"}).status_code == 200
    assert mario.post("/api/applications/bulk", json={"ids": [other_id], "action": "delete"}).status_code == 404
    assert len(client.get("/api/applications").json()) == 1


def test_attachments(client, tmp_path):
    app_id = client.post("/api/applications", json={"title": "Con allegati"}).json()["id"]
    r = client.post(f"/api/applications/{app_id}/attachments", files=[
        ("files", ("lettera.pdf", b"%PDF-1.4 lettera", "application/pdf")),
        ("files", ("../note.html", b"<script>alert(1)</script>", "text/html")),
    ])
    assert r.status_code == 201
    attachments = r.json()["attachments"]
    assert [(a["filename"], a["size"]) for a in attachments] == [("lettera.pdf", 16), ("note.html", 25)]
    assert client.get(f"/api/applications/{app_id}").json()["attachments"] == attachments

    # Downloads keep the original name and are never rendered inline
    r = client.get(f"/api/applications/{app_id}/attachments/{attachments[1]['id']}")
    assert r.content == b"<script>alert(1)</script>"
    assert r.headers["content-type"] == "application/octet-stream"
    assert 'attachment; filename="note.html"' in r.headers["content-disposition"]

    folder = next(tmp_path.glob(f"user_*/applications/{app_id}"))
    assert len(list(folder.iterdir())) == 2
    r = client.delete(f"/api/applications/{app_id}/attachments/{attachments[0]['id']}")
    assert [a["filename"] for a in r.json()["attachments"]] == ["note.html"]
    assert len(list(folder.iterdir())) == 1
    assert client.get(f"/api/applications/{app_id}/attachments/{attachments[0]['id']}").status_code == 404

    # Deleting the application deletes its files
    assert client.delete(f"/api/applications/{app_id}").status_code == 204
    assert not folder.exists()


def test_attachments_rejected(client):
    app_id = client.post("/api/applications", json={"title": "x"}).json()["id"]
    r = client.post(f"/api/applications/{app_id}/attachments", files=[
        ("files", ("ok.txt", b"ok", "text/plain")), ("files", ("vuoto.txt", b"", "text/plain"))])
    assert r.status_code == 422
    # Nothing is stored when one of the files is rejected
    assert client.get(f"/api/applications/{app_id}").json()["attachments"] == []

    client.post("/api/users", json={"username": "mario", "email": "m@example.com", "password": "Segreta1234"})
    mario = TestClient(app)
    mario.post("/api/auth/login", json={"username": "mario", "password": "Segreta1234"})
    r = mario.post(f"/api/applications/{app_id}/attachments", files=[("files", ("a.txt", b"a", "text/plain"))])
    assert r.status_code == 404


def test_bulk_delete_removes_attachments(client, tmp_path):
    ids = [client.post("/api/applications", json={"title": f"A{i}"}).json()["id"] for i in range(2)]
    for app_id in ids:
        client.post(f"/api/applications/{app_id}/attachments", files=[("files", ("cv.pdf", b"cv", "application/pdf"))])
    assert len(list(tmp_path.glob("user_*/applications/*"))) == 2
    client.post("/api/applications/bulk", json={"ids": ids, "action": "delete"})
    assert list(tmp_path.glob("user_*/applications/*")) == []

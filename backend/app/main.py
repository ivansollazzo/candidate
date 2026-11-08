import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app import __build__, __version__
from app.core.config import get_settings
from app.core.i18n import LanguageMiddleware, t
from app.features.applications import events_router
from app.features.applications import router as applications
from app.features.applications import service as applications_service
from app.features.applications.jobs import ApplicationFill
from app.features.auth import router as auth
from app.features.auth import service as security
from app.features.background_jobs import router as jobs
from app.features.background_jobs import service as job_queue
from app.features.background_jobs import worker
from app.features.background_jobs.models import JobKind
from app.features.backups import router as backups
from app.features.https import router as https
from app.features.https import service as https_service
from app.features.profile import router as profile
from app.features.profile import service as profile_service
from app.features.profile.jobs import ProfileFill
from app.features.reports import router as reports
from app.features.reports import service as reports_service
from app.features.reports.jobs import ReportGeneration
from app.features.settings import router as settings
from app.features.settings import service as app_settings
from app.features.updates import router as updates
from app.features.users import router as users
from app.shared import maintenance
from app.shared.database import engine
from app.shared.llm import check_llm, hardware_support

logging.basicConfig(level=logging.INFO)


def wire() -> None:
    """Connects features that react to each other without importing each other."""
    job_queue.register(JobKind.APPLICATION, ApplicationFill())
    job_queue.register(JobKind.PROFILE, ProfileFill())
    job_queue.register(JobKind.REPORT, ReportGeneration())
    profile_service.on_skills_changed(reports_service.mark_stale)
    applications_service.on_position_changed(reports_service.mark_application_stale)
    applications_service.on_filled(reports_service.queue_after_fill)
    app_settings.on_ai_disabled(job_queue.cancel_all)
    app_settings.on_ai_disabled(reports_service.clear_all)


wire()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tell the llm service whether to start the model, per the last saved setting
    with Session(engine) as session:
        app_settings.publish(app_settings.ensure(session))
    worker.start()
    https_service.start()
    yield
    https_service.stop()
    worker.stop()


app = FastAPI(title="Candidate", description="Gestione delle candidature lavorative", version=__version__,
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Requests served at once. A request can hold a database connection while it waits for a worker thread, and its
# connection goes back to the pool only on a worker thread: with more requests in flight than connections, threads
# and connections end up waiting for each other and the app stops answering. Further requests wait here instead,
# without a connection (the pool in app.shared.database has room for all of these).
MAX_IN_FLIGHT = 30
_in_flight = asyncio.Semaphore(MAX_IN_FLIGHT)


@app.middleware("http")
async def limit_in_flight(request: Request, call_next):
    # The health check (updater) and the web server's HTTPS sync answer also when the app is busy
    if request.url.path == "/api/health" or request.url.path.startswith("/api/internal/"):
        return await call_next(request)
    async with _in_flight:
        return await call_next(request)


@app.middleware("http")
async def maintenance_mode(request: Request, call_next):
    """While a backup is restored the database is being replaced: only the health check answers."""
    if maintenance.restoring() and request.url.path != "/api/health":
        return JSONResponse({"detail": t("restoring"), "code": "restoring"}, status_code=503)
    return await call_next(request)


@app.middleware("http")
async def https_flag(request: Request, call_next):
    """Session cookies are marked Secure when the page was opened over HTTPS."""
    token = security.secure_request.set(https.is_secure(request))
    try:
        return await call_next(request)
    finally:
        security.secure_request.reset(token)


# Added last, so it runs first: the maintenance message is in the user's language
app.add_middleware(LanguageMiddleware)

app.include_router(auth.router)
app.include_router(auth.me_router)
app.include_router(users.me_router)
app.include_router(users.router)
app.include_router(applications.router)
app.include_router(reports.router)
app.include_router(events_router.router)
app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(settings.router)
app.include_router(updates.router)
app.include_router(backups.router)
app.include_router(https.router)
app.include_router(https.internal)


@app.get("/api/health")
def health():
    if maintenance.restoring():
        return {"status": "restoring", "version": __version__, "build": __build__, "llm": None}
    with Session(engine) as session:
        enabled = app_settings.load(session).llm_enabled
    llm = {"enabled": enabled, **(check_llm() if enabled else {}), "hardware": hardware_support()}
    return {"status": "ok", "version": __version__, "build": __build__, "llm": llm}

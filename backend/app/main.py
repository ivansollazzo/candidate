import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app import __build__, __version__
from app.api import ai, applications, auth, events, me, profile, settings, updates, users
from app.config import get_settings
from app.db import engine
from app.i18n import LanguageMiddleware
from app.services import app_settings
from app.services.llm import check_llm, hardware_support

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tell the llm service whether to start the model, per the last saved setting
    with Session(engine) as session:
        app_settings.publish(app_settings.load(session))
    yield


app = FastAPI(title="Candidate", description="Gestione delle candidature lavorative", version=__version__,
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(LanguageMiddleware)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(users.router)
app.include_router(applications.router)
app.include_router(events.router)
app.include_router(profile.router)
app.include_router(ai.router)
app.include_router(settings.router)
app.include_router(updates.router)


@app.get("/api/health")
def health():
    with Session(engine) as session:
        enabled = app_settings.load(session).llm_enabled
    llm = {"enabled": enabled, **(check_llm() if enabled else {}), "hardware": hardware_support()}
    return {"status": "ok", "version": __version__, "build": __build__, "llm": llm}

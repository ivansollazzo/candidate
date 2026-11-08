from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session
from starlette.requests import ClientDisconnect

from app.core.i18n import t
from app.models import AppSettings
from app.schemas import HttpsRead, HttpsUpdate
from app.services import app_settings, https, security
from app.shared.database import get_session

router = APIRouter(prefix="/api/https", tags=["https"])
# Reached by the frontend container on the Compose network; Caddy doesn't forward /api/internal
internal = APIRouter(prefix="/api/internal/https", include_in_schema=False)

MAX_PEM_BYTES = 256 * 1024


def is_secure(request: Request) -> bool:
    # Set by Caddy, which replaces whatever the browser sent
    return request.headers.get("x-forwarded-proto") == "https"


def read(settings: AppSettings, session: Session, request: Request) -> dict:
    served = https.served_names(settings.https_certs)
    certificates = [{**https.cert_info(pair["cert"]).__dict__, "hosts": names}
                    for pair, names in zip(settings.https_certs, served, strict=True)]
    authority = None
    if settings.https_ca:
        ca = https.cert_info(settings.https_ca["cert"])
        leaf = https.cert_info(settings.https_leaf["cert"]) if settings.https_leaf else None
        authority = {"name": ca.issuer, "fingerprint": ca.fingerprint, "not_after": ca.not_after,
                     "leaf_not_after": leaf.not_after if leaf else None}
    return {"mode": settings.https_mode, "hosts": settings.https_hosts, "certificates": certificates,
            "authority": authority, **https.state(session), "secure_request": is_secure(request),
            "port": https.PORT}


def _save(session: Session, settings: AppSettings, was_on: bool) -> None:
    https.ensure_internal(settings)
    if was_on != (https.bundle(settings)[0] != "off"):
        # The protocol changes: every session ends, everyone signs in again on the new address
        security.end_all_sessions(settings)
    session.add(settings)
    session.commit()
    session.refresh(settings)


def _is_on(settings: AppSettings) -> bool:
    return https.bundle(settings)[0] != "off"


@router.get("", response_model=HttpsRead, dependencies=[Depends(security.admin_user)])
def get_https(request: Request, session: Session = Depends(get_session)):
    return read(app_settings.load(session), session, request)


@router.put("", response_model=HttpsRead, dependencies=[Depends(security.admin_user)])
def update_https(payload: HttpsUpdate, request: Request, session: Session = Depends(get_session)):
    """Mode, and the hosts of internal mode (custom mode serves the names of its certificates). Caddy picks up
    the new configuration within a few seconds. Turning HTTPS on or off ends every session."""
    settings = app_settings.load(session)
    was_on = _is_on(settings)
    if payload.mode == "internal":
        hosts = https.normalize_hosts(payload.hosts)
        if not hosts:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_no_hosts"))
        settings.https_hosts = hosts
    if payload.mode == "custom" and not settings.https_certs:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_no_certs"))
    settings.https_mode = payload.mode
    _save(session, settings, was_on)
    return read(settings, session, request)


async def _pem(upload: UploadFile) -> str:
    data = await upload.read(MAX_PEM_BYTES + 1)
    if len(data) > MAX_PEM_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, t("file_too_large", mb=0.25))
    return data.decode("utf-8", errors="replace")


@router.post("/certificates", response_model=HttpsRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(security.admin_user)])
async def upload_certificate(
    request: Request, certificate: UploadFile = File(...), key: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """A certificate (PEM, with its intermediate certificates) and its private key, for custom mode. A
    certificate for the same names replaces the old one."""
    cert_pem, key_pem, info = https.check_pair(await _pem(certificate), await _pem(key))
    settings = app_settings.load(session)
    was_on = _is_on(settings)
    certs = [c for c in settings.https_certs if sorted(https.cert_info(c["cert"]).names) != sorted(info.names)]
    if len(certs) >= https.MAX_CERTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_too_many_certs", count=https.MAX_CERTS))
    # The newest one comes first, so it is the one used for a name two certificates hold
    settings.https_certs = [{"cert": cert_pem, "key": key_pem}, *certs]
    _save(session, settings, was_on)
    return read(settings, session, request)


@router.delete("/certificates/{certificate_id}", response_model=HttpsRead,
               dependencies=[Depends(security.admin_user)])
def delete_certificate(certificate_id: str, request: Request, session: Session = Depends(get_session)):
    settings = app_settings.load(session)
    certs = [c for c in settings.https_certs if https.cert_info(c["cert"]).id != certificate_id]
    if len(certs) == len(settings.https_certs):
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("https_cert_not_found"))
    if settings.https_mode == "custom" and not certs:
        raise HTTPException(status.HTTP_409_CONFLICT, t("https_last_cert"))
    was_on = _is_on(settings)
    settings.https_certs = certs
    _save(session, settings, was_on)
    return read(settings, session, request)


@router.get("/authority/certificate")
def download_authority(session: Session = Depends(get_session)):
    """Certificate of the internal authority, to install on the devices that open the app. Public: it holds no
    secret, and a device may need it before anyone can sign in from it."""
    settings = app_settings.load(session)
    if not settings.https_ca:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("https_no_authority"))
    return Response(settings.https_ca["cert"], media_type="application/x-x509-ca-cert",
                    headers={"Content-Disposition": 'attachment; filename="candidate-root-ca.crt"'})


@internal.get("/config", response_class=PlainTextResponse)
def wanted_config(session: Session = Depends(get_session)):
    """Name of the configuration Caddy should use: "off" (plain HTTP) or a hash of the HTTPS one."""
    return https.wanted(session)


@internal.get("/config/{name}")
def get_config(name: str, session: Session = Depends(get_session)):
    """Archive of the wanted configuration (Caddyfile and certificates); 404 if the settings changed since."""
    wanted, archive = https.bundle(app_settings.load(session))
    if archive is None or wanted != name:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return Response(archive, media_type="application/gzip")


@internal.post("/reports", status_code=status.HTTP_204_NO_CONTENT)
async def add_report(request: Request, applied: str = "off", failed: str = ""):
    """The frontend container reports the configuration in use and the one Caddy refused, with the error as
    the body (a POST: the container's wget knows no other method with a body)."""
    try:
        error = (await request.body()).decode("utf-8", errors="replace")
    except ClientDisconnect:
        return  # the container gave up waiting: it reports again in a few seconds
    https.record(applied, failed, error)

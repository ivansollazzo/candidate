from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session

from app.db import get_session
from app.i18n import t
from app.models import AppSettings
from app.schemas import HttpsRead, HttpsUpdate
from app.services import app_settings, https, security

router = APIRouter(prefix="/api/https", tags=["https"])
# Reached by the frontend container on the Compose network; Caddy doesn't forward /api/internal
internal = APIRouter(prefix="/api/internal/https", include_in_schema=False)

MAX_PEM_BYTES = 256 * 1024


def is_secure(request: Request) -> bool:
    # Set by Caddy, which replaces whatever the browser sent
    return request.headers.get("x-forwarded-proto") == "https"


def read(settings: AppSettings, session: Session, request: Request) -> dict:
    used: set[str] = set()
    certificates = []
    for pair in settings.https_certs:
        info = https.cert_info(pair["cert"])
        hosts = [h for h in settings.https_hosts if h not in used and https.covers(info.names, h)]
        used.update(hosts)
        certificates.append({**info.__dict__, "hosts": hosts})
    authority = None
    if settings.https_ca:
        ca = https.cert_info(settings.https_ca["cert"])
        leaf = https.cert_info(settings.https_leaf["cert"]) if settings.https_leaf else None
        authority = {"name": ca.issuer, "fingerprint": ca.fingerprint, "not_after": ca.not_after,
                     "leaf_not_after": leaf.not_after if leaf else None}
    return {"mode": settings.https_mode, "hosts": settings.https_hosts, "certificates": certificates,
            "authority": authority, **https.state(session), "secure_request": is_secure(request),
            "port": https.PORT}


def _save(session: Session, settings: AppSettings) -> None:
    https.ensure_internal(settings)
    session.add(settings)
    session.commit()
    session.refresh(settings)


@router.get("", response_model=HttpsRead, dependencies=[Depends(security.admin_user)])
def get_https(request: Request, session: Session = Depends(get_session)):
    return read(app_settings.load(session), session, request)


@router.put("", response_model=HttpsRead, dependencies=[Depends(security.admin_user)])
def update_https(payload: HttpsUpdate, request: Request, session: Session = Depends(get_session)):
    """Mode and hosts. Caddy picks up the new configuration within a few seconds."""
    settings = app_settings.load(session)
    hosts = https.normalize_hosts(payload.hosts)
    if payload.mode != "off" and not hosts:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_no_hosts"))
    if payload.mode == "custom" and (missing := https.uncovered(hosts, settings.https_certs)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_uncovered", hosts=", ".join(missing)))
    settings.https_mode, settings.https_hosts = payload.mode, hosts
    _save(session, settings)
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
    certs = [c for c in settings.https_certs if sorted(https.cert_info(c["cert"]).names) != sorted(info.names)]
    if len(certs) >= https.MAX_CERTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_too_many_certs", count=https.MAX_CERTS))
    # The newest one comes first, so it is the one used for the hosts it covers
    settings.https_certs = [{"cert": cert_pem, "key": key_pem}, *certs]
    _save(session, settings)
    return read(settings, session, request)


@router.delete("/certificates/{index}", response_model=HttpsRead, dependencies=[Depends(security.admin_user)])
def delete_certificate(index: int, request: Request, session: Session = Depends(get_session)):
    settings = app_settings.load(session)
    if not 0 <= index < len(settings.https_certs):
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("https_cert_not_found"))
    certs = [c for i, c in enumerate(settings.https_certs) if i != index]
    if settings.https_mode == "custom" and (missing := https.uncovered(settings.https_hosts, certs)):
        raise HTTPException(status.HTTP_409_CONFLICT, t("https_cert_in_use", hosts=", ".join(missing)))
    settings.https_certs = certs
    _save(session, settings)
    return read(settings, session, request)


@router.get("/root-ca.crt")
def download_authority(session: Session = Depends(get_session)):
    """Certificate of the internal authority, to install on the devices that open the app. Public: it holds no
    secret, and a device may need it before anyone can sign in from it."""
    settings = app_settings.load(session)
    if not settings.https_ca:
        raise HTTPException(status.HTTP_404_NOT_FOUND, t("https_no_authority"))
    return Response(settings.https_ca["cert"], media_type="application/x-x509-ca-cert",
                    headers={"Content-Disposition": 'attachment; filename="candidate-root-ca.crt"'})


@internal.post("/sync", response_class=PlainTextResponse)
async def sync(request: Request, applied: str = "off", failed: str = "", session: Session = Depends(get_session)):
    """The frontend container reports the configuration in use (and the one Caddy refused, with the error in
    the body) and gets the name of the wanted one."""
    https.record(applied, failed, (await request.body()).decode("utf-8", errors="replace"))
    return https.wanted(session)


@internal.get("/bundle/{name}")
def get_bundle(name: str, session: Session = Depends(get_session)):
    """The archive of the wanted configuration; 404 if the settings changed since the name was given."""
    wanted, archive = https.bundle(app_settings.load(session))
    if archive is None or wanted != name:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return Response(archive, media_type="application/gzip")

"""HTTPS for the web app, set by the admin in Settings › Security › HTTPS and served by Caddy (frontend service).

The settings live in the database. From them the backend builds a Caddy configuration with its certificates
(the "bundle"); the frontend container asks for it every few seconds (frontend/https.sh), applies it with a
reload and reports back. A configuration Caddy refuses is not retried and the last working one stays in use,
so a wrong certificate never locks anyone out.

Modes:
- off: plain HTTP on port 5173, as before.
- internal: the app creates its own certificate authority once and a certificate for all the hosts listed;
  the authority's certificate is downloaded and installed on the devices that open the app.
- custom: certificates uploaded by the admin; each one is served for the names it holds (one name, several names
  or a wildcard). There is no list of hosts in this mode: the certificates are the list.
"""

import hashlib
import io
import ipaddress
import json
import logging
import re
import secrets
import tarfile
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi import HTTPException, status
from sqlmodel import Session

from app.core.i18n import t
from app.models import AppSettings
from app.services import app_settings
from app.shared.database import engine

log = logging.getLogger(__name__)

MODES = ("off", "internal", "custom")
MAX_HOSTS = 20
MAX_CERTS = 20
# Port of the web app inside the frontend container (published as 5173 by docker-compose.yml)
PORT = 5173
# Where the frontend container unpacks a bundle; its own files (site.caddy) are in /etc/caddy
BUNDLE_DIR = "/etc/caddy/https"
CA_YEARS = 10
# Certificates of the internal authority: browsers refuse longer lives, renewed this many days before expiry
LEAF_DAYS = 365
RENEW_DAYS = 30
# The frontend reports every 5 seconds: after this long without news its state is unknown
SEEN_SECONDS = 30
# How often the internal certificate's expiry is checked
CHECK_SECONDS = 12 * 3600

_HOST_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


# Hosts

def normalize_host(value: str) -> str:
    """A host name ("candidate.local", "*.example.com") or an IP address, lowercase. Raises ValueError."""
    host = value.strip().lower().rstrip(".")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    labels = host.split(".")
    if labels and labels[0] == "*":
        labels = labels[1:]
        if len(labels) < 2:
            raise ValueError(value)
    if not labels or len(host) > 253 or not all(_HOST_LABEL.match(label) for label in labels):
        raise ValueError(value)
    return host


def normalize_hosts(values: list[str]) -> list[str]:
    hosts, wrong = [], []
    for value in values:
        if not value.strip():
            continue
        try:
            host = normalize_host(value)
        except ValueError:
            wrong.append(value.strip())
            continue
        if host not in hosts:
            hosts.append(host)
    if wrong:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_bad_hosts", hosts=", ".join(wrong)))
    if len(hosts) > MAX_HOSTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_too_many_hosts", count=MAX_HOSTS))
    return hosts


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def site_address(host: str) -> str:
    return f"https://[{host}]:{PORT}" if ":" in host else f"https://{host}:{PORT}"


# Certificates

@dataclass
class CertInfo:
    id: str
    names: list[str]
    issuer: str
    not_before: datetime
    not_after: datetime
    fingerprint: str
    self_signed: bool


def _names(cert: x509.Certificate) -> list[str]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = [n.lower() for n in san.get_values_for_type(x509.DNSName)]
        names += [str(ip) for ip in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        names = []
    if not names:
        names = [a.value.lower() for a in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]
    return names


def _label(name: x509.Name) -> str:
    for oid in (NameOID.COMMON_NAME, NameOID.ORGANIZATION_NAME):
        if values := name.get_attributes_for_oid(oid):
            return str(values[0].value)
    return name.rfc4514_string()


def cert_info(pem: str) -> CertInfo:
    cert = x509.load_pem_x509_certificates(pem.encode())[0]
    return CertInfo(
        id=cert.fingerprint(hashes.SHA256()).hex()[:16], names=_names(cert), issuer=_label(cert.issuer), not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc, fingerprint=cert.fingerprint(hashes.SHA256()).hex(":").upper(),
        self_signed=cert.issuer == cert.subject,
    )


def check_pair(cert_pem: str, key_pem: str) -> tuple[str, str, CertInfo]:
    """Validate an uploaded certificate (with its chain) and private key; returns them as clean PEM."""
    try:
        chain = x509.load_pem_x509_certificates(cert_pem.encode())
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_bad_cert")) from None
    try:
        key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    except TypeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_key_encrypted")) from None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_bad_key")) from None
    raw = serialization.PublicFormat.SubjectPublicKeyInfo
    if key.public_key().public_bytes(serialization.Encoding.DER, raw) != \
            chain[0].public_key().public_bytes(serialization.Encoding.DER, raw):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_key_mismatch"))
    if chain[0].not_valid_after_utc <= datetime.now(UTC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_cert_expired"))
    if not site_names(_names(chain[0])):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, t("https_cert_no_names"))
    cert_out = "".join(c.public_bytes(serialization.Encoding.PEM).decode() for c in chain)
    key_out = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return cert_out, key_out, cert_info(cert_out)


def site_names(names: list[str]) -> list[str]:
    """The names of a certificate that can be served (a common name like "My server" can't)."""
    usable = []
    for name in names:
        try:
            host = normalize_host(name)
        except ValueError:
            continue
        if host not in usable:
            usable.append(host)
    return usable


def served_names(certs: list[dict]) -> list[list[str]]:
    """Custom mode: the names each certificate is served for; a name held by two goes to the first one."""
    taken: set[str] = set()
    result = []
    for pair in certs:
        names = [n for n in site_names(cert_info(pair["cert"]).names) if n not in taken]
        taken.update(names)
        result.append(names)
    return result


# Internal authority

def _key_pem(key) -> str:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def _new_ca() -> dict:
    key = ec.generate_private_key(ec.SECP256R1())
    # A random suffix tells apart the authorities of different installations on the same device
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"Candidate Local CA {secrets.token_hex(3).upper()}"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Candidate"),
    ])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365 * CA_YEARS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return {"cert": cert.public_bytes(serialization.Encoding.PEM).decode(), "key": _key_pem(key)}


def _new_leaf(ca: dict, hosts: list[str]) -> dict:
    ca_cert = x509.load_pem_x509_certificate(ca["cert"].encode())
    ca_key = serialization.load_pem_private_key(ca["key"].encode(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    names = [x509.IPAddress(ipaddress.ip_address(h)) if is_ip(h) else x509.DNSName(h) for h in hosts]
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
        .issuer_name(ca_cert.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=LEAF_DAYS))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=False, crl_sign=False,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return {"cert": pem + ca["cert"], "key": _key_pem(key), "hosts": hosts}


def ensure_internal(settings: AppSettings) -> bool:
    """Internal mode: create the authority if missing and (re)issue the certificate when the hosts changed or
    it is about to expire. True if something changed (not committed)."""
    if settings.https_mode != "internal" or not settings.https_hosts:
        return False
    changed = False
    if not settings.https_ca:
        settings.https_ca = _new_ca()
        changed = True
    leaf = settings.https_leaf
    if (changed or not leaf or leaf.get("hosts") != settings.https_hosts
            or not leaf["cert"].endswith(settings.https_ca["cert"])
            or cert_info(leaf["cert"]).not_after - datetime.now(UTC) < timedelta(days=RENEW_DAYS)):
        settings.https_leaf = _new_leaf(settings.https_ca, list(settings.https_hosts))
        changed = True
    return changed


def check_renewal() -> None:
    with Session(engine) as session:
        settings = app_settings.load(session)
        if ensure_internal(settings):
            log.info("Internal HTTPS certificate issued for %s", ", ".join(settings.https_hosts))
            session.add(settings)
            session.commit()


def _renewal_loop(stop: threading.Event) -> None:
    while not stop.wait(CHECK_SECONDS):
        try:
            check_renewal()
        except Exception:
            log.exception("Internal HTTPS certificate check failed")


_stop = threading.Event()


def start() -> None:
    try:
        check_renewal()
    except Exception:
        log.exception("Internal HTTPS certificate check failed")
    _stop.clear()
    threading.Thread(target=_renewal_loop, args=(_stop,), daemon=True, name="https-renewal").start()


def stop() -> None:
    _stop.set()


# Caddy configuration

def _caddyfile(settings: AppSettings) -> tuple[str, dict[str, str]]:
    """Caddyfile with "{dir}" where the bundle is unpacked, and the certificate files it loads."""
    if settings.https_mode == "internal":
        pairs, names = [settings.https_leaf], [list(settings.https_hosts)]
    else:
        pairs, names = settings.https_certs, served_names(settings.https_certs)
    files: dict[str, str] = {}
    sites: list[tuple[list[str], int]] = []
    for index, (pair, served) in enumerate(zip(pairs, names, strict=True)):
        if served:
            files[f"{index}.crt"], files[f"{index}.key"] = pair["cert"], pair["key"]
            sites.append((served, index))
    hosts = [h for served, _ in sites for h in served if not h.startswith("*.")]
    hosts = hosts or [sites[0][0][0].replace("*", "www", 1)]
    # Without SNI (an address typed as an IP) Caddy picks the certificate of this name
    default_sni = next((h for h in hosts if is_ip(h)), hosts[0])
    lines = [
        "# Written by Candidate from Settings › Security › HTTPS: changes made here are lost",
        "{",
        "\tadmin localhost:2019",
        "\tauto_https off",
        f"\tdefault_sni {default_sni}",
        f"\tservers :{PORT} {{",
        "\t\t# A plain HTTP request on the HTTPS port is redirected to HTTPS, temporarily: a permanent redirect",
        "\t\t# stays in the browsers and would send them to HTTPS also after it is turned off (frontend/caddy)",
        "\t\tlistener_wrappers {",
        "\t\t\tcandidate_redirect",
        "\t\t\ttls",
        "\t\t}",
        "\t}",
        "}",
        "",
    ]
    for served, index in sites:
        lines += [
            ", ".join(site_address(h) for h in served) + " {",
            f"\ttls {{dir}}/{index}.crt {{dir}}/{index}.key",
            "\timport /etc/caddy/site.caddy",
            "}",
            "",
        ]
    lines += [
        "# Plain HTTP inside the Compose network, for the updater's checks (not published)",
        "http://:8080 {",
        "\timport /etc/caddy/site.caddy",
        "}",
        "",
    ]
    return "\n".join(lines), files


def bundle(settings: AppSettings) -> tuple[str, bytes | None]:
    """Name of the wanted configuration ("off" for plain HTTP) and, for HTTPS, the archive with Caddyfile and
    certificates. The name is a hash of the content, so it changes whenever the configuration does."""
    if settings.https_mode == "off" or (settings.https_mode == "internal" and not settings.https_hosts):
        return "off", None
    if settings.https_mode == "internal" and not settings.https_leaf:
        return "off", None
    if settings.https_mode == "custom" and not any(served_names(settings.https_certs)):
        return "off", None
    caddyfile, files = _caddyfile(settings)
    digest = hashlib.sha256(caddyfile.encode())
    for name in sorted(files):
        digest.update(name.encode() + b"\0" + files[name].encode())
    name = digest.hexdigest()[:16]
    files["Caddyfile"] = caddyfile.replace("{dir}", f"{BUNDLE_DIR}/{name}")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(path)
            info.size, info.mode, info.mtime = len(data), 0o600, int(time.time())
            archive.addfile(info, io.BytesIO(data))
    return name, buffer.getvalue()


def wanted(session: Session) -> str:
    return bundle(app_settings.load(session))[0]


# State reported by the frontend container

@dataclass
class Report:
    applied: str = "off"
    failed: str = ""
    error: str = ""
    seen: float = 0.0
    failed_at: datetime | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_report = Report()


def readable_error(log_text: str) -> str:
    """The reason Caddy gave, out of its JSON log lines ("... HTTP 400: {"error": "loading config: ..."}")."""
    messages = []
    for line in log_text.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            if line.strip():
                messages.append(line.strip())
            continue
        if not isinstance(entry, dict) or entry.get("level") not in ("error", "fatal"):
            continue
        message = str(entry.get("msg", ""))
        if "{" in message:
            try:
                message = json.loads(message[message.index("{"):]).get("error", message)
            except (ValueError, AttributeError):
                pass
        messages.append(message.strip())
    return "\n".join(messages)[-4000:] if messages else log_text.strip()[-4000:]


def record(applied: str, failed: str, error: str) -> None:
    with _report.lock:
        if failed and failed != _report.failed:
            _report.failed_at = datetime.now(UTC)
        _report.applied, _report.failed, _report.error = applied, failed, readable_error(error)
        _report.seen = time.monotonic()


def state(session: Session) -> dict:
    """What Caddy is doing compared to the settings: off, active, applying, error or unknown (no news from
    the frontend container, e.g. outside Docker)."""
    target = wanted(session)
    with _report.lock:
        seen = _report.seen and time.monotonic() - _report.seen < SEEN_SECONDS
        applied, failed, error, failed_at = _report.applied, _report.failed, _report.error, _report.failed_at
    if not seen:
        value = "unknown"
    elif failed and failed == target:
        value = "error"
    elif applied != target:
        value = "applying"
    else:
        value = "off" if target == "off" else "active"
    return {"state": value, "error": error if value == "error" else None,
            "failed_at": failed_at if value == "error" else None, "https_in_use": seen and applied != "off"}

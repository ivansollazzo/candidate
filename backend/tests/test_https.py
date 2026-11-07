import io
import ipaddress
import tarfile
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.main import app
from app.services import https


def make_cert(*names: str, days: int = 90) -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
    sans = []
    for name in names:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            sans.append(x509.DNSName(name))
    now = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=days)).add_extension(x509.SubjectAlternativeName(sans), False)
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption()).decode()
    return cert.public_bytes(serialization.Encoding.PEM).decode(), key_pem


def upload(client, cert: str, key: str):
    return client.post("/api/https/certificates", files={"certificate": ("c.pem", cert), "key": ("k.pem", key)})


def sync(anon, applied="off", failed="", error=""):
    r = anon.post(f"/api/internal/https/sync?applied={applied}&failed={failed}", content=error)
    assert r.status_code == 200
    return r.text


def bundle_files(anon, name: str) -> dict[str, str]:
    r = anon.get(f"/api/internal/https/bundle/{name}")
    assert r.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(r.content)) as archive:
        return {m.name: archive.extractfile(m).read().decode() for m in archive.getmembers()}


def test_normalize_hosts():
    assert https.normalize_host(" Candidate.Local. ") == "candidate.local"
    assert https.normalize_host("[FD00::1]") == "fd00::1"
    assert https.normalize_host("*.example.com") == "*.example.com"
    for wrong in ("http://x.it", "x.it:443", "*.com", "a..b", "-a.it", "a b"):
        with pytest.raises(ValueError):
            https.normalize_host(wrong)
    assert https.covers(["*.example.com"], "app.example.com")
    assert not https.covers(["*.example.com"], "a.b.example.com")
    assert not https.covers(["*.example.com"], "example.com")
    assert https.covers(["192.168.1.5"], "192.168.1.5")


def test_admin_only(client):
    stranger = TestClient(app)
    assert stranger.get("/api/https").status_code == 401
    data = client.get("/api/https").json()
    assert data["mode"] == "off" and data["hosts"] == [] and data["state"] == "unknown"
    assert stranger.get("/api/https/root-ca.crt").status_code == 404
    client.put("/api/https", json={"mode": "internal", "hosts": ["candidate.local"]})
    assert stranger.get("/api/https/root-ca.crt").status_code == 200


def test_internal_mode_issues_one_certificate_for_all_hosts(client, anon):
    r = client.put("/api/https", json={"mode": "internal", "hosts": []})
    assert r.status_code == 422
    r = client.put("/api/https", json={"mode": "internal", "hosts": ["http://bad", "x:1"]})
    assert r.status_code == 422 and "http://bad" in r.json()["detail"]
    r = client.put("/api/https", json={"mode": "internal",
                                       "hosts": ["Candidate.local", "192.168.1.50", "candidate.local", "fd00::1"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["hosts"] == ["candidate.local", "192.168.1.50", "fd00::1"]
    assert data["authority"]["name"].startswith("Candidate Local CA")

    name = sync(anon)
    assert name != "off" and client.get("/api/https").json()["state"] == "applying"
    files = bundle_files(anon, name)
    caddyfile = files["Caddyfile"]
    assert "https://candidate.local:5173, https://192.168.1.50:5173, https://[fd00::1]:5173 {" in caddyfile
    assert f"tls /etc/caddy/https/{name}/0.crt /etc/caddy/https/{name}/0.key" in caddyfile
    assert "default_sni 192.168.1.50" in caddyfile and "http://:8080 {" in caddyfile
    leaf = x509.load_pem_x509_certificates(files["0.crt"].encode())
    assert sorted(https.cert_info(files["0.crt"]).names) == ["192.168.1.50", "candidate.local", "fd00::1"]
    # The chain ends with the authority that can be downloaded
    root = anon.get("/api/https/root-ca.crt")
    authority = leaf[1].public_bytes(serialization.Encoding.PEM).decode()
    assert root.status_code == 200 and root.text.strip() == authority.strip()
    assert anon.get("/api/internal/https/bundle/0000").status_code == 404

    sync(anon, applied=name)
    assert client.get("/api/https").json()["state"] == "active"

    # Same authority, new certificate when the hosts change
    client.put("/api/https", json={"mode": "internal", "hosts": ["candidate.local"]})
    assert anon.get("/api/https/root-ca.crt").text == root.text
    assert https.cert_info(bundle_files(anon, sync(anon))["0.crt"]).names == ["candidate.local"]


def test_refused_configuration_is_reported(client, anon):
    client.put("/api/https", json={"mode": "internal", "hosts": ["candidate.local"]})
    name = sync(anon)
    sync(anon, applied="off", failed=name, error="loading certificate: bad\n")
    data = client.get("/api/https").json()
    assert data["state"] == "error" and data["error"] == "loading certificate: bad"
    client.put("/api/https", json={"mode": "off", "hosts": ["candidate.local"]})
    assert sync(anon, applied="off", failed=name) == "off"
    data = client.get("/api/https").json()
    assert data["state"] == "off" and data["hosts"] == ["candidate.local"]


def test_readable_error():
    log = ('{"level":"info","msg":"using config from file"}\n'
           '{"level":"error","msg":"sending configuration to instance: caddy responded with error: HTTP 400: '
           '{\\"error\\":\\"loading config: tls: failed to parse private key\\"}\\n"}\n')
    assert https.readable_error(log) == "loading config: tls: failed to parse private key"
    assert https.readable_error("plain text\n") == "plain text"


def test_custom_certificates(client, anon):
    wildcard, wildcard_key = make_cert("*.example.com", "example.com")
    ip_cert, ip_key = make_cert("192.168.1.50")
    hosts = ["app.example.com", "example.com", "192.168.1.50"]
    r = client.put("/api/https", json={"mode": "custom", "hosts": hosts})
    assert r.status_code == 422 and "app.example.com" in r.json()["detail"]

    assert upload(client, wildcard, ip_key).status_code == 422  # key of another certificate
    assert upload(client, "nope", wildcard_key).status_code == 422
    expired = make_cert("old.example.com", days=-1)
    assert upload(client, *expired).status_code == 422
    assert upload(client, wildcard, wildcard_key).status_code == 201
    r = client.put("/api/https", json={"mode": "custom", "hosts": hosts})
    assert r.status_code == 422 and r.json()["detail"].endswith("192.168.1.50")
    r = upload(client, ip_cert, ip_key)
    assert r.status_code == 201
    assert client.put("/api/https", json={"mode": "custom", "hosts": hosts}).status_code == 200
    certs = client.get("/api/https").json()["certificates"]
    assert [c["hosts"] for c in certs] == [["192.168.1.50"], ["app.example.com", "example.com"]]
    assert "key" not in str(certs)

    caddyfile = bundle_files(anon, sync(anon))["Caddyfile"]
    assert "https://192.168.1.50:5173 {" in caddyfile
    assert "https://app.example.com:5173, https://example.com:5173 {" in caddyfile

    # A certificate still needed can't be removed; the same names replace the old one
    assert client.delete("/api/https/certificates/0").status_code == 409
    assert upload(client, *make_cert("192.168.1.50")).status_code == 201
    assert len(client.get("/api/https").json()["certificates"]) == 2
    client.put("/api/https", json={"mode": "custom", "hosts": ["example.com"]})
    assert client.delete("/api/https/certificates/0").status_code == 200
    assert client.delete("/api/https/certificates/5").status_code == 404


def test_internal_routes_hidden_from_users(client):
    client.put("/api/https", json={"mode": "internal", "hosts": ["candidate.local"]})
    assert "https_ca" not in client.get("/api/settings").text
    assert "/api/internal/https/sync" not in client.get("/openapi.json").json()["paths"]


def test_session_cookie_secure_over_https(anon):
    from tests.conftest import ADMIN

    r = anon.post("/api/auth/setup", json=ADMIN, headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 201 and "secure" in r.headers["set-cookie"].lower()
    r = anon.post("/api/auth/login", json={"username": "admin", "password": ADMIN["password"]})
    assert "secure" not in r.headers["set-cookie"].lower()


def test_cli_turns_https_off(client, capsys):
    from app import cli

    client.put("/api/https", json={"mode": "internal", "hosts": ["candidate.local"]})
    assert cli.main(["https-off"]) == 0
    data = client.get("/api/https").json()
    assert data["mode"] == "off" and data["hosts"] == ["candidate.local"]
    assert cli.main([]) == 2

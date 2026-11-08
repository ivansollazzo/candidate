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
from tests.conftest import ADMIN


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


def login(client, https_request: bool = False):
    client.cookies.clear()
    headers = {"X-Forwarded-Proto": "https"} if https_request else {}
    r = client.post("/api/session", json={"username": ADMIN["username"], "password": ADMIN["password"]},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r


def put_https(client, **payload):
    """Save, then sign in again: turning HTTPS on or off ends every session."""
    r = client.put("/api/https", json={"hosts": [], **payload})
    login(client)
    return r


def wanted(anon) -> str:
    r = anon.get("/api/internal/https/config")
    assert r.status_code == 200
    return r.text


def report(anon, applied="off", failed="", error=""):
    r = anon.post(f"/api/internal/https/reports?applied={applied}&failed={failed}", content=error)
    assert r.status_code == 204


def bundle_files(anon, name: str) -> dict[str, str]:
    r = anon.get(f"/api/internal/https/config/{name}")
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


def test_admin_only(client):
    stranger = TestClient(app)
    assert stranger.get("/api/https").status_code == 401
    data = client.get("/api/https").json()
    assert data["mode"] == "off" and data["hosts"] == [] and data["state"] == "unknown"
    assert stranger.get("/api/https/authority/certificate").status_code == 404
    put_https(client, mode="internal", hosts=["candidate.local"])
    assert stranger.get("/api/https/authority/certificate").status_code == 200


def test_internal_mode_issues_one_certificate_for_all_hosts(client, anon):
    assert client.put("/api/https", json={"mode": "internal", "hosts": []}).status_code == 422
    r = client.put("/api/https", json={"mode": "internal", "hosts": ["http://bad", "x:1"]})
    assert r.status_code == 422 and "http://bad" in r.json()["detail"]
    r = put_https(client, mode="internal", hosts=["Candidate.local", "192.168.1.50", "candidate.local", "fd00::1"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["hosts"] == ["candidate.local", "192.168.1.50", "fd00::1"]
    assert data["authority"]["name"].startswith("Candidate Local CA")

    name = wanted(anon)
    report(anon)
    assert name != "off" and client.get("/api/https").json()["state"] == "applying"
    files = bundle_files(anon, name)
    caddyfile = files["Caddyfile"]
    assert "https://candidate.local:5173, https://192.168.1.50:5173, https://[fd00::1]:5173 {" in caddyfile
    assert f"tls /etc/caddy/https/{name}/0.crt /etc/caddy/https/{name}/0.key" in caddyfile
    assert "default_sni 192.168.1.50" in caddyfile and "http://:8080 {" in caddyfile
    leaf = x509.load_pem_x509_certificates(files["0.crt"].encode())
    assert sorted(https.cert_info(files["0.crt"]).names) == ["192.168.1.50", "candidate.local", "fd00::1"]
    # The chain ends with the authority that can be downloaded
    root = anon.get("/api/https/authority/certificate")
    authority = leaf[1].public_bytes(serialization.Encoding.PEM).decode()
    assert root.status_code == 200 and root.text.strip() == authority.strip()
    assert anon.get("/api/internal/https/config/0000").status_code == 404

    report(anon, applied=name)
    assert client.get("/api/https").json()["state"] == "active"

    # Same authority, new certificate when the hosts change; sessions stay (HTTPS stays on)
    assert client.put("/api/https", json={"mode": "internal", "hosts": ["candidate.local"]}).status_code == 200
    assert client.get("/api/https").status_code == 200
    assert anon.get("/api/https/authority/certificate").text == root.text
    assert https.cert_info(bundle_files(anon, wanted(anon))["0.crt"]).names == ["candidate.local"]


def test_refused_configuration_is_reported(client, anon):
    put_https(client, mode="internal", hosts=["candidate.local"])
    name = wanted(anon)
    report(anon, applied="off", failed=name, error="loading certificate: bad\n")
    data = client.get("/api/https").json()
    assert data["state"] == "error" and data["error"] == "loading certificate: bad"
    put_https(client, mode="off")
    assert wanted(anon) == "off"
    report(anon, applied="off", failed=name)
    data = client.get("/api/https").json()
    assert data["state"] == "off" and data["hosts"] == ["candidate.local"]


def test_readable_error():
    log = ('{"level":"info","msg":"using config from file"}\n'
           '{"level":"error","msg":"sending configuration to instance: caddy responded with error: HTTP 400: '
           '{\\"error\\":\\"loading config: tls: failed to parse private key\\"}\\n"}\n')
    assert https.readable_error(log) == "loading config: tls: failed to parse private key"
    assert https.readable_error("plain text\n") == "plain text"


def test_custom_certificates_serve_their_own_names(client, anon):
    wildcard, wildcard_key = make_cert("*.example.com", "example.com", "My server")
    ip_cert, ip_key = make_cert("192.168.1.50")
    r = client.put("/api/https", json={"mode": "custom", "hosts": []})
    assert r.status_code == 422  # no certificate yet

    assert upload(client, wildcard, ip_key).status_code == 422  # key of another certificate
    assert upload(client, "nope", wildcard_key).status_code == 422
    assert upload(client, *make_cert("old.example.com", days=-1)).status_code == 422
    assert upload(client, *make_cert("Just a label")).status_code == 422  # no usable name
    assert upload(client, wildcard, wildcard_key).status_code == 201
    assert upload(client, ip_cert, ip_key).status_code == 201
    # Still off: uploading doesn't change the mode
    assert wanted(anon) == "off"
    assert put_https(client, mode="custom").status_code == 200
    certs = client.get("/api/https").json()["certificates"]
    assert [c["hosts"] for c in certs] == [["192.168.1.50"], ["*.example.com", "example.com"]]
    assert "PRIVATE KEY" not in client.get("/api/https").text

    caddyfile = bundle_files(anon, wanted(anon))["Caddyfile"]
    assert "https://192.168.1.50:5173 {" in caddyfile
    assert "https://*.example.com:5173, https://example.com:5173 {" in caddyfile
    assert "default_sni 192.168.1.50" in caddyfile

    # The same names replace the old certificate; the last one can't go while custom mode is on
    assert upload(client, *make_cert("192.168.1.50")).status_code == 201
    certs = client.get("/api/https").json()["certificates"]
    assert len(certs) == 2
    assert client.delete(f"/api/https/certificates/{certs[0]['id']}").status_code == 200
    assert client.delete(f"/api/https/certificates/{certs[0]['id']}").status_code == 404
    assert client.delete(f"/api/https/certificates/{certs[1]['id']}").status_code == 409
    put_https(client, mode="off")
    assert client.delete(f"/api/https/certificates/{certs[1]['id']}").status_code == 200


def test_internal_routes_hidden(client):
    put_https(client, mode="internal", hosts=["candidate.local"])
    assert "https_ca" not in client.get("/api/settings").text
    assert not [p for p in client.get("/openapi.json").json()["paths"] if p.startswith("/api/internal")]


def test_session_cookie_per_protocol(anon):
    """A session opened over HTTPS can't be used over HTTP and the other way round, and signing in over HTTP
    works while the browser still holds the HTTPS cookie (the bug of HTTPS turned off)."""
    secure = {"X-Forwarded-Proto": "https"}
    r = anon.post("/api/setup", json=ADMIN, headers=secure)
    assert r.status_code == 201
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("__Secure-candidate_session=") and "secure" in cookie.lower()
    token = anon.cookies.get("__Secure-candidate_session")
    # The test client works over http: the Secure cookie is passed by hand, as a browser does over HTTPS
    over_https = TestClient(app, base_url="https://testserver", headers=secure)
    over_https.cookies.set("__Secure-candidate_session", token)
    assert over_https.get("/api/me").status_code == 200
    # Over plain HTTP the HTTPS session isn't valid, not even under the HTTP cookie name
    assert anon.get("/api/me").status_code == 401
    assert anon.get("/api/me", cookies={"candidate_session": token}).status_code == 401
    r = login(anon)
    assert r.headers["set-cookie"].startswith("candidate_session=")
    assert "secure" not in r.headers["set-cookie"].split(",")[0].lower()
    anon.cookies.set("__Secure-candidate_session", token)
    assert anon.get("/api/me").status_code == 200
    # And over HTTPS the plain HTTP session isn't valid
    over_https.cookies.set("candidate_session", anon.cookies.get("candidate_session"))
    over_https.cookies.delete("__Secure-candidate_session")
    assert over_https.get("/api/me").status_code == 401


def test_switching_protocol_ends_sessions(client):
    other = TestClient(app)
    login(other)
    assert other.get("/api/me").status_code == 200
    client.put("/api/https", json={"mode": "internal", "hosts": ["candidate.local"]})
    assert other.get("/api/me").status_code == 401
    assert client.get("/api/me").status_code == 401
    login(client)
    # Changing only the hosts keeps them
    login(other)
    client.put("/api/https", json={"mode": "internal", "hosts": ["candidate.local", "10.0.0.2"]})
    assert other.get("/api/me").status_code == 200


def test_cli_turns_https_off(client):
    from app import cli

    put_https(client, mode="internal", hosts=["candidate.local"])
    assert cli.main(["https-off"]) == 0
    assert client.get("/api/me").status_code == 401
    login(client)
    data = client.get("/api/https").json()
    assert data["mode"] == "off" and data["hosts"] == ["candidate.local"]
    assert cli.main([]) == 2

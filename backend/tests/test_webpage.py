import json

import pytest

from app.services import webpage

DESCRIPTION = "<p>Cerchiamo uno sviluppatore backend.</p><ul><li>Python</li><li>PostgreSQL</li></ul>" + "<p>Dettagli.</p>" * 30
POSTING = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Backend Developer",
    "hiringOrganization": {"@type": "Organization", "name": "ACME"},
    "jobLocation": {"@type": "Place", "address": {"addressLocality": "Milano", "addressCountry": "IT"}},
    "employmentType": "FULL_TIME",
    "baseSalary": {"@type": "MonetaryAmount", "currency": "EUR",
                   "value": {"@type": "QuantitativeValue", "minValue": 35000, "maxValue": 42000, "unitText": "YEAR"}},
    "description": DESCRIPTION,
}


def page(body: str) -> bytes:
    return f"<html><head><title>Annuncio</title>{body}</head><body><nav>Menu</nav></body></html>".encode()


def test_json_ld_posting(monkeypatch):
    script = f'<script type="application/ld+json">{json.dumps({"@graph": [{"@type": "WebPage"}, POSTING]})}</script>'
    monkeypatch.setattr(webpage, "_download", lambda url: (page(script), "text/html; charset=utf-8"))
    text = webpage.fetch_job_posting("https://example.com/job/1")
    assert text.startswith("Backend Developer\nAzienda: ACME\nSede: Milano, IT")
    assert "Retribuzione: 35000 - 42000 EUR per year" in text
    assert "- Python" in text and "<p>" not in text and "Menu" not in text


def test_page_without_text_explains_how_to_continue(monkeypatch):
    monkeypatch.setattr(webpage, "_download", lambda url: (page("<script>app()</script>"), "text/html"))
    with pytest.raises(webpage.FetchError, match="incollalo"):
        webpage.fetch_job_posting("https://example.com/job/2")


def test_rejects_non_http_links():
    with pytest.raises(webpage.FetchError):
        webpage.fetch_job_posting("file:///etc/passwd")

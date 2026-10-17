"""Download a job posting's text from a link."""

import html
import json
import re
from urllib.parse import urlparse

import httpx
import lxml.html
import trafilatura

from app.i18n import t
from app.services.documents import UnsupportedDocument, extract_text

MAX_BYTES = 5 * 1024 * 1024
MIN_CHARS = 200
HEADERS = {
    # Many sites reject clients that don't look like a browser
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/141.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
BLOCKED_CODES = {401, 403, 429, 999}
SALARY_UNITS = {"YEAR": "per year", "MONTH": "per month", "WEEK": "per week", "DAY": "per day", "HOUR": "per hour"}


class FetchError(Exception):
    pass


def fetch_job_posting(url: str) -> str:
    """Download the page and return the posting text, preferring schema.org/JobPosting structured data."""
    if urlparse(url).scheme not in ("http", "https"):
        raise FetchError(t("link_scheme"))
    content, content_type = _download(url)

    if "pdf" in content_type or content.startswith(b"%PDF"):
        try:
            return extract_text("annuncio.pdf", content)
        except UnsupportedDocument as exc:
            raise FetchError(str(exc)) from exc

    page = content.decode(_charset(content_type) or "utf-8", errors="replace")
    text = _from_json_ld(page)
    if not text or len(text) < MIN_CHARS:
        text = trafilatura.extract(page, url=url, include_tables=True, include_comments=False, favor_recall=True)
    if not text or len(text.strip()) < MIN_CHARS:
        raise FetchError(t("page_no_text", hint=t("paste_hint")))
    return text.strip()


def _download(url: str) -> tuple[bytes, str]:
    try:
        with httpx.stream("GET", url, headers=HEADERS, follow_redirects=True, timeout=20) as response:
            if response.status_code in BLOCKED_CODES:
                raise FetchError(t("site_blocked", code=response.status_code, hint=t("paste_hint")))
            if response.status_code >= 400:
                raise FetchError(t("page_error", code=response.status_code))
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise FetchError(t("page_too_large"))
                chunks.append(chunk)
            return b"".join(chunks), response.headers.get("content-type", "").lower()
    except httpx.HTTPError as exc:
        raise FetchError(t("page_unreachable", error=exc)) from exc


def _charset(content_type: str) -> str | None:
    match = re.search(r"charset=([\w-]+)", content_type)
    return match.group(1) if match else None


def _from_json_ld(page: str) -> str | None:
    for raw in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page, re.S | re.I):
        try:
            data = json.loads(raw.strip(), strict=False)
        except ValueError:
            continue
        posting = _find_posting(data)
        if posting:
            return _posting_text(posting)
    return None


def _find_posting(data):
    if isinstance(data, list):
        return next((p for p in map(_find_posting, data) if p), None)
    if isinstance(data, dict):
        kind = data.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            return data
        if "@graph" in data:
            return _find_posting(data["@graph"])
    return None


def _posting_text(posting: dict) -> str:
    lines = []
    if title := _plain(posting.get("title")):
        lines.append(title)
    org = posting.get("hiringOrganization")
    if company := _plain(org.get("name") if isinstance(org, dict) else org):
        lines.append(f"Azienda: {company}")
    if location := _location(posting.get("jobLocation")):
        lines.append(f"Sede: {location}")
    if posting.get("jobLocationType") == "TELECOMMUTE":
        lines.append("Modalità: remoto")
    if employment := posting.get("employmentType"):
        lines.append(f"Contratto: {', '.join(employment) if isinstance(employment, list) else employment}")
    if salary := _salary(posting.get("baseSalary")):
        lines.append(f"Retribuzione: {salary}")
    lines.append("")
    for key in ("description", "responsibilities", "qualifications", "skills", "experienceRequirements",
                "educationRequirements", "jobBenefits"):
        if text := _html_to_text(posting.get(key)):
            lines.append(text)
    return "\n".join(lines)


def _location(value) -> str | None:
    places = value if isinstance(value, list) else [value]
    names = []
    for place in places:
        address = place.get("address") if isinstance(place, dict) else None
        if isinstance(address, dict):
            parts = [address.get(k) for k in ("addressLocality", "addressRegion", "addressCountry")]
            parts = [p.get("name") if isinstance(p, dict) else p for p in parts]
            names.append(", ".join(str(p) for p in parts if p))
    return "; ".join(n for n in names if n) or None


def _salary(value) -> str | None:
    if not isinstance(value, dict):
        return None
    amount = value.get("value")
    currency = value.get("currency") or ""
    if isinstance(amount, dict):
        unit = SALARY_UNITS.get(str(amount.get("unitText", "")).upper(), "")
        low, high, single = amount.get("minValue"), amount.get("maxValue"), amount.get("value")
        numbers = " - ".join(str(v) for v in (low, high) if v is not None) or (str(single) if single else "")
        return " ".join(p for p in (numbers, currency, unit) if p) if numbers else None
    return f"{amount} {currency}".strip() if amount else None


def _plain(value) -> str | None:
    return html.unescape(str(value)).strip() if value else None


def _html_to_text(value) -> str | None:
    if not value:
        return None
    if isinstance(value, list):
        return "\n".join(f"- {_plain(v)}" for v in value if v)
    if isinstance(value, dict):
        return None
    fragment = str(value)
    if "&lt;" in fragment:
        fragment = html.unescape(fragment)
    if "<" not in fragment:
        return html.unescape(fragment).strip()
    fragment = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"(?i)<li[^>]*>", "\n- ", fragment)
    fragment = re.sub(r"(?i)</(p|div|li|h[1-6]|ul|ol|tr)>", "\n", fragment)
    text = lxml.html.fromstring(f"<div>{fragment}</div>").text_content()
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()

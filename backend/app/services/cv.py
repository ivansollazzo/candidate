"""Deterministic checks on CV-extracted data, so we don't rely on the LLM alone."""

import re
from datetime import date

from app.schemas import CVExperience, CVLink, PersonalExtraction

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w/])\+?\d[\d\s().-]{7,}\d(?![\w/])")
LINK_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com|gitlab\.com)/[\w\-./]+", re.I)
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?")


def apply_contact_fallbacks(personal: PersonalExtraction, text: str) -> PersonalExtraction:
    """Fill in email, phone and links when the model missed them."""
    data = personal.model_copy(deep=True)
    if not data.email and (m := EMAIL_RE.search(text)):
        data.email = m.group(0)
    if not data.phone:
        # At least 9 digits so year ranges like "2018 - 2023" aren't taken for a phone number
        phones = [m.group(0).strip() for m in PHONE_RE.finditer(text)]
        data.phone = next((p for p in phones if sum(c.isdigit() for c in p) >= 9), None)
    known = {link.url.lower().removeprefix("https://").removeprefix("www.") for link in data.links}
    for m in LINK_RE.finditer(text):
        url = m.group(0).rstrip(".")
        bare = url.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
        if bare not in known:
            known.add(bare)
            label = "LinkedIn" if "linkedin" in bare else "GitHub" if "github" in bare else "GitLab"
            data.links.append(CVLink(label=label, url=url if url.startswith("http") else f"https://{url}"))
    return data


def _month_index(value: str | None, *, end: bool) -> int | None:
    if not value or not (m := DATE_RE.match(value.strip())):
        return None
    year, month = int(m.group(1)), m.group(2)
    return year * 12 + (int(month) - 1 if month else (11 if end else 0))


def total_experience_years(experiences: list[CVExperience]) -> float | None:
    """Years of work experience, counting overlapping periods once."""
    today = date.today()
    now = today.year * 12 + today.month - 1
    spans = []
    for exp in experiences:
        start = _month_index(exp.start, end=False)
        stop = now if exp.current or not exp.end else _month_index(exp.end, end=True)
        if start is not None and stop is not None and stop >= start:
            spans.append((start, min(stop, now)))
    if not spans:
        return None
    spans.sort()
    months, (cur_start, cur_end) = 0, spans[0]
    for start, stop in spans[1:]:
        if start > cur_end + 1:
            months += cur_end - cur_start + 1
            cur_start, cur_end = start, stop
        else:
            cur_end = max(cur_end, stop)
    months += cur_end - cur_start + 1
    return round(months / 12, 1)

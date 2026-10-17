"""Deterministic detection of the expected salary in job postings.

Used both as a hint for the LLM and as a fallback when the model misses it. Besides the amount (or range)
it detects the period (annual, monthly, daily, hourly) and whether it is gross or net.
"""

import re
from dataclasses import dataclass

from app.i18n import current_language, t

STRONG_RE = re.compile(
    r"\b(r\.?a\.?l\.?|retribuzion\w*|stipendi\w*|compens\w*|remunerazion\w*|salar(?:y|io|i)|pay(?:\s+range)?|"
    r"inquadramento\s+economico|trattamento\s+economico|gross\s+annual|annual\s+(?:base\s+)?salary|gehalt|salaire)\b",
    re.I,
)
MONEY_RE = re.compile(r"€|\b(?:eur|euro|usd|gbp|chf)\b|\$|£|\d\s*k\b|\bk€|\bmila\b|\blord[io]\b|\bgross\b", re.I)
PERIODS = [
    ("hourly", re.compile(r"all'?\s*ora\b|/\s*h\b|/\s*ora\b|per\s+hour|\bhourly\b|\borari[ao]\b|\bper\s+ora\b", re.I)),
    ("daily", re.compile(r"al\s+giorno|/\s*giorno|\bgiornalier[ao]\b|per\s+day|/\s*day\b|\bdaily\b|day\s+rate", re.I)),
    ("monthly", re.compile(r"al\s+mese|/\s*mese|\bmensil[ie]\b|per\s+month|/\s*month|\bmonthly\b", re.I)),
    ("annual", re.compile(r"\bannu[aoi]\b|\bannual\w*|all'?\s*anno|/\s*anno|per\s+(?:year|annum)|\byearly\b|"
                          r"/\s*y(?:ea)?r\b|\br\.?a\.?l\.?\b", re.I)),
]
GROSS_RE = re.compile(r"\blord[aeio]\b|\bgross\b|\bbrutto\b|\br\.?a\.?l\.?\b|\bbrut\b", re.I)
# "(?<!\.)" skips ".NET" and "ASP.NET"
NET_RE = re.compile(r"\bnett[aeio]\b|(?<!\.)\bnet\b", re.I)
PAYMENTS_RE = re.compile(r"\b(1[2-6])\s*(?:mensilit|monthly\s+payments|salaries)", re.I)
UPTO_RE = re.compile(r"\b(fino\s+a|max(?:imum)?|massim[oa]|up\s+to)\b", re.I)
FROM_RE = re.compile(r"\b(a\s+partire\s+da|minim[oa]|from|starting\s+(?:at|from))\b", re.I)
# Number with thousands separators, optional decimals and k / mila suffix
NUMBER_RE = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[.,\s'’]\d{3})+|\d+)(?:[.,](\d{1,2})(?!\d))?\s*(k\b|k€|mila\b|thousand\b)?",
    re.I,
)
NOT_MONEY_AFTER = re.compile(r"\s*(%|anni|anno\b|years?|yrs|ore\b|hours?|giorni|days|mesi|months|mensilit|"
                             r"dipendenti|persone|people|employees|livell|level|\+\s*anni)", re.I)
CURRENCIES = [("EUR", re.compile(r"€|\beur\b|\beuro\b", re.I)), ("USD", re.compile(r"\$|\busd\b", re.I)),
              ("GBP", re.compile(r"£|\bgbp\b", re.I)), ("CHF", re.compile(r"\bchf\b", re.I))]
SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}

# Plausible amounts per period; None = period not stated
RANGES = {
    "annual": (8_000, 500_000),
    "monthly": (300, 25_000),
    "daily": (30, 3_000),
    "hourly": (5, 500),
    None: (300, 500_000),
}


@dataclass
class SalaryHint:
    text: str  # posting line mentioning the salary
    amount: str | None = None  # normalized amount or range, e.g. "35.000 – 42.000 €"
    period: str | None = None  # annual | monthly | daily | hourly
    basis: str | None = None  # gross | net
    currency: str | None = None

    @property
    def has_amount(self) -> bool:
        return self.amount is not None


def parse_salary(description: str) -> SalaryHint | None:
    """Return the most likely salary line, with amount, period and gross/net."""
    best: SalaryHint | None = None
    best_rank = -1
    for line in _candidate_lines(description):
        strong = bool(STRONG_RE.search(line))
        if not strong and not MONEY_RE.search(line):
            continue
        hint = _parse_line(line)
        rank = (2 if hint.has_amount else 0) + (1 if strong else 0)
        if (hint.has_amount or strong) and rank > best_rank:
            best, best_rank = hint, rank
    return best


def _candidate_lines(text: str) -> list[str]:
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        for part in re.split(r"(?<=[.;])\s+(?=[A-ZÀ-Ý])", raw):
            part = part.strip(" \t-•*·")
            if part:
                lines.append(part)
    return lines


def _parse_line(line: str) -> SalaryHint:
    period = next((name for name, pattern in PERIODS if pattern.search(line)), None)
    payments = PAYMENTS_RE.search(line)
    basis = "net" if NET_RE.search(line) else "gross" if GROSS_RE.search(line) else None
    has_thousands_suffix = bool(re.search(r"\d\s*(k\b|k€|mila\b|thousand\b)", line, re.I))

    values: list[float] = []
    for m in NUMBER_RE.finditer(line):
        if payments and m.start() == payments.start(1):
            continue
        if NOT_MONEY_AFTER.match(line, m.end()):
            continue
        number = float(re.sub(r"[.,\s'’]", "", m.group(1)) + (f".{m.group(2)}" if m.group(2) else ""))
        if m.group(3) or (has_thousands_suffix and number < 1000):
            number *= 1000
        values.append(number)

    low, high = RANGES[period]
    amounts = [v for v in values if low <= v <= high][:2]
    hint = SalaryHint(text=line[:300], period=period, basis=basis, currency=_currency(line))
    if not amounts:
        return hint
    if period is None and max(amounts) >= RANGES["annual"][0]:
        # With no explicit period, amounts in the tens of thousands are annual
        hint.period = "annual"
    hint.currency = hint.currency or "EUR"

    symbol = SYMBOLS.get(hint.currency, hint.currency)
    if len(amounts) == 2 and amounts[0] != amounts[1]:
        text = f"{_fmt(min(amounts))} – {_fmt(max(amounts))} {symbol}"
    elif UPTO_RE.search(line):
        text = t("salary_up_to", amount=f"{_fmt(amounts[0])} {symbol}")
    elif FROM_RE.search(line):
        text = t("salary_from", amount=f"{_fmt(amounts[0])} {symbol}")
    else:
        text = f"{_fmt(amounts[0])} {symbol}"
    if payments and hint.period == "monthly":
        text = t("salary_payments", amount=text, count=payments.group(1))
    hint.amount = text
    return hint


def _fmt(value: float) -> str:
    text = f"{int(value):,}" if value == int(value) else f"{value:,.2f}"
    if current_language.get() == "en":
        return text
    # Italian separators: 35.000 and 12,50
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _currency(line: str) -> str | None:
    for code, pattern in CURRENCIES:
        if pattern.search(line):
            return code
    return None

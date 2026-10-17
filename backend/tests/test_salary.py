import pytest

from app.services.salary import parse_salary


@pytest.mark.parametrize(("text", "amount", "period", "basis"), [
    ("RAL: 35.000 - 42.000 €", "35.000 – 42.000 €", "annual", "gross"),
    ("Offriamo una RAL 35-42k più welfare", "35.000 – 42.000 €", "annual", "gross"),
    ("Retribuzione: da 30k a 35k lordi annui", "30.000 – 35.000 €", "annual", "gross"),
    ("RAL fino a 45.000€", "fino a 45.000 €", "annual", "gross"),
    ("Salary: €40,000–€50,000 per year", "40.000 – 50.000 €", "annual", None),
    ("Compenso: 30.000-35.000 euro", "30.000 – 35.000 €", "annual", None),
    ("RAL tra i 28 e i 32 mila euro", "28.000 – 32.000 €", "annual", "gross"),
    ("Inquadramento: CCNL Commercio, RAL 30.000,00 €", "30.000 €", "annual", "gross"),
    ("Salary range: 60k-80k USD gross", "60.000 – 80.000 $", "annual", "gross"),
    ("2.000€ lordi mensili per 14 mensilità", "2.000 € × 14 mensilità", "monthly", "gross"),
    ("Stipendio: 1.600 € netti al mese", "1.600 €", "monthly", "net"),
    ("RAL a partire da 38K", "da 38.000 €", "annual", "gross"),
    ("Pay range: $120,000 - $150,000", "120.000 – 150.000 $", "annual", None),
    ("Compenso orario: 12,50 € lordi all'ora", "12,50 €", "hourly", "gross"),
    ("Tariffa giornaliera: 350 €/giorno", "350 €", "daily", None),
    ("Sviluppatore .NET, retribuzione 35k", "35.000 €", "annual", None),
])
def test_parse_salary(text, amount, period, basis):
    hint = parse_salary(f"Sviluppatore backend\nSede: Milano, Via Roma 30, 20100\n{text}\nTeam di 30 persone, fondata nel 2015")
    assert hint is not None
    assert (hint.amount, hint.period, hint.basis) == (amount, period, basis)


def test_salary_mentioned_without_amount():
    hint = parse_salary("Requisiti: Python\nRAL commisurata all'esperienza")
    assert hint.text == "RAL commisurata all'esperienza" and not hint.has_amount


@pytest.mark.parametrize("text", [
    "Sede: Via Roma 30, 20100 Milano\n3+ anni di esperienza",
    "Azienda fondata nel 2015 con 250 dipendenti, 14 mensilità",
])
def test_no_false_positives(text):
    hint = parse_salary(text)
    assert hint is None or not hint.has_amount


def test_reconcile_prefers_llm_and_fills_gaps_from_parser():
    from app.schemas import JobCompensationExtraction
    from app.services.extraction import _reconcile_salary

    hint = parse_salary("RAL 35-42k")
    kept = _reconcile_salary(JobCompensationExtraction(salary="36.000 - 40.000 €", salary_period="annual"), hint)
    assert (kept.salary, kept.salary_period, kept.salary_basis) == ("36.000 - 40.000 €", "annual", "gross")
    # Model returns a sentence without amounts: the parser's value wins
    fixed = _reconcile_salary(JobCompensationExtraction(salary="interessante"), hint)
    assert (fixed.salary, fixed.salary_period, fixed.salary_basis) == ("35.000 – 42.000 €", "annual", "gross")


def test_period_and_basis_synonyms_are_normalized():
    from app.schemas import ApplicationUpdate

    update = ApplicationUpdate(salary_period="Mensile", salary_basis="netto")
    assert (update.salary_period, update.salary_basis) == ("monthly", "net")
    assert ApplicationUpdate(salary_period="boh").salary_period is None


def test_salary_text_follows_language():
    from app.i18n import current_language

    token = current_language.set("en")
    try:
        assert parse_salary("Salary up to 45k EUR").amount == "up to 45,000 €"
        assert parse_salary("2.000€ lordi mensili per 14 mensilità").amount == "2,000 € × 14 monthly payments"
    finally:
        current_language.reset(token)

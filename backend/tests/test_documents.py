from pathlib import Path

from app.services.documents import extract_text

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return extract_text(name, (FIXTURES / name).read_bytes())


def test_two_column_pdf_reads_one_column_at_a_time():
    text = read("cv_two_columns.pdf")
    sidebar, main = text.index("Giulia Bianchi"), text.index("Esperienza")
    assert sidebar < main
    # Sidebar stays compact, with no main-column rows in between
    assert "Python\nDjango\nDocker\nPostgreSQL\nKubernetes" in text
    assert "Laurea in Informatica Università di Torino 2014 - 2017" in text


def test_single_column_pdf_keeps_lines_intact():
    text = read("cv_single_column.pdf")
    assert "Backend Developer 1 2019 - 2021" in text
    assert "con\nrilasci settimanali" in text or "con rilasci settimanali" in text

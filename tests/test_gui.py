import pytest

pytest.importorskip("tkinter")

from terminator_nfz.gui import WATCHING_RE, doctor_rows, friendly_status, selection_error, visit_choice_index

from test_watch import doctor


def test_friendly_status():
    assert friendly_status("2026-11-02 14:30:05 FULL×2") == "14:30 – sprawdzone, na razie brak nowych terminów"
    assert friendly_status("2026-11-02 14:30:05 FREE×1, FULL×1 | NOWE: 1") == "14:30 – znaleziono wolny termin!"
    assert "nie udało się" in friendly_status("2026-11-02 14:30:05 ERROR×1, FULL×1")
    assert friendly_status("Przychodnia: pilnuję 1 lekarzy: Anna") is None


def test_watching_line():
    m = WATCHING_RE.match("Przychodnia Testowa: pilnuję 2 lekarzy: Anna Testowa, Jan Testowy")
    assert m.groups() == ("Przychodnia Testowa", "Anna Testowa, Jan Testowy")


def test_doctor_rows_grouped_by_unit():
    a, b = doctor("1", "Anna Testowa"), doctor("2", "Jan Testowy")
    c = doctor("3", "Ewa Inna")
    c = type(c)(**{**c.__dict__, "unit": "PORADNIA GINEKOLOGICZNA", "specialty_id": "3227"})

    rows = doctor_rows([b, c, a])

    assert rows == [("unit", "PORADNIA GINEKOLOGICZNA"), ("doctor", c),
                    ("unit", "PORADNIA POZ"), ("doctor", a), ("doctor", b)]


def test_selection_and_visit_choice():
    assert selection_error([]) is not None
    assert selection_error([doctor("1", "Anna Testowa")]) is None
    assert visit_choice_index(["prywatna", "nfz"]) == 2
    assert visit_choice_index(["nfz"]) == 0

from datetime import datetime
from pathlib import Path

import pytest

from terminator_nfz.clinic import Doctor
from terminator_nfz.state import State
from terminator_nfz.watch import run_round

FIXTURES = Path(__file__).parent / "fixtures"
FREE_HTML = (FIXTURES / "tile_free_nfz.html").read_text(encoding="utf-8")
FULL_HTML = (FIXTURES / "tile_full.html").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 29, 7, 0)


def doctor(id, name):
    slug = name.lower().replace(" ", "-")
    return Doctor(
        id=id, name=name, description="lekarz rodzinny", unit="PORADNIA POZ", provider_id="1", rzoz_id="-1",
        unit_no="1", specialty_id="3081", tile_selector="x", path=f"/{slug}/lekarz-rodzinny/miasto",
        slug=slug, location="miasto",
    )


DOCTORS = [doctor("1", "Anna Testowa"), doctor("2", "Jan Testowy")]


class Outbox:
    def __init__(self):
        self.messages = []

    def __call__(self, text):
        self.messages.append(text)


def fetcher(pages):
    def fetch(doc):
        page = pages[doc.id]
        if isinstance(page, Exception):
            raise page
        return page

    return fetch


def round_(fetch, state, out, now=NOW, problems=()):
    return run_round(DOCTORS, fetch, state, out, now, kinds=("nfz",), title="Przychodnia Testowa", problems=problems)


def test_new_slot_is_announced_once():
    state, out = State(), Outbox()
    fetch = fetcher({"1": FREE_HTML, "2": FULL_HTML})

    assert round_(fetch, state, out) is True
    assert len(out.messages) == 1
    assert "Przychodnia Testowa" in out.messages[0]
    assert "Anna Testowa" in out.messages[0]
    assert "26.11 17:50" in out.messages[0]
    assert "/logowanie/" in out.messages[0]

    assert round_(fetch, state, out) is False
    assert len(out.messages) == 1


def test_failed_send_is_retried_next_round():
    state = State()

    def broken_send(_text):
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        round_(fetcher({"1": FREE_HTML, "2": FULL_HTML}), state, broken_send)
    assert state.seen == {}

    out = Outbox()
    round_(fetcher({"1": FREE_HTML, "2": FULL_HTML}), state, out)
    assert len(out.messages) == 1


def test_past_slots_are_forgotten():
    state, out = State(), Outbox()
    round_(fetcher({"1": FREE_HTML, "2": FULL_HTML}), state, out)
    assert state.seen

    later = datetime(2026, 11, 27, 9, 0)
    assert round_(fetcher({"1": FULL_HTML, "2": FULL_HTML}), state, out, now=later) is True
    assert state.seen == {}


@pytest.mark.parametrize("broken", [RuntimeError("timeout"), "<html>Coś poszło nie tak.</html>"])
def test_failure_alert_after_three_rounds_and_recovery(broken):
    state, out = State(), Outbox()
    bad = fetcher({"1": broken, "2": FULL_HTML})

    for _ in range(2):
        round_(bad, state, out)
    assert out.messages == []

    round_(bad, state, out)
    assert len(out.messages) == 1
    assert "Anna Testowa" in out.messages[0]

    round_(bad, state, out)
    assert len(out.messages) == 1

    round_(fetcher({"1": FULL_HTML, "2": FULL_HTML}), state, out)
    assert len(out.messages) == 2
    assert state.fail_streak == 0


def test_extra_problems_count_as_failure():
    state, out = State(), Outbox()
    ok = fetcher({"1": FULL_HTML, "2": FULL_HTML})
    for _ in range(3):
        round_(ok, state, out, problems=["Nie ma lekarza 999 na stronie placówki"])
    assert len(out.messages) == 1
    assert "999" in out.messages[0]


def test_state_roundtrip(tmp_path):
    state = State()
    state.seen["1|nfz|2026-10-29T08:30"] = "2026-10-29T08:30"
    state.fail_streak = 2
    path = tmp_path / "state.json"
    state.save(path, NOW)

    loaded = State.load(path)
    assert loaded.seen == state.seen
    assert loaded.fail_streak == 2
    assert loaded.saved_at == NOW
    assert State.load(tmp_path / "missing.json").seen == {}

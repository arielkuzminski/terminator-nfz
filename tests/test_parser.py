from datetime import datetime
from pathlib import Path

from terminator_nfz.parser import FREE, FULL, NOT_PUBLISHED, UNKNOWN, parse_tile

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_full_tile_has_no_slots():
    # tile_full.html jest syntetyczny: prawdziwy kafelek z podmienionym komunikatem „Zajęte są wszystkie…”
    status = parse_tile(load("tile_full.html"))
    assert status.state == FULL
    assert status.slots == []
    assert "30.10.2026" in status.note


def test_no_free_slots_right_now_is_full():
    status = parse_tile(load("tile_no_free_now.html"))
    assert status.state == FULL
    assert status.slots == []


def test_not_published_tile():
    status = parse_tile(load("tile_not_published.html"))
    assert status.state == NOT_PUBLISHED
    assert status.slots == []


def test_free_nfz_slot_is_parsed():
    status = parse_tile(load("tile_free_nfz.html"))
    assert status.state == FREE
    assert len(status.slots) == 1
    slot = status.slots[0]
    assert slot.kind == "nfz"
    assert slot.label == "Wizyta NFZ"
    assert slot.when == datetime(2026, 11, 26, 17, 50)
    assert "/logowanie/" in slot.booking_path


def test_private_slot_does_not_count_for_nfz_watch():
    status = parse_tile(load("tile_free_private.html"))
    assert status.state == NOT_PUBLISHED
    assert status.slots == []


def test_private_slot_is_parsed_when_requested():
    status = parse_tile(load("tile_free_private.html"), kinds=("prv",))
    assert status.state == FREE
    assert [s.when for s in status.slots] == [datetime(2026, 11, 27, 7, 30)]


def test_error_page_is_unknown():
    status = parse_tile("<html><body>Coś poszło nie tak.</body></html>")
    assert status.state == UNKNOWN


def test_unrecognised_nfz_box_is_unknown():
    html = (
        '<div class="termin-box t-nfz t-gab"><div><header><span class="tb-lead">'
        "<span>Wizyta NFZ</span></span></header><span>coś nowego</span></div></div>"
    )
    assert parse_tile(html).state == UNKNOWN

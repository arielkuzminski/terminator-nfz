from terminator_nfz.desktop_notify import BOOKING_LABEL, combined_sender, parse_message
from terminator_nfz.parser import parse_tile
from terminator_nfz.state import State
from terminator_nfz.watch import format_slots, update_health

from test_watch import DOCTORS, FREE_HTML, NOW


def test_slot_message_becomes_text_and_buttons():
    slot = parse_tile(FREE_HTML).slots[0]
    lines = parse_message(format_slots([(DOCTORS[0], slot)], NOW, "Przychodnia <Testowa>"))

    texts = [line[1] for line in lines if line[0] == "text" and line[1]]
    links = [line[1:] for line in lines if line[0] == "link"]
    assert texts[0] == "Wolny termin – Przychodnia <Testowa>"  # bez emoji i znaczników, z odkodowanym &lt;
    assert texts[1].startswith("Anna Testowa – ")
    assert "26.11 17:50" in texts[2]
    assert links[0][0] == BOOKING_LABEL
    assert "/logowanie/" in links[0][1]
    assert links[1] == ("Terminarz lekarza", DOCTORS[0].url)


def test_health_messages_are_plain_text():
    out = []
    state = State(fail_streak=2)
    update_health(state, ["Anna Testowa: timeout"], out.append)
    update_health(state, [], out.append)

    assert parse_message(out[0])[0] == ("text", "⚠ Terminator NFZ nie może sprawdzić terminów")
    assert parse_message(out[1]) == [("text", "✅ Terminator NFZ znowu działa.")]


def test_combined_sender_survives_failing_channel():
    got, errors = [], []

    def broken(_text):
        raise RuntimeError("Telegram nie działa")

    combined_sender([broken, got.append], errors.append)("wiadomość")

    assert got == ["wiadomość"]
    assert str(errors[0]) == "Telegram nie działa"

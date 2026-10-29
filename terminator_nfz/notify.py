"""Wysyłka powiadomień przez Telegram Bot API."""

import os

import requests

from . import config

API = "https://api.telegram.org/bot{token}/{method}"


def telegram_sender(token=None, chat_id=None):
    token = token or os.environ.get("TELEGRAM_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise SystemExit(
            "Brak TELEGRAM_TOKEN / TELEGRAM_CHAT_ID. Ustaw je w pliku .env (patrz README) "
            "albo użyj --dry-run, żeby tylko wypisywać powiadomienia."
        )

    def send(text):
        resp = requests.post(
            API.format(token=token, method="sendMessage"),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=config.TIMEOUT_S,
        )
        if not resp.ok:
            raise RuntimeError(f"Telegram odrzucił wiadomość: HTTP {resp.status_code} {resp.text[:200]}")

    return send


def print_sender(text):
    print("--- [dry-run] wiadomość Telegram ---")
    print(text)
    print("------------------------------------", flush=True)


def bot_name(token):
    """Nazwa użytkownika bota albo None, gdy token jest nieprawidłowy."""
    try:
        resp = requests.get(API.format(token=token, method="getMe"), timeout=config.TIMEOUT_S)
    except requests.RequestException:
        return None
    return resp.json().get("result", {}).get("username") if resp.ok else None


def find_chats(token):
    """Rozmowy, w których ktoś ostatnio pisał do bota: lista (chat_id, opis)."""
    resp = requests.get(API.format(token=token, method="getUpdates"), timeout=config.TIMEOUT_S)
    if not resp.ok:
        raise SystemExit(f"Telegram odrzucił token: HTTP {resp.status_code} {resp.text[:200]}")
    chats = {}
    for update in resp.json().get("result", []):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat")
        if chat:
            label = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
            chats[chat["id"]] = f"{label} ({chat.get('type')})"
    return list(chats.items())

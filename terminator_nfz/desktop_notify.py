"""Powiadomienia w okienkowej wersji: wyskakujące okno z dźwiękiem i przyciskami do rezerwacji."""

import html
import re
import sys
import webbrowser

LINK_RE = re.compile(r'<a href="([^"]*)">(.*?)</a>', re.S)
TAG_RE = re.compile(r"<[^>]+>")
# Tk na Windowsie nie zawsze rysuje emoji spoza BMP (🩺 📅 👉) ani selektor wariantu U+FE0F, więc je pomijamy.
NON_BMP_RE = re.compile(r"[\U00010000-\U0010FFFF]\s?|\N{VARIATION SELECTOR-16}")
BOOKING_LABEL = "Zarezerwuj ten termin"


def _plain(fragment):
    return NON_BMP_RE.sub("", html.unescape(TAG_RE.sub("", fragment))).strip()


def parse_message(text):
    """Wiadomość w HTML Telegrama (format_slots, update_health) -> lista linii.

    Każda linia to ("text", tekst) albo ("link", etykieta, adres); pusta linia to ("text", "").
    """
    lines = []
    for raw in text.splitlines():
        link = LINK_RE.search(raw)
        if link:
            lines.append(("link", _plain(link.group(2)), html.unescape(link.group(1))))
        else:
            lines.append(("text", _plain(raw)))
    return lines


def combined_sender(senders, on_error):
    """Wysyła do wszystkich kanałów; błąd jednego (np. Telegrama) nie blokuje pozostałych."""

    def send(text):
        for sender in senders:
            try:
                sender(text)
            except Exception as exc:  # noqa: BLE001 – powiadomienie na komputerze ma przyjść mimo błędu Telegrama
                on_error(exc)

    return send


def _play_sound(root, times=3):
    if sys.platform == "win32":
        import winsound

        for i in range(times):
            root.after(i * 900, lambda: winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC))
    else:
        root.bell()


def _flash(window):
    """Miganie przycisku na pasku zadań, dopóki ktoś nie kliknie okna."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

    FLASHW_ALL, FLASHW_TIMERNOFG = 0x3, 0xC
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_ALL | FLASHW_TIMERNOFG, 0, 0)
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))


def show_popup(root, text):
    """Okno na wierzchu z treścią powiadomienia. Wywoływać tylko z wątku Tk."""
    import tkinter as tk
    from tkinter import ttk

    lines = parse_message(text)
    title = next((line[1] for line in lines if line[0] == "text" and line[1]), "Terminator NFZ")

    win = tk.Toplevel(root)
    win.title(title)
    win.attributes("-topmost", True)
    win.resizable(False, False)
    frame = ttk.Frame(win, padding=20)
    frame.pack(fill="both", expand=True)

    first = True
    for line in lines:
        if line[0] == "link":
            _, label, url = line
            style = "Accent.TButton" if label == BOOKING_LABEL else "TButton"
            ttk.Button(frame, text=label, style=style, command=lambda u=url: webbrowser.open(u)).pack(
                anchor="w", pady=(2, 2), ipadx=8, ipady=4 if label == BOOKING_LABEL else 0
            )
        elif line[1]:
            font = ("Segoe UI", 13, "bold") if first else ("Segoe UI", 11)
            ttk.Label(frame, text=line[1], font=font, wraplength=420, justify="left").pack(anchor="w")
            first = False
        else:
            ttk.Frame(frame, height=8).pack()

    ttk.Button(frame, text="Zamknij", command=win.destroy).pack(anchor="e", pady=(12, 0))

    win.update_idletasks()
    x = root.winfo_screenwidth() - win.winfo_reqwidth() - 40
    y = root.winfo_screenheight() - win.winfo_reqheight() - 100
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.lift()
    win.focus_force()
    _play_sound(root)
    _flash(win)
    return win

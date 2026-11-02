"""Okienkowa wersja Terminatora NFZ: przychodnia -> lekarze -> pilnowanie, z ikoną przy zegarku."""

import queue
import re
import sys
import threading
import webbrowser
from datetime import datetime

import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import requests

from . import appdata, config
from .clinic import ClinicError
from .client import fetch_clinic, fetch_tile, make_session
from .config import VISIT_TYPES, ConfigError, load_config, normalize_clinic_url
from .desktop_notify import combined_sender, show_popup
from .notify import bot_name, find_chats, telegram_sender
from .watch import watch
from .wizard import listing_order, read_env, status_summary, update_env, write_config

TITLE = "Terminator NFZ"
SITE_URL = config.BASE_URL
CHECKED, UNCHECKED = "☑", "☐"
VISIT_OPTIONS = [("Tylko NFZ", ["nfz"]), ("Tylko prywatne", ["prywatna"]), ("NFZ i prywatne", ["nfz", "prywatna"])]
ROUND_RE = re.compile(r"^\d{4}-\d\d-\d\d (\d\d:\d\d):\d\d (.*)$")
# Pierwsza linia z watch(): „Przychodnia X: pilnuję 2 lekarzy: Anna Kowalska, Jan Nowak”.
WATCHING_RE = re.compile(r"^(.*): pilnuję \d+ lekarzy: (.*)$")


# --- czyste funkcje (testowane bez okien) ---------------------------------------------------------------------------

def friendly_status(msg):
    """Linia podsumowania rundy z watch() -> zdanie dla człowieka; None, gdy to nie podsumowanie rundy."""
    m = ROUND_RE.match(msg)
    if not m:
        return None
    clock, rest = m.groups()
    if "NOWE:" in rest:
        return f"{clock} – znaleziono wolny termin!"
    if "ERROR" in rest or "UNKNOWN" in rest:
        return f"{clock} – nie udało się sprawdzić wszystkich lekarzy, spróbuję ponownie"
    return f"{clock} – sprawdzone, na razie brak nowych terminów"


def doctor_rows(doctors):
    """Lekarze pogrupowani według poradni: lista ("unit", nazwa) i ("doctor", Doctor)."""
    rows, unit = [], None
    for doctor in listing_order(doctors):
        if (doctor.unit, doctor.specialty_id) != unit:
            unit = (doctor.unit, doctor.specialty_id)
            rows.append(("unit", doctor.unit or "Bez nazwy poradni"))
        rows.append(("doctor", doctor))
    return rows


def selection_error(chosen):
    if not chosen:
        return "Zaznacz co najmniej jednego lekarza (kliknij jego nazwisko)."
    return None


def visit_choice_index(visit_types):
    for i, (_, types) in enumerate(VISIT_OPTIONS):
        if sorted(types) == sorted(visit_types):
            return i
    return 0


# --- aplikacja ------------------------------------------------------------------------------------------------------

class App:
    def __init__(self, root, autostart=False):
        self.root = root
        self.calls = queue.Queue()
        self.clinic = None
        self.rows = {}  # id wiersza Treeview -> Doctor
        self.checked = set()  # klucze zaznaczonych lekarzy
        self.load_generation = 0
        self.stop_event = None
        self.wake_event = None
        self.worker = None
        self.tray = None
        self.hide_hint_shown = False
        self.quitting = False

        root.title(TITLE)
        root.geometry("780x700")
        root.minsize(680, 640)
        self._set_style()
        self._set_window_icon()

        self.clinic_view = self._build_clinic_view()
        self.doctors_view = self._build_doctors_view()
        self.watch_view = self._build_watch_view()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._start_tray()
        self._poll()

        cfg = self._saved_config()
        if cfg:
            self.start_watch(cfg)
            if autostart and self.tray:
                root.withdraw()
        else:
            self.show(self.clinic_view)

    # --- infrastruktura

    def _set_style(self):
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        base = ("Segoe UI", 10)
        style.configure(".", font=base)
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Error.TLabel", foreground="#c62828")
        style.configure("Ok.TLabel", foreground="#2e7d32")
        style.configure("Status.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"))
        style.configure("Treeview", rowheight=26)

    def _set_window_icon(self):
        try:
            from PIL import ImageTk

            from .icon import make_icon_image

            self._icon_photo = ImageTk.PhotoImage(make_icon_image(64))
            self.root.iconphoto(True, self._icon_photo)
        except ImportError:  # Pillow niezainstalowany – zostaje domyślna ikona
            pass

    def ui(self, fn, *args):
        """Wywołanie fn w wątku Tk (z dowolnego wątku)."""
        self.calls.put((fn, args))

    def _poll(self):
        try:
            while True:
                fn, args = self.calls.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def run_in_thread(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def show(self, view):
        for frame in (self.clinic_view, self.doctors_view, self.watch_view):
            frame.pack_forget()
        view.pack(fill="both", expand=True)

    def _saved_config(self):
        try:
            return load_config(appdata.config_path()) if appdata.config_path().exists() else None
        except ConfigError:
            return None

    # --- widok 1: przychodnia

    def _build_clinic_view(self):
        f = ttk.Frame(self.root, padding=24)
        ttk.Label(f, text="Szukam terminu do lekarza", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            f, style="Hint.TLabel", wraplength=680, justify="left",
            text="1. Otwórz lekarzebezkolejki.pl i znajdź swoją przychodnię.\n"
                 "2. Skopiuj adres strony przychodni z paska przeglądarki (Ctrl+C).\n"
                 "3. Wklej go poniżej (Ctrl+V) i kliknij „Dalej”.",
        ).pack(anchor="w", pady=(8, 12))
        ttk.Button(f, text="Otwórz lekarzebezkolejki.pl", command=lambda: webbrowser.open(SITE_URL)).pack(anchor="w")

        ttk.Label(f, text="Adres przychodni:").pack(anchor="w", pady=(20, 4))
        self.url_var = tk.StringVar()
        entry = ttk.Entry(f, textvariable=self.url_var, font=("Segoe UI", 11))
        entry.pack(fill="x")
        entry.bind("<Return>", lambda _e: self.load_clinic())
        ttk.Label(f, style="Hint.TLabel", text="np. https://lekarzebezkolejki.pl/placowka/NazwaPrzychodni.Miasto").pack(
            anchor="w", pady=(4, 0)
        )

        self.clinic_msg = ttk.Label(f, style="Error.TLabel", wraplength=680, justify="left")
        self.clinic_msg.pack(anchor="w", pady=(12, 0))
        self.clinic_next = ttk.Button(f, text="Dalej  →", style="Accent.TButton", command=self.load_clinic)
        self.clinic_next.pack(anchor="e", pady=(16, 0), ipadx=12, ipady=4)
        return f

    def load_clinic(self, preselect=None):
        self.clinic_msg.configure(text="Wczytuję listę lekarzy…", style="Hint.TLabel")
        self.clinic_next.state(["disabled"])
        self.run_in_thread(self._load_clinic_worker, self.url_var.get(), preselect)

    def _load_clinic_worker(self, url, preselect):
        try:
            clinic = fetch_clinic(make_session(), normalize_clinic_url(url))
        except (ConfigError, ClinicError) as exc:
            self.ui(self._clinic_failed, str(exc))
        except requests.RequestException:
            self.ui(self._clinic_failed, "Nie udało się otworzyć strony. Sprawdź adres i połączenie z internetem.")
        else:
            self.ui(self._clinic_loaded, clinic, preselect)

    def _clinic_failed(self, text):
        self.clinic_next.state(["!disabled"])
        self.clinic_msg.configure(text=text, style="Error.TLabel")
        self.show(self.clinic_view)

    def _clinic_loaded(self, clinic, preselect):
        self.clinic_next.state(["!disabled"])
        self.clinic_msg.configure(text="")
        self.clinic = clinic
        self.clinic_name.configure(text=clinic.name)
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        selected_ids, visit_types = preselect or ([], ["nfz"])
        self.checked = {d.key for d in clinic.doctors if d.id in selected_ids}
        unit = ""
        for kind, item in doctor_rows(clinic.doctors):
            if kind == "unit":
                unit = self.tree.insert("", "end", text=item, open=True, tags=("unit",))
            else:
                row = self.tree.insert(unit, "end", values=(item.description, "sprawdzam…"))
                self.rows[row] = item
                self._draw_check(row)
        self.visit_var.set(visit_choice_index(visit_types))
        self.doctors_msg.configure(text="")
        self.show(self.doctors_view)
        self.load_generation += 1
        self.run_in_thread(self._load_statuses, self.load_generation, list(self.rows.items()))

    def _load_statuses(self, generation, rows):
        session = make_session()
        for row, doctor in rows:
            if generation != self.load_generation:
                return
            try:
                status = status_summary(fetch_tile(session, doctor))
            except requests.RequestException:
                status = "?"
            self.ui(self._set_status, generation, row, status)
            threading.Event().wait(config.DELAY_BETWEEN_DOCTORS_S)

    def _set_status(self, generation, row, status):
        if generation == self.load_generation and self.tree.exists(row):
            self.tree.set(row, "status", status)

    # --- widok 2: lekarze

    def _build_doctors_view(self):
        f = ttk.Frame(self.root, padding=24)
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Button(top, text="←  Inna przychodnia", command=lambda: self.show(self.clinic_view)).pack(side="left")
        self.clinic_name = ttk.Label(f, style="Title.TLabel", wraplength=700)
        self.clinic_name.pack(anchor="w", pady=(12, 0))
        ttk.Label(
            f, style="Hint.TLabel", wraplength=700, justify="left",
            text="Kliknij lekarza, którego mam pilnować (można kilku). „zajęte” = wszystko zajęte, warto pilnować; "
                 "„—” = ten lekarz nie zapisuje przez internet, tylko telefonicznie.",
        ).pack(anchor="w", pady=(4, 8))

        box = ttk.Frame(f)
        box.pack(fill="both", expand=True)
        # Mała wysokość startowa: lista rośnie, gdy jest miejsce, ale nie spycha poniżej okna opcji i przycisku „Zacznij”.
        self.tree = ttk.Treeview(
            box, columns=("desc", "status"), show="tree headings", selectmode="none", height=5
        )
        for col, text, width in (("#0", "Lekarz", 340), ("desc", "Specjalność", 180), ("status", "Najbliższy termin", 170)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, minwidth=60, anchor="w")
        self.check_images = self._checkbox_images()
        self.tree.tag_configure("unit", font=("Segoe UI", 10, "bold"), background="#eeeeee")
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.toggle_doctor)

        options = ttk.Frame(f)
        options.pack(fill="x", pady=(12, 0))
        ttk.Label(options, text="Jakie wizyty:").pack(side="left")
        self.visit_var = tk.IntVar(value=0)
        for i, (label, _) in enumerate(VISIT_OPTIONS):
            ttk.Radiobutton(options, text=label, variable=self.visit_var, value=i).pack(side="left", padx=(8, 0))

        self.autostart_var = tk.BooleanVar(value=appdata.autostart_enabled())
        if appdata.IS_WINDOWS:
            ttk.Checkbutton(f, text="Uruchamiaj razem z Windowsem i od razu pilnuj", variable=self.autostart_var).pack(
                anchor="w", pady=(8, 0)
            )

        self._build_telegram_section(f)

        bottom = self.doctors_bottom = ttk.Frame(f)
        bottom.pack(fill="x", pady=(12, 0))
        self.doctors_msg = ttk.Label(bottom, style="Error.TLabel")
        self.doctors_msg.pack(side="left")
        ttk.Button(bottom, text="Zacznij pilnować  →", style="Accent.TButton", command=self.save_and_start).pack(
            side="right", ipadx=12, ipady=4
        )
        return f

    def toggle_doctor(self, event):
        row = self.tree.identify_row(event.y)
        doctor = self.rows.get(row)
        if not doctor:
            return "break"
        if doctor.key in self.checked:
            self.checked.discard(doctor.key)
        else:
            self.checked.add(doctor.key)
        self._draw_check(row)
        self.doctors_msg.configure(text="")
        return "break"

    def _draw_check(self, row):
        doctor = self.rows[row]
        on = doctor.key in self.checked
        if self.check_images:
            self.tree.item(row, text=" " + doctor.name, image=self.check_images[on])
        else:
            self.tree.item(row, text=f"{CHECKED if on else UNCHECKED} {doctor.name}")

    def _checkbox_images(self):
        """Pole wyboru jako obrazek (czytelniejsze niż znak ☐); bez Pillow zostaje znak."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except ImportError:
            return None
        size = 18
        images = []
        for on in (False, True):
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rectangle((1, 1, size - 2, size - 2), fill="#1976d2" if on else "white", outline="#555555", width=1)
            if on:
                draw.line((4, 9, 8, 13, 14, 5), fill="white", width=2)
            images.append(ImageTk.PhotoImage(img))
        return images

    def _build_telegram_section(self, parent):
        self.tg_open = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent, text="Wysyłaj też na telefon przez Telegram (opcjonalnie)", variable=self.tg_open,
            command=self._toggle_telegram,
        ).pack(anchor="w", pady=(8, 0))
        self.tg_frame = ttk.Frame(parent, padding=(24, 4, 0, 0))
        self.tg_status = ttk.Label(self.tg_frame, wraplength=640, justify="left")
        self.tg_status.pack(anchor="w")
        self.tg_help = ttk.Label(
            self.tg_frame, style="Hint.TLabel", wraplength=640, justify="left",
            text="Na Telegramie napisz do @BotFather, wyślij mu /newbot i nadaj nazwę. "
                 "Dostaniesz długi klucz (np. 123456:ABC…) – wklej go tutaj.",
        )
        self.tg_row = ttk.Frame(self.tg_frame)
        self.tg_token = tk.StringVar()
        ttk.Entry(self.tg_row, textvariable=self.tg_token, show="•", width=50).pack(side="left")
        self.tg_button = ttk.Button(self.tg_row, text="Połącz", command=self.telegram_connect)
        self.tg_button.pack(side="left", padx=(8, 0))
        self.tg_bot = None
        env = read_env(appdata.env_path())
        if env.get("TELEGRAM_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
            self.tg_open.set(True)
            self._telegram_connected()

    def _show_telegram_frame(self):
        if hasattr(self, "doctors_bottom"):
            self.tg_frame.pack(anchor="w", fill="x", before=self.doctors_bottom)
        else:
            self.tg_frame.pack(anchor="w", fill="x")

    def _toggle_telegram(self):
        if self.tg_open.get():
            self._show_telegram_frame()
            if not self._telegram_configured():
                self._telegram_ask_token()
        else:
            self.tg_frame.pack_forget()
            if self._telegram_configured():
                update_env(appdata.env_path(), {"TELEGRAM_TOKEN": "", "TELEGRAM_CHAT_ID": ""})
                self.tg_status.configure(text="")

    def _telegram_configured(self):
        env = read_env(appdata.env_path())
        return bool(env.get("TELEGRAM_TOKEN") and env.get("TELEGRAM_CHAT_ID"))

    def _telegram_ask_token(self):
        self.tg_bot = None
        self.tg_status.configure(text="", style="TLabel")
        self.tg_help.pack(anchor="w")
        self.tg_row.pack(anchor="w", pady=(4, 0))
        self.tg_button.configure(text="Połącz")

    def _telegram_connected(self):
        self.tg_help.pack_forget()
        self.tg_row.pack_forget()
        self.tg_status.configure(text="✓ Telegram połączony – powiadomienia przyjdą też na telefon.", style="Ok.TLabel")
        if self.tg_open.get():
            self._show_telegram_frame()

    def telegram_connect(self):
        token = self.tg_token.get().strip()
        if not token:
            self.tg_status.configure(text="Wklej klucz od @BotFather.", style="Error.TLabel")
            return
        self.tg_button.state(["disabled"])
        self.tg_status.configure(text="Sprawdzam…", style="Hint.TLabel")
        self.run_in_thread(self._telegram_worker, token, self.tg_bot)

    def _telegram_worker(self, token, bot):
        try:
            if bot is None:
                name = bot_name(token)
                if not name:
                    self.ui(self._telegram_msg, "Telegram nie rozpoznaje tego klucza. Skopiuj go jeszcze raz od @BotFather.")
                    return
                self.ui(self._telegram_wait_for_message, name)
                return
            chats = find_chats(token)
            if not chats:
                self.ui(self._telegram_msg, f"Nie widzę jeszcze wiadomości. Napisz cokolwiek do @{bot} i kliknij ponownie.")
                return
            chat_id, _label = chats[-1]
            telegram_sender(token, chat_id)("✅ Terminator NFZ połączony. Tutaj przyjdą powiadomienia o wolnych terminach.")
            update_env(appdata.env_path(), {"TELEGRAM_TOKEN": token, "TELEGRAM_CHAT_ID": str(chat_id)})
            self.ui(self._telegram_connected)
        except (requests.RequestException, RuntimeError, SystemExit):
            self.ui(self._telegram_msg, "Nie udało się połączyć z Telegramem. Sprawdź internet i spróbuj ponownie.")
        finally:
            self.ui(lambda: self.tg_button.state(["!disabled"]))

    def _telegram_msg(self, text):
        self.tg_status.configure(text=text, style="Error.TLabel")

    def _telegram_wait_for_message(self, name):
        self.tg_bot = name
        self.tg_help.pack_forget()  # instrukcja o BotFatherze już niepotrzebna
        self.tg_status.configure(
            text=f"✓ Bot @{name} znaleziony. Teraz otwórz go na Telegramie, napisz cokolwiek (np. „cześć”) "
                 "i kliknij „Sprawdź”.",
            style="TLabel",
        )
        self.tg_button.configure(text="Sprawdź")

    def save_and_start(self):
        chosen = [d for d in self.rows.values() if d.key in self.checked]
        error = selection_error(chosen)
        if error:
            self.doctors_msg.configure(text=error)
            return
        if self.tg_open.get() and not self._telegram_configured():
            self.doctors_msg.configure(text="Dokończ łączenie z Telegramem albo odznacz tę opcję.")
            return
        visit_types = VISIT_OPTIONS[self.visit_var.get()][1]
        write_config(appdata.config_path(), self.clinic, chosen, visit_types, 90)
        try:
            appdata.set_autostart(self.autostart_var.get())
        except OSError:
            pass  # brak dostępu do rejestru nie powinien blokować pilnowania
        self.load_generation += 1  # przerywa wczytywanie statusów
        self.start_watch(load_config(appdata.config_path()))

    # --- widok 3: pilnowanie

    def _build_watch_view(self):
        f = ttk.Frame(self.root, padding=24)
        self.watch_title = ttk.Label(f, style="Title.TLabel", wraplength=700)
        self.watch_title.pack(anchor="w")
        self.watch_doctors = ttk.Label(f, wraplength=700, justify="left")
        self.watch_doctors.pack(anchor="w", pady=(4, 0))
        self.watch_status = ttk.Label(f, style="Status.TLabel", wraplength=700)
        self.watch_status.pack(anchor="w", pady=(16, 0))
        ttk.Label(
            f, style="Hint.TLabel", wraplength=700, justify="left",
            text="Gdy zwolni się termin, wyskoczy okienko z dźwiękiem i przyciskiem „Zarezerwuj”. "
                 "Możesz zamknąć to okno – program dalej pilnuje (ikona przy zegarku). "
                 "Komputer musi być włączony.",
        ).pack(anchor="w", pady=(8, 12))

        buttons = ttk.Frame(f)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Sprawdź teraz", command=self.check_now).pack(side="left")
        self.pause_button = ttk.Button(buttons, text="Wstrzymaj", command=self.toggle_pause)
        self.pause_button.pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Zmień lekarzy", command=self.change_doctors).pack(side="left", padx=(8, 0))

        ttk.Label(f, text="Historia:", style="Hint.TLabel").pack(anchor="w", pady=(16, 2))
        self.log_box = ScrolledText(f, height=10, font=("Segoe UI", 10), state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True)
        return f

    def start_watch(self, cfg):
        self.stop_watch()
        self.cfg = cfg
        self.watch_title.configure(text="Pilnuję terminów…")
        self.watch_doctors.configure(text=cfg.clinic_url)
        self.watch_status.configure(text="Pierwsze sprawdzenie za chwilę…")
        self.pause_button.configure(text="Wstrzymaj")
        self.show(self.watch_view)

        env = read_env(appdata.env_path())
        senders = [lambda text: self.ui(show_popup, self.root, text)]
        if env.get("TELEGRAM_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
            senders.append(telegram_sender(env["TELEGRAM_TOKEN"], env["TELEGRAM_CHAT_ID"]))
        send = combined_sender(senders, lambda exc: self.log(f"Nie udało się wysłać na Telegram: {exc}"))

        self.stop_event, self.wake_event = threading.Event(), threading.Event()
        self.worker = threading.Thread(
            target=self._watch_worker, args=(cfg, send, self.stop_event, self.wake_event), daemon=True
        )
        self.worker.start()
        appdata.keep_awake(True)
        self._update_tray()

    def _watch_worker(self, cfg, send, stop, wake):
        while not stop.is_set():
            try:
                code = watch(cfg, appdata.state_path(), send, out=self.log, stop=stop, wake=wake)
            except (ClinicError, ConfigError) as exc:
                self.ui(self._watch_failed, str(exc))
                return
            except Exception as exc:  # noqa: BLE001 – nieoczekiwany błąd: zapisz i spróbuj ponownie
                self.log(f"Błąd: {exc!r}")
                code = 1
            if code == 0:
                return
            self.log("Strona przychodni nie odpowiada, spróbuję ponownie za chwilę.")
            stop.wait(cfg.interval_seconds)

    def _watch_failed(self, text):
        self.stop_watch()
        self.url_var.set(self.cfg.clinic_url)
        self._clinic_failed(text)
        self._restore_window()

    def stop_watch(self):
        if self.stop_event:
            self.stop_event.set()
            self.wake_event.set()
        self.stop_event = self.wake_event = None
        appdata.keep_awake(False)
        self._update_tray()

    @property
    def watching(self):
        return self.stop_event is not None

    def log(self, msg):
        """Wywoływane z wątku pilnowania. Do log.txt trafia pełna linia, w oknie zdanie dla człowieka."""
        try:
            appdata.append_log(msg if ROUND_RE.match(msg) else f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}")
        except OSError:
            pass
        self.ui(self._show_log, msg)

    def _show_log(self, msg):
        watching = WATCHING_RE.match(msg)
        if watching:
            self.watch_title.configure(text=watching.group(1))
            self.watch_doctors.configure(text="Pilnuję: " + watching.group(2))
            line = f"{datetime.now():%H:%M} – zaczynam pilnować"
        else:
            status = friendly_status(msg)
            if status:
                self.watch_status.configure(text=status)
            line = status or f"{datetime.now():%H:%M} – {msg}"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def check_now(self):
        if self.watching:
            self.watch_status.configure(text="Sprawdzam…")
            self.wake_event.set()
        else:
            self.start_watch(self.cfg)

    def toggle_pause(self):
        if self.watching:
            self.stop_watch()
            self.watch_status.configure(text="Wstrzymane – nie pilnuję terminów.")
            self.pause_button.configure(text="Wznów")
        else:
            self.start_watch(self.cfg)

    def change_doctors(self):
        self.stop_watch()
        self.url_var.set(self.cfg.clinic_url)
        self.show(self.clinic_view)
        self.load_clinic(preselect=(self.cfg.doctors, self.cfg.visit_types))

    # --- ikona przy zegarku i zamykanie

    def _start_tray(self):
        try:
            import pystray

            from .icon import make_icon_image
        except ImportError:  # bez pystray zamknięcie okna kończy program
            return

        menu = pystray.Menu(
            pystray.MenuItem("Pokaż okno", lambda: self.ui(self._restore_window), default=True),
            pystray.MenuItem(lambda _item: "Wstrzymaj pilnowanie" if self.watching else "Wznów pilnowanie",
                             lambda: self.ui(self.toggle_pause)),
            pystray.MenuItem("Zakończ", lambda: self.ui(self.quit)),
        )
        self.tray = pystray.Icon("terminator-nfz", make_icon_image(64), TITLE, menu)
        self.tray.run_detached()

    def _update_tray(self):
        if self.tray:
            self.tray.title = f"{TITLE} – pilnuję" if self.watching else f"{TITLE} – wstrzymany"
            self.tray.update_menu()

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def on_close(self):
        if self.tray and self.watching:
            self.root.withdraw()
            if not self.hide_hint_shown:
                self.hide_hint_shown = True
                self.tray.notify("Nadal pilnuję terminów. Ikona jest przy zegarku.", TITLE)
            return
        if self.watching and not messagebox.askyesno(TITLE, "Zamknąć program i przestać pilnować terminów?"):
            return
        self.quit()

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.stop_watch()
        if self.tray:
            self.tray.stop()
        self.root.destroy()


def _dpi_aware():
    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    _dpi_aware()
    if not appdata.single_instance():
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(TITLE, "Terminator NFZ już działa.\nKliknij jego ikonę przy zegarku (prawy dolny róg ekranu).")
        root.destroy()
        return
    root = tk.Tk()
    App(root, autostart="--autostart" in argv)
    root.mainloop()


if __name__ == "__main__":
    main()

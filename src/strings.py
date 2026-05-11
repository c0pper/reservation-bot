from datetime import date

# ── Day and month names ────────────────────────────────────────

DAY_ABBRS_IT = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]

DISPLAY_NAMES_IT = [
    "Lunedì", "Martedì", "Mercoledì",
    "Giovedì", "Venerdì", "Sabato", "Domenica",
]

MONTH_ABBRS_IT = [
    "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
    "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
]

MONTH_NAMES_IT = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]


# ── Date formatters ────────────────────────────────────────────

def fmt_date_short(d: date) -> str:
    return f"{DAY_ABBRS_IT[d.weekday()]} {d.day}"


def fmt_date_weekday_long(d: date) -> str:
    return f"{DISPLAY_NAMES_IT[d.weekday()]} {d.day} {MONTH_NAMES_IT[d.month - 1]}"


def fmt_date_long(d: date) -> str:
    return f"{DISPLAY_NAMES_IT[d.weekday()]} {d.day} {MONTH_NAMES_IT[d.month - 1]} {d.year}"


def fmt_date_abbr(d: date) -> str:
    return f"{DAY_ABBRS_IT[d.weekday()]}, {d.day} {MONTH_ABBRS_IT[d.month - 1]}"


def fmt_date_abbr_long(d: date) -> str:
    return f"{DAY_ABBRS_IT[d.weekday()]}, {d.day} {MONTH_ABBRS_IT[d.month - 1]} {d.year}"


def fmt_date_abbr_day(d: date) -> str:
    return f"{DAY_ABBRS_IT[d.weekday()]} {d.day} {MONTH_ABBRS_IT[d.month - 1]}"


# ── Plural helpers ─────────────────────────────────────────────

def child_label(n: int) -> str:
    return "bambino" if n == 1 else "bambini"


def h_label(n: int) -> str:
    return "ora" if n == 1 else "ore"


# ── Commands ───────────────────────────────────────────────────

HELP_TEXT = (
    "Comandi disponibili:\n"
    "/start - Avvia il bot\n"
    "/help - Mostra questo messaggio\n"
    "/book - Prenota con la babysitter\n"
    "/my_bookings - Le tue prenotazioni\n"
    "/cancel - Cancella una prenotazione\n"
    "/available - Mostra fasce orarie disponibili\n"
)

SITTER_HELP = (
    "\nComandi babysitter:\n"
    "/set_schedule - Configura orario settimanale\n"
    "/admin - Visualizza tutte le prenotazioni\n"
)


# ── /start ─────────────────────────────────────────────────────

def fmt_start(name: str) -> str:
    return (
        f"Ciao {name}! Sono il bot per le prenotazioni di Carolina.\n\n "
        "Usa /help per i comandi o /book per prenotare."
    )


# ── /book ──────────────────────────────────────────────────────

NO_SCHEDULE = "Nessun orario configurato. Riprova più tardi."
NO_SLOTS_14 = "Nessuno slot disponibile nei prossimi 14 giorni. Riprova più tardi."
SELECT_LOCATION = "Digita l'indirizzo dove hai bisogno della babysitter (es. Via Roma 1, Napoli):"
LOCATION_NOT_FOUND = "Indirizzo non trovato in Campania. Riprova con un indirizzo della regione Campania, oppure digita \u2018Indietro\u2019 per tornare alla scelta della data."
MULTIPLE_LOCATIONS = "Ho trovato più indirizzi. Scegli quello corretto:"
CONFIRM_LOCATION = "📍 Posizione confermata: {address}"
SELECT_DATE = "Seleziona una data (solo slot disponibili):"
NO_AVAILABILITY_DAY = "Nessuna disponibilità in questo giorno."
NO_SLOTS_DATE = "Nessuno slot disponibile il {date}. Scegli un'altra data."
AVAILABLE_TIMES = "Orari disponibili per {date}:"
NO_DURATION = "Nessuna durata disponibile per questo orario. Scegli un altro orario."
DURATION_FOR = "Durata per {date} alle {time}:"
HOW_MANY_CHILDREN = "Quanti bambini?"

BOOKING_SUMMARY = (
    "📋 Riepilogo prenotazione\n"
    "Data: {date}\n"
    "Orario: {start} \u2013 {end} ({hours} {h_label})\n"
    "Bambini: {children}\n"
    "📍 {address}\n"
    "Nome: {name}\n\n"
    "Confermi?"
)

BOOKING_CONFIRMED_TXT = (
    "✅ Prenotazione confermata!\n"
    "Data: {date}\n"
    "Orario: {start} \u2013 {end}\n"
    "Bambini: {children}\n"
    "📍 {address}\n"
    "ID prenotazione: #{id}\n\n"
    "Usa /my_bookings per vedere le tue prenotazioni "
    "o /cancel per annullarle."
)

SITTER_NEW_BOOKING = (
    "✅ Nuova prenotazione #{id}\n"
    "Cliente: {name} (ID: {uid})\n"
    "Data: {date}\n"
    "Orario: {start} \u2013 {end}\n"
    "Bambini: {children}\n"
    "📍 {address}"
)

BOOKING_CANCELLED_OVER = "Prenotazione annullata. Usa /book per ricominciare."
BOOKING_CANCELLED_NEW = "Prenotazione annullata. Usa /book per farne una nuova."
SLOT_UNAVAILABLE = "Slot non più disponibile. Usa /book per riprovare."
DURATION_UNAVAILABLE = "Durata non più disponibile. Usa /book per riprovare."
USE_BUTTONS_BOOK = "Usa i pulsanti per rispondere, o digita /cancel per uscire."


# ── /my_bookings ───────────────────────────────────────────────

NO_BOOKINGS = "Non hai prenotazioni imminenti."
YOUR_BOOKINGS = "Le tue prenotazioni imminenti:"
CANCEL_HINT = "\nUsa /cancel per annullare una prenotazione."


# ── /cancel ────────────────────────────────────────────────────

NO_BOOKINGS_CANCEL = "Non hai prenotazioni da annullare."
SELECT_BOOKING_CANCEL = "Seleziona una prenotazione da annullare:"
CANCELLATION_ABORTED = "Cancellazione annullata."
BOOKING_UNAVAILABLE = "Prenotazione non più disponibile."
CANCEL_THIS_BOOKING = (
    "Annullare questa prenotazione?\n\n"
    "#{id} \u2014 {date}\n"
    "{start} \u2013 {end}\n"
    "{children}"
)
BOOKING_CANCELLED_OK = "✅ Prenotazione #{id} annullata."
SITTER_CANCEL_NOTE = "❌ Prenotazione #{id} annullata dal cliente {name}."
CANCEL_FAILED = "Impossibile annullare. Potrebbe non esistere più."
USE_BUTTONS_CANCEL = "Usa i pulsanti qui sopra, o digita /cancel per uscire."
CANCEL_ALL_PROMPT = "Annullare tutte le prenotazioni?"
BOOKINGS_ALL_CANCELLED = "✅ {count} prenotazione(i) annullata(e)."
SITTER_CANCEL_ALL_NOTE = "❌ {name} ha annullato {count} prenotazione(i)."


# ── /available ─────────────────────────────────────────────────

NO_SCHEDULE_AVAIL = "Nessun orario configurato."
AVAILABLE_HEADER = "Slot disponibili nei prossimi 14 giorni:"
NO_AVAILABLE_SLOTS = "Nessuno slot disponibile nei prossimi 14 giorni."


# ── /set_schedule ──────────────────────────────────────────────

SITTER_ONLY = "Questo comando è solo per la baby sitter."
TAP_DAY = "Tocca un giorno per configurare le fasce orarie, poi tocca Fatto:"
NO_WINDOWS_CFG = "  Nessuna fascia configurata"
SELECT_START = "Seleziona ora inizio:"
SELECT_END = "Inizio: {start}\nSeleziona ora fine:"
SCHEDULE_PREVIEW = "Anteprima orari:"
SAVE_SCHEDULE = "Salvare questi orari?"
SCHEDULE_UNCHANGED = "Orario invariato. Usa /set_schedule per ricominciare."
NO_WINDOWS_SAVE = "Nessuna fascia oraria configurata. Orario invariato."
SCHEDULE_UPDATED = "✅ Orario aggiornato!\n\n{schedule}"
SCHEDULE_CANCELLED = "Orario invariato."
USE_BUTTONS_SCHEDULE = "Usa i pulsanti qui sopra, o digita /cancel per uscire."


# ── /admin ─────────────────────────────────────────────────────

ADMIN_SITTER_ONLY = "Questo comando è solo per la baby sitter."
ADMIN_NO_BOOKINGS = "Nessuna prenotazione imminente."
ADMIN_TIMELINE_HEADER = "📋 Programma settimanale"
ADMIN_WINDOW_HEADER = "\n  🕐 {start}-{end}"
ADMIN_BOOKING_LINE = "    ▸ {start}-{end}  #{id} {name} 📍{address} ({children})"
ADMIN_BOOKING_NOLOC = "    ▸ {start}-{end}  #{id} {name} ({children})"
ADMIN_GAP = "    ══ {minutes} min liberi ══"
ADMIN_FREE_WINDOW = "    ── libera ──"


# ── scheduler.py strings ───────────────────────────────────────

NO_SCHEDULE_CONFIGURED = "Nessun orario configurato."
DAY_OFF_LABEL = "OFF"


# ── Button labels ──────────────────────────────────────────────

BTN_CANCEL = "\u274c Annulla"
BTN_BACK = "\u25c0 Indietro"
BTN_YES = "\u2705 S\u00ec"
BTN_NO = "\u274c No"
BTN_DONE = "\u2705 Fatto"
BTN_YES_CANCEL = "\u2705 S\u00ec, annulla"
BTN_NO_BACK = "\u25c0 No, torna indietro"
BTN_ADD_WINDOW = "\u2795 Aggiungi fascia"
BTN_CLEAR_DAY = "\U0001f5d1 Cancella giorno"
BTN_BACK_DAYS = "\u25c0 Giorni"
BTN_CANCEL_EXIT = "\u274c Annulla"
BTN_CANCEL_ALL = "\U0001f5d1 Annulla tutte"

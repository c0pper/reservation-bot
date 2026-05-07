# Agents.md

## Project

Minimal Telegram bot using `python-telegram-bot` 22.x. Single entrypoint at `src/main.py`.

## Commands

```bash
uv sync                        # install dependencies
BOT_TOKEN="xxx" SITTER_USER_ID="123456" uv run python src/main.py   # run the bot
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | — | Telegram bot token from @BotFather |
| `SITTER_USER_ID` | Yes | — | Telegram user ID of the sitter (for admin commands) |
| `DATABASE_PATH` | No | `data/reservations.db` | Path to SQLite database file |

The local `.env` file exists but is **not** loaded automatically — do not commit it.

## Tooling

- **Package manager**: `uv` (PEP 723 / uv.lock)
- **Python**: 3.14 (`.python-version`)
- **Tests / lint / typecheck**: none configured

## Architecture

- `src/main.py` — `Application.builder().token(...).build()` + polling
- `src/db.py` — SQLite database (schema init, CRUD)
- `src/scheduler.py` — Availability computation logic
- `src/notifier.py` — Sitter notification helper
- `src/handlers.py` — All command and conversation handlers

## Bot Commands

| Command | Access | Description |
|---|---|---|
| `/start` | Everyone | Welcome message |
| `/help` | Everyone | List commands |
| `/book` | Everyone | Interactive booking (date → time → duration → confirm) |
| `/my_bookings` | Everyone | View upcoming bookings |
| `/cancel <id>` | Everyone | Cancel a booking |
| `/available [date]` | Everyone | Show available slots |
| `/set_schedule` | Sitter only | Configure weekly repeating schedule |
| `/admin` | Sitter only | View all upcoming bookings |

## Database

SQLite via stdlib `sqlite3`. Single database file at `data/reservations.db` (configurable via `DATABASE_PATH`). Contains `schedule` and `bookings` tables.

## Booking Flow

1. `/book` → 14-day date picker (greyed out = no schedule that day)
2. Pick a date → available `:00` start times
3. Pick a start time → duration options (1h, 2h, ...)
4. Confirm → booking saved, sitter notified via Telegram message

No persistence, no webhooks — polling only.

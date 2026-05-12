# Reservation Bot

Telegram bot for booking a babysitter (Carolina). Built with `python-telegram-bot` 22.x. Italian language interface.

## Features

- **Booking flow**: address search → date picker (14 days) → time slot → duration → child count → confirm
- **Geocoding**: address lookup and transit time estimation via Geoapify API (Campania region filter)
- **Schedule management**: sitter configures weekly repeating availability windows
- **Sitter notifications**: new bookings and cancellations sent via Telegram
- **Admin view**: timeline of all upcoming bookings with gaps

## Commands

| Command | Access | Description |
|---|---|---|
| `/start` | Everyone | Welcome message |
| `/help` | Everyone | List commands |
| `/book` | Everyone | Interactive booking (address → date → time → duration → confirm) |
| `/my_bookings` | Everyone | View upcoming bookings |
| `/cancel` | Everyone | Cancel a booking |
| `/available` | Everyone | Show available slots |
| `/set_schedule` | Sitter only | Configure weekly repeating schedule |
| `/admin` | Sitter only | View all upcoming bookings |

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

```bash
# Install dependencies
uv sync

# Run the bot
BOT_TOKEN="your_token" SITTER_USER_ID="123456" uv run python src/main.py
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | — | Telegram bot token from @BotFather |
| `SITTER_USER_ID` | Yes | — | Telegram user ID(s) of the sitter — comma-separated for multiple |
| `DATABASE_PATH` | No | `data/reservations.db` | Path to SQLite database file |
| `GEOAPIFY_API_KEY` | No | — | API key for Geoapify geocoding/routing |
| `LOG_LEVEL` | No | `INFO` | Logging level |

The `.env` file is **not** loaded automatically — do not commit it.

## Docker

```bash
docker compose up -d
```

Requires a `stack.env` file with the environment variables above.

## Project Structure

```
src/
├── main.py        # Entrypoint — Application builder + polling
├── db.py          # SQLite database (schema init, CRUD)
├── handlers.py    # All command and conversation handlers
├── scheduler.py   # Availability computation logic
├── notifier.py    # Sitter notification helper
├── geocoder.py    # Geoapify geocoding, reverse geocoding, routing
└── strings.py     # Italian UI strings and formatters
```

## Database

SQLite via stdlib `sqlite3`. Contains `schedule` and `bookings` tables.

## Booking Flow

1. `/book` → enter address (geocoded via Geoapify, filtered to Campania)
2. Confirm address → 14-day date picker (greyed out = no schedule that day)
3. Pick a date → available `:00` start times
4. Pick a start time → duration options (1h, 2h, ...)
5. Enter number of children → confirm → booking saved, sitter notified

No persistence, no webhooks — polling only.

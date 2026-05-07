import logging
import re
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import db
import scheduler as sch
from notifier import SITTER_USER_ID, notify_sitter

DATE, START_TIME, DURATION, CONFIRM = range(4)

HELP_TEXT = (
    "Available commands:\n"
    "/start - Start the bot\n"
    "/help - Show this help message\n"
    "/book - Book a reservation with the sitter\n"
    "/my_bookings - View your upcoming bookings\n"
    "/cancel <id> - Cancel a booking\n"
    "/available [date] - Show available time slots\n"
)

SITTER_HELP = (
    "\nSitter commands:\n"
    "/set_schedule - Configure the weekly schedule\n"
    "/admin - View all upcoming bookings\n"
)


def _is_sitter(update: Update) -> bool:
    return str(update.effective_user.id) == SITTER_USER_ID


# ── /start ──────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("User %d (%s) ran /start", user.id, user.first_name)
    text = (
        f"Hello {user.first_name}! I'm the baby sitter reservation bot.\n\n"
        "Use /help to see available commands or /book to make a reservation."
    )
    await update.message.reply_text(text)


# ── /help ───────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    is_sitter = _is_sitter(update)
    logger.info("User %d (%s) ran /help (sitter=%s)", user.id, user.first_name, is_sitter)
    text = HELP_TEXT
    if is_sitter:
        text += SITTER_HELP
    await update.message.reply_text(text)


# ── /book conversation ──────────────────────────────────────────────────

async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    schedule = db.get_schedule()
    if not schedule:
        logger.info("User %d (%s) tried /book but no schedule exists", user.id, user.first_name)
        await update.message.reply_text(
            "No schedule has been configured yet. Please try again later."
        )
        return ConversationHandler.END

    logger.info("User %d (%s) started /book", user.id, user.first_name)

    today = date.today()
    keyboard = []
    row = []

    for i in range(14):
        d = today + timedelta(days=i)
        weekday = d.weekday()
        if not any(s["day_of_week"] == weekday for s in schedule):
            continue
        bookings = db.get_bookings_for_date(d.isoformat())
        now_str = datetime.now().strftime("%H:%M") if d == today else None
        starts = sch.get_available_start_times(schedule, bookings, d, current_time=now_str)
        if not starts:
            continue
        label = d.strftime("%a %d")
        row.append(
            InlineKeyboardButton(label, callback_data=f"date_{d.isoformat()}")
        )

        if len(row) == 4:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    if not keyboard:
        await update.message.reply_text(
            "No available slots in the next 14 days. Please try again later."
        )
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a date (available slots only):", reply_markup=reply_markup)
    return DATE


async def _show_date_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("User %d returning to date picker", update.effective_user.id)
    schedule = db.get_schedule()
    today = date.today()
    keyboard = []
    row = []

    for i in range(14):
        d = today + timedelta(days=i)
        weekday = d.weekday()
        if not any(s["day_of_week"] == weekday for s in schedule):
            continue
        bookings = db.get_bookings_for_date(d.isoformat())
        now_str = datetime.now().strftime("%H:%M") if d == today else None
        starts = sch.get_available_start_times(schedule, bookings, d, current_time=now_str)
        if not starts:
            continue
        label = d.strftime("%a %d")
        row.append(
            InlineKeyboardButton(label, callback_data=f"date_{d.isoformat()}")
        )

        if len(row) == 4:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    if not keyboard:
        query = update.callback_query
        await query.edit_message_text(
            "No available slots in the next 14 days. Please try again later."
        )
        context.user_data.clear()
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    await query.edit_message_text("Select a date (available slots only):", reply_markup=reply_markup)
    return DATE


async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data
    if data == "noop":
        logger.info("User %d tapped a disabled date", user.id)
        await query.answer("No availability this day.", show_alert=False)
        return DATE
    if data == "back":
        return await _show_date_picker(update, context)

    date_str = data.split("_", 1)[1]
    logger.info("User %d selected date %s", user.id, date_str)
    context.user_data["booking_date"] = date_str
    return await _show_time_picker(update, context, date_str)


async def _show_time_picker(
    update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str
) -> int:
    user = update.effective_user
    d = date.fromisoformat(date_str)
    schedule = db.get_schedule()
    bookings = db.get_bookings_for_date(date_str)

    now_str = datetime.now().strftime("%H:%M") if d == date.today() else None
    starts = sch.get_available_start_times(schedule, bookings, d, current_time=now_str)
    logger.info("User %d: time picker for %s (%d slots)", user.id, date_str, len(starts))

    if not starts:
        keyboard = [[InlineKeyboardButton("◀ Back", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query = update.callback_query
        await query.edit_message_text(
            f"No available slots on {d.strftime('%A, %d %B')}. Pick another date.",
            reply_markup=reply_markup,
        )
        return DATE

    keyboard = []
    row = []
    for t in starts:
        row.append(InlineKeyboardButton(t, callback_data=f"time_{t}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("◀ Back", callback_data="back")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    await query.edit_message_text(
        f"Available times for {d.strftime('%A, %d %B')}:",
        reply_markup=reply_markup,
    )
    return START_TIME


async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data
    if data == "back":
        logger.info("User %d went back from time picker", user.id)
        return await _show_date_picker(update, context)

    start_time = data.split("_", 1)[1]
    logger.info("User %d selected start time %s", user.id, start_time)
    context.user_data["booking_start"] = start_time

    date_str = context.user_data["booking_date"]
    return await _show_duration_picker(update, context, date_str, start_time)


async def _show_duration_picker(
    update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str, start_time: str
) -> int:
    user = update.effective_user
    d = date.fromisoformat(date_str)
    schedule = db.get_schedule()
    bookings = db.get_bookings_for_date(date_str)

    options = sch.get_duration_options(schedule, bookings, d, start_time)
    logger.info("User %d: duration picker for %s at %s (%d options)", user.id, date_str, start_time, len(options))

    if not options:
        keyboard = [[InlineKeyboardButton("◀ Back", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query = update.callback_query
        await query.edit_message_text(
            "No duration available for this start time. Please pick another time.",
            reply_markup=reply_markup,
        )
        return START_TIME

    keyboard = []
    for s, e in options:
        hours = (sch._to_min(e) - sch._to_min(s)) // 60
        label = f"{hours}h (until {e})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"dur_{e}")])

    keyboard.append([InlineKeyboardButton("◀ Back", callback_data="back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    await query.edit_message_text(
        f"Duration for {date_str} at {start_time}:",
        reply_markup=reply_markup,
    )
    return DURATION


async def duration_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data
    if data == "back":
        logger.info("User %d went back from duration picker", user.id)
        date_str = context.user_data["booking_date"]
        return await _show_time_picker(update, context, date_str)

    end_time = data.split("_", 1)[1]
    logger.info("User %d selected end time %s", user.id, end_time)
    context.user_data["booking_end"] = end_time
    return await _show_confirmation(update, context)


async def _show_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user = update.effective_user
    date_str = context.user_data["booking_date"]
    start_time = context.user_data["booking_start"]
    end_time = context.user_data["booking_end"]
    logger.info("User %d: showing confirmation for %s %s-%s", user.id, date_str, start_time, end_time)

    d = date.fromisoformat(date_str)
    start_min = sch._to_min(start_time)
    end_min = sch._to_min(end_time)
    hours = (end_min - start_min) // 60

    text = (
        f"📋 Booking Summary\n"
        f"Date: {d.strftime('%A, %d %B %Y')}\n"
        f"Time: {start_time} – {end_time} ({hours} hour{'s' if hours > 1 else ''})\n"
        f"Name: {user.first_name}\n\n"
        f"Confirm?"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ No", callback_data="confirm_no"),
        ],
        [InlineKeyboardButton("◀ Back", callback_data="back")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    await query.edit_message_text(text, reply_markup=reply_markup)
    return CONFIRM


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if query.data == "confirm_no":
        logger.info("User %d declined booking confirmation", user.id)
        await query.edit_message_text("Booking cancelled. Use /book to start over.")
        context.user_data.clear()
        return ConversationHandler.END

    if query.data == "back":
        logger.info("User %d went back from confirmation", user.id)
        date_str = context.user_data["booking_date"]
        start_time = context.user_data["booking_start"]
        return await _show_duration_picker(update, context, date_str, start_time)

    date_str = context.user_data["booking_date"]
    start_time = context.user_data["booking_start"]
    end_time = context.user_data["booking_end"]

    schedule = db.get_schedule()
    bookings = db.get_bookings_for_date(date_str)
    d = date.fromisoformat(date_str)
    now_str = datetime.now().strftime("%H:%M") if d == date.today() else None

    starts = sch.get_available_start_times(schedule, bookings, d, current_time=now_str)
    if start_time not in starts:
        logger.info("User %d booking failed: slot %s on %s no longer available", user.id, start_time, date_str)
        await query.edit_message_text(
            "Sorry, this slot is no longer available. Use /book to start again."
        )
        context.user_data.clear()
        return ConversationHandler.END

    options = sch.get_duration_options(schedule, bookings, d, start_time)
    if (start_time, end_time) not in options:
        logger.info("User %d booking failed: duration %s-%s no longer available", user.id, start_time, end_time)
        await query.edit_message_text(
            "Sorry, this duration is no longer available. Use /book to start again."
        )
        context.user_data.clear()
        return ConversationHandler.END

    booking_id = db.add_booking(
        user.id, user.first_name, date_str, start_time, end_time
    )
    logger.info(
        "User %d (%s) confirmed booking #%d: %s %s-%s",
        user.id, user.first_name, booking_id, date_str, start_time, end_time,
    )

    await query.edit_message_text(
        f"✅ Booking confirmed!\n"
        f"Date: {d.strftime('%A, %d %B %Y')}\n"
        f"Time: {start_time} – {end_time}\n"
        f"Booking ID: #{booking_id}\n\n"
        f"Use /my_bookings to view your bookings or /cancel {booking_id} to cancel."
    )

    await notify_sitter(
        context.bot,
        f"✅ New booking #{booking_id}\n"
        f"Customer: {user.first_name} (ID: {user.id})\n"
        f"Date: {d.strftime('%A, %d %B %Y')}\n"
        f"Time: {start_time} – {end_time}",
    )

    context.user_data.clear()
    return ConversationHandler.END


async def book_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("User %d cancelled booking conversation", update.effective_user.id)
    await update.message.reply_text("Booking cancelled. Use /book to start a new one.")
    return ConversationHandler.END


async def book_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(
        "User %d sent unexpected input during booking: %s",
        update.effective_user.id,
        update.message.text,
    )
    await update.message.reply_text(
        "Please use the buttons to respond, or type /cancel to exit."
    )
    return CONFIRM


book_conv = ConversationHandler(
    entry_points=[CommandHandler("book", book_start)],
    states={
        DATE: [
            CallbackQueryHandler(date_chosen, pattern="^(date_|noop|back)"),
        ],
        START_TIME: [
            CallbackQueryHandler(time_chosen, pattern="^(time_|back)"),
        ],
        DURATION: [
            CallbackQueryHandler(duration_chosen, pattern="^(dur_|back)"),
        ],
        CONFIRM: [
            CallbackQueryHandler(confirm_booking, pattern="^(confirm_yes|confirm_no|back)$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", book_cancel),
        MessageHandler(filters.TEXT & ~filters.COMMAND, book_unexpected),
    ],
)


# ── /my_bookings ────────────────────────────────────────────────────────

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    bookings = db.get_user_bookings(user.id)

    if not bookings:
        logger.info("User %d (%s) viewed bookings: none", user.id, user.first_name)
        await update.message.reply_text("You have no upcoming bookings.")
        return

    logger.info("User %d (%s) viewed %d booking(s)", user.id, user.first_name, len(bookings))
    lines = ["Your upcoming bookings:"]
    for b in bookings:
        d = date.fromisoformat(b["date"])
        lines.append(
            f"  #{b['id']} — {d.strftime('%a, %d %b %Y')} {b['start_time']}–{b['end_time']}"
        )
    lines.append("\nUse /cancel <id> to cancel a booking.")
    await update.message.reply_text("\n".join(lines))


# ── /cancel ─────────────────────────────────────────────────────────────

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    if not args or not args[0].isdigit():
        logger.info("User %d invalid /cancel syntax: %s", user.id, args)
        await update.message.reply_text("Usage: /cancel <booking_id>")
        return

    booking_id = int(args[0])
    is_sitter = _is_sitter(update)

    success = db.cancel_booking(booking_id, user.id, sitter_mode=is_sitter)
    if success:
        logger.info("User %d (%s) cancelled booking #%d", user.id, user.first_name, booking_id)
        await update.message.reply_text(f"Booking #{booking_id} has been cancelled.")
        if not is_sitter:
            await notify_sitter(
                context.bot,
                f"❌ Booking #{booking_id} cancelled by customer {user.first_name}.",
            )
    else:
        logger.info("User %d failed to cancel booking #%d: not found or not owned", user.id, booking_id)
        await update.message.reply_text(
            "Could not cancel. Check the booking ID and that it belongs to you."
        )


# ── /available ──────────────────────────────────────────────────────────

async def available(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    target = date.today()
    if args:
        try:
            target = date.fromisoformat(args[0])
        except ValueError:
            logger.info("User %d invalid /available date: %s", user.id, args[0])
            await update.message.reply_text(
                "Invalid date. Use YYYY-MM-DD format, e.g. /available 2026-05-10"
            )
            return

    schedule = db.get_schedule()
    if not schedule:
        await update.message.reply_text(
            "No schedule has been configured yet."
        )
        return

    bookings = db.get_bookings_for_date(target.isoformat())
    now_str = datetime.now().strftime("%H:%M") if target == date.today() else None
    starts = sch.get_available_start_times(schedule, bookings, target, current_time=now_str)
    logger.info("User %d checked availability for %s: %d slots", user.id, target.isoformat(), len(starts))

    if not starts:
        weekday = target.weekday()
        has_sched = any(s["day_of_week"] == weekday for s in schedule)
        if not has_sched:
            await update.message.reply_text(
                f"No schedule for {target.strftime('%A, %d %B')}."
            )
        else:
            await update.message.reply_text(
                f"No available slots on {target.strftime('%A, %d %B')}."
            )
        return

    lines = [f"Available slots for {target.strftime('%A, %d %B')}:"]
    for t in starts:
        lines.append(f"  • {t}")
    await update.message.reply_text("\n".join(lines))


# ── /set_schedule conversation ──────────────────────────────────────────

SCHEDULE_DAYS, SCHEDULE_DAY_ACTION, SCHEDULE_START_TIME, SCHEDULE_END_TIME, SCHEDULE_CONFIRM = range(5)

DAY_ABBRS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _day_label(day_idx: int, windows: list[tuple[str, str]]) -> str:
    abbr = DAY_ABBRS[day_idx]
    if not windows:
        return f"{abbr}: \u2014"
    s, e = windows[0]
    label = f"{abbr} {s}\u2013{e}"
    if len(windows) > 1:
        label += "\u2026"
    return label


async def set_schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_sitter(update):
        logger.info("Non-sitter user %d tried /set_schedule", update.effective_user.id)
        await update.message.reply_text("This command is only for the sitter.")
        return ConversationHandler.END

    logger.info("Sitter started interactive schedule edit")
    current = db.get_schedule()
    draft: dict[int, list[tuple[str, str]]] = {}
    for s in current:
        draft.setdefault(s["day_of_week"], []).append((s["start_time"], s["end_time"]))
    context.user_data["schedule_draft"] = draft

    keyboard = []
    row = []
    for i in range(7):
        windows = draft.get(i, [])
        row.append(InlineKeyboardButton(_day_label(i, windows), callback_data=f"sched_day_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("\u2705 Done", callback_data="sched_done")])

    await update.message.reply_text(
        "Tap a day to configure its time windows, then tap Done:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SCHEDULE_DAYS


async def schedule_day_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "sched_done":
        return await _show_schedule_confirm(update, context)

    day_idx = int(data.split("_")[-1])
    context.user_data["schedule_selected_day"] = day_idx
    return await _show_day_action(update, context)


async def _show_day_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    day_idx = context.user_data["schedule_selected_day"]
    draft = context.user_data["schedule_draft"]
    windows = draft.get(day_idx, [])

    lines = [f"<b>{sch.DISPLAY_NAMES[day_idx]}</b>"]
    if windows:
        for s, e in windows:
            lines.append(f"  {s} \u2013 {e}")
    else:
        lines.append("  No windows configured")

    keyboard = [[InlineKeyboardButton("\u2795 Add window", callback_data="sched_add")]]
    if windows:
        keyboard.append([InlineKeyboardButton("\U0001f5d1 Clear day", callback_data="sched_clear")])
    keyboard.append([InlineKeyboardButton("\U0001f519 Back to days", callback_data="sched_back_days")])

    await update.callback_query.edit_message_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )
    return SCHEDULE_DAY_ACTION


async def schedule_day_action_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "sched_back_days":
        return await _show_schedule_day_selector(update, context)

    if data == "sched_clear":
        day_idx = context.user_data["schedule_selected_day"]
        context.user_data["schedule_draft"].pop(day_idx, None)
        return await _show_day_action(update, context)

    if data == "sched_add":
        return await _show_start_time_picker(update, context)

    return SCHEDULE_DAY_ACTION


async def _show_schedule_day_selector(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = context.user_data["schedule_draft"]
    keyboard = []
    row = []
    for i in range(7):
        windows = draft.get(i, [])
        row.append(InlineKeyboardButton(_day_label(i, windows), callback_data=f"sched_day_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("\u2705 Done", callback_data="sched_done")])

    await update.callback_query.edit_message_text(
        "Tap a day to configure its time windows, then tap Done:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SCHEDULE_DAYS


async def _show_start_time_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = []
    row = []
    for h in range(24):
        row.append(InlineKeyboardButton(f"{h:02d}:00", callback_data=f"sched_st_{h:02d}"))
        if len(row) == 6:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("\U0001f519 Back", callback_data="sched_back_action")])

    await update.callback_query.edit_message_text(
        "Select start time:", reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SCHEDULE_START_TIME


async def schedule_start_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "sched_back_action":
        return await _show_day_action(update, context)

    start_hour = int(data.split("_")[-1])
    context.user_data["schedule_start_hour"] = start_hour
    return await _show_end_time_picker(update, context)


async def _show_end_time_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    start_hour = context.user_data["schedule_start_hour"]
    keyboard = []
    row = []
    for h in range(start_hour + 1, 24):
        row.append(InlineKeyboardButton(f"{h:02d}:00", callback_data=f"sched_en_{h:02d}"))
        if len(row) == 6:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("\U0001f519 Back", callback_data="sched_back_start")])

    await update.callback_query.edit_message_text(
        f"Start: {start_hour:02d}:00\nSelect end time:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SCHEDULE_END_TIME


async def schedule_end_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "sched_back_start":
        return await _show_start_time_picker(update, context)

    end_hour = int(data.split("_")[-1])
    day_idx = context.user_data["schedule_selected_day"]
    start_hour = context.user_data["schedule_start_hour"]

    draft = context.user_data["schedule_draft"]
    draft.setdefault(day_idx, []).append((f"{start_hour:02d}:00", f"{end_hour:02d}:00"))

    return await _show_day_action(update, context)


async def _show_schedule_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = context.user_data["schedule_draft"]
    lines = ["<b>Schedule preview:</b>"]
    for day_idx in range(7):
        windows = draft.get(day_idx, [])
        if windows:
            times = ", ".join(f"{s}\u2013{e}" for s, e in windows)
            lines.append(f"{sch.DISPLAY_NAMES[day_idx]}: {times}")
        else:
            lines.append(f"{sch.DISPLAY_NAMES[day_idx]}: OFF")
    lines.append("")
    lines.append("Save this schedule?")

    keyboard = [
        [
            InlineKeyboardButton("\u2705 Yes", callback_data="sched_save_yes"),
            InlineKeyboardButton("\u274c No", callback_data="sched_save_no"),
        ],
        [InlineKeyboardButton("\U0001f519 Back", callback_data="sched_back_days")],
    ]

    await update.callback_query.edit_message_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )
    return SCHEDULE_CONFIRM


async def schedule_confirm_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "sched_back_days":
        return await _show_schedule_day_selector(update, context)

    if data == "sched_save_no":
        logger.info("Sitter declined schedule save")
        await query.edit_message_text("Schedule unchanged. Use /set_schedule to start over.")
        context.user_data.clear()
        return ConversationHandler.END

    draft = context.user_data["schedule_draft"]
    slots = []
    for day_idx, windows in draft.items():
        for s, e in windows:
            slots.append((day_idx, s, e))

    if not slots:
        await query.edit_message_text("No time windows configured. Schedule unchanged.")
        context.user_data.clear()
        return ConversationHandler.END

    db.set_schedule(slots)
    logger.info("Sitter updated schedule with %d window(s)", len(slots))
    new_schedule = db.get_schedule()
    await query.edit_message_text(
        "\u2705 Schedule updated!\n\n" + sch.format_schedule(new_schedule)
    )
    context.user_data.clear()
    return ConversationHandler.END


async def set_schedule_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Sitter cancelled schedule edit")
    await update.message.reply_text("Schedule unchanged.")
    context.user_data.clear()
    return ConversationHandler.END


async def set_schedule_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(
        "Sitter sent unexpected input during schedule edit: %s",
        update.message.text,
    )
    await update.message.reply_text(
        "Please use the buttons above, or type /cancel to exit."
    )
    return SCHEDULE_DAYS


set_schedule_conv = ConversationHandler(
    entry_points=[CommandHandler("set_schedule", set_schedule_start)],
    states={
        SCHEDULE_DAYS: [
            CallbackQueryHandler(schedule_day_chosen, pattern="^sched_day_|^sched_done$"),
        ],
        SCHEDULE_DAY_ACTION: [
            CallbackQueryHandler(schedule_day_action_chosen, pattern="^sched_add$|^sched_clear$|^sched_back_days$"),
        ],
        SCHEDULE_START_TIME: [
            CallbackQueryHandler(schedule_start_chosen, pattern="^sched_st_|^sched_back_action$"),
        ],
        SCHEDULE_END_TIME: [
            CallbackQueryHandler(schedule_end_chosen, pattern="^sched_en_|^sched_back_start$"),
        ],
        SCHEDULE_CONFIRM: [
            CallbackQueryHandler(schedule_confirm_chosen, pattern="^sched_save_|^sched_back_days$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", set_schedule_cancel),
        MessageHandler(filters.TEXT & ~filters.COMMAND, set_schedule_unexpected),
    ],
)


# ── /admin ──────────────────────────────────────────────────────────────

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_sitter(update):
        logger.info("Non-sitter user %d tried /admin", update.effective_user.id)
        await update.message.reply_text("This command is only for the sitter.")
        return

    bookings = db.get_all_bookings()
    if not bookings:
        logger.info("Sitter viewed admin: no upcoming bookings")
        await update.message.reply_text("No upcoming bookings.")
        return

    logger.info("Sitter viewed admin: %d upcoming booking(s)", len(bookings))
    lines = ["📋 All upcoming confirmed bookings:"]
    for b in bookings:
        d = date.fromisoformat(b["date"])
        lines.append(
            f"  #{b['id']} — {d.strftime('%a, %d %b %Y')} "
            f"{b['start_time']}–{b['end_time']} | "
            f"{b['user_name']} (ID: {b['user_id']})"
        )
    await update.message.reply_text("\n".join(lines))

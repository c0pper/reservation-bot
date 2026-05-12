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
import strings
import scheduler as sch
import geocoder
from notifier import SITTER_USER_IDS, notify_sitter

DATE, LOCATION, START_TIME, DURATION, CHILDREN, CONFIRM = range(6)
CANCEL_SELECT, CANCEL_CONFIRM = range(2)


def _is_sitter(update: Update) -> bool:
    return str(update.effective_user.id) in SITTER_USER_IDS


# ── /start ──────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info("User %d (%s) ran /start", user.id, user.first_name)
    await update.message.reply_text(strings.fmt_start(user.first_name))


# ── /help ───────────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    is_sitter = _is_sitter(update)
    logger.info("User %d (%s) ran /help (sitter=%s)", user.id, user.first_name, is_sitter)
    text = strings.HELP_TEXT
    if is_sitter:
        text += strings.SITTER_HELP
    await update.message.reply_text(text)


# ── /book conversation ──────────────────────────────────────────────────

async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    schedule = db.get_schedule()
    if not schedule:
        logger.info("User %d (%s) tried /book but no schedule exists", user.id, user.first_name)
        await update.message.reply_text(strings.NO_SCHEDULE)
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
        label = strings.fmt_date_short(d)
        row.append(
            InlineKeyboardButton(label, callback_data=f"date_{d.isoformat()}")
        )

        if len(row) == 4:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    if not keyboard:
        await update.message.reply_text(strings.NO_SLOTS_14)
        return ConversationHandler.END

    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL, callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(strings.SELECT_DATE, reply_markup=reply_markup)
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
        label = strings.fmt_date_short(d)
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
        await query.edit_message_text(strings.NO_SLOTS_14)
        context.user_data.clear()
        return ConversationHandler.END

    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL, callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    await query.edit_message_text(strings.SELECT_DATE, reply_markup=reply_markup)
    return DATE


def _build_date_keyboard(schedule: list[dict]) -> list[list[InlineKeyboardButton]]:
    keyboard = []
    row = []
    today = date.today()

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
        label = strings.fmt_date_short(d)
        row.append(
            InlineKeyboardButton(label, callback_data=f"date_{d.isoformat()}")
        )

        if len(row) == 4:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)
    return keyboard


async def _show_date_picker_as_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    schedule = db.get_schedule()
    keyboard = _build_date_keyboard(schedule)

    if not keyboard:
        await update.message.reply_text(strings.NO_SLOTS_14)
        context.user_data.clear()
        return ConversationHandler.END

    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL, callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(strings.SELECT_DATE, reply_markup=reply_markup)
    else:
        await update.message.reply_text(strings.SELECT_DATE, reply_markup=reply_markup)
    return DATE


async def _show_location_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.edit_message_reply_markup(None)
        await query.message.reply_text(strings.SELECT_LOCATION)
    else:
        await update.message.reply_text(strings.SELECT_LOCATION)
    return LOCATION


async def location_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    text = update.message.text.strip()

    if text.lower() == "indietro":
        logger.info("User %d went back from location picker", user.id)
        return await _show_date_picker_as_new_message(update, context)

    logger.info("User %d entered address: %s", user.id, text)
    context.user_data["booking_address_raw"] = text

    results = await geocoder.forward_geocode(text)
    if not results:
        logger.info("User %d address not in Campania or geocode failed: %s", user.id, text)
        await update.message.reply_text(strings.LOCATION_NOT_FOUND)
        return LOCATION

    if len(results) == 1:
        lat, lon, formatted, city, postcode = results[0]
        context.user_data["booking_lat"] = lat
        context.user_data["booking_lon"] = lon
        context.user_data["booking_address"] = text

        logger.info("User %d geocoded address: %s (%.6f, %.6f)", user.id, text, lat, lon)
        await update.message.reply_text(strings.CONFIRM_LOCATION.format(address=text))
        date_str = context.user_data["booking_date"]
        return await _show_time_picker(update, context, date_str)

    context.user_data["booking_location_results"] = results
    keyboard = []
    for i, (_, _, _, city, postcode) in enumerate(results):
        label = f"{text} — {city} ({postcode})" if city and postcode else text
        keyboard.append([InlineKeyboardButton(label, callback_data=f"loc_{i}")])
    keyboard.append([
        InlineKeyboardButton(strings.BTN_BACK, callback_data="back"),
        InlineKeyboardButton(strings.BTN_CANCEL, callback_data="cancel"),
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(strings.MULTIPLE_LOCATIONS, reply_markup=reply_markup)
    return LOCATION


async def location_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

    if data == "cancel":
        return await _booking_cancel(update, context)

    if data == "back":
        return await _show_location_picker(update, context)

    idx = int(data[4:])
    results = context.user_data["booking_location_results"]
    lat, lon, formatted, city, postcode = results[idx]
    raw = context.user_data.get("booking_address_raw", formatted)

    context.user_data["booking_lat"] = lat
    context.user_data["booking_lon"] = lon
    context.user_data["booking_address"] = raw

    logger.info("User %d selected address: %s (%.6f, %.6f)", user.id, raw, lat, lon)
    await query.edit_message_reply_markup(None)
    await query.message.reply_text(strings.CONFIRM_LOCATION.format(address=raw))
    date_str = context.user_data["booking_date"]
    return await _show_time_picker(update, context, date_str)




async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data
    if data == "cancel":
        return await _booking_cancel(update, context)
    if data == "noop":
        logger.info("User %d tapped a disabled date", user.id)
        await query.answer(strings.NO_AVAILABILITY_DAY, show_alert=False)
        return DATE
    if data == "back":
        return await _show_date_picker(update, context)

    date_str = data.split("_", 1)[1]
    logger.info("User %d selected date %s", user.id, date_str)
    context.user_data["booking_date"] = date_str
    return await _show_location_picker(update, context)


async def _filter_starts_by_transit(
    starts: list[str],
    bookings: list[dict],
    dest_lat: float,
    dest_lon: float,
) -> list[str]:
    confirmed = [b for b in bookings if b.get("latitude") is not None and b["status"] == "confirmed"]
    if not confirmed:
        return starts

    transit_cache: dict[tuple[float, float], float] = {}
    result = []

    def find_prev(start_min: int) -> dict | None:
        prev = None
        for b in confirmed:
            if sch._to_min(b["end_time"]) <= start_min:
                prev = b
        return prev

    for t in starts:
        t_min = sch._to_min(t)
        prev = find_prev(t_min)
        if prev is None:
            result.append(t)
            continue

        key = (prev["latitude"], prev["longitude"])
        if key not in transit_cache:
            travel_seconds = await geocoder.get_transit_time(
                prev["latitude"], prev["longitude"], dest_lat, dest_lon, mode="drive"
            )
            transit_cache[key] = travel_seconds

        travel_time = transit_cache[key]
        if travel_time is None:
            result.append(t)
            continue

        travel_min = travel_time / 60
        prev_end_min = sch._to_min(prev["end_time"])
        if t_min >= prev_end_min + travel_min:
            result.append(t)

    return result


async def _filter_durations_by_transit(
    options: list[tuple[str, str]],
    bookings: list[dict],
    start_time: str,
    current_lat: float,
    current_lon: float,
) -> list[tuple[str, str]]:
    start_min = sch._to_min(start_time)
    confirmed = [
        b for b in bookings
        if b.get("latitude") is not None and b["status"] == "confirmed" and sch._to_min(b["start_time"]) > start_min
    ]
    if not confirmed:
        return options

    next_b = min(confirmed, key=lambda b: sch._to_min(b["start_time"]))
    travel_seconds = await geocoder.get_transit_time(
        current_lat, current_lon, next_b["latitude"], next_b["longitude"], mode="drive"
    )
    if travel_seconds is None:
        return options

    travel_min = travel_seconds / 60
    next_start_min = sch._to_min(next_b["start_time"])
    max_allowed_end = next_start_min - travel_min

    filtered = []
    for s, e in options:
        if sch._to_min(e) <= max_allowed_end:
            filtered.append((s, e))

    return filtered


async def _show_time_picker(
    update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str
) -> int:
    user = update.effective_user
    d = date.fromisoformat(date_str)
    schedule = db.get_schedule()
    bookings = db.get_bookings_for_date(date_str)

    now_str = datetime.now().strftime("%H:%M") if d == date.today() else None
    starts = sch.get_available_start_times(schedule, bookings, d, current_time=now_str)

    new_lat = context.user_data.get("booking_lat")
    new_lon = context.user_data.get("booking_lon")

    logger.info("User %d: filtering time slots by transit for %s (dest: %.6f, %.6f)", user.id, date_str, new_lat, new_lon)
    if new_lat is not None and new_lon is not None:
        starts = await _filter_starts_by_transit(starts, bookings, new_lat, new_lon)
        logger.info("User %d: filtered time slots by transit for %s (dest: %.6f, %.6f): %d", user.id, date_str, new_lat, new_lon, len(starts))

    logger.info("User %d: time picker for %s (%d slots)", user.id, date_str, len(starts))

    if not starts:
        keyboard = [[InlineKeyboardButton(strings.BTN_BACK, callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = strings.NO_SLOTS_DATE.format(date=strings.fmt_date_weekday_long(d))
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
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
    keyboard.append([InlineKeyboardButton(strings.BTN_BACK, callback_data="back"), InlineKeyboardButton(strings.BTN_CANCEL, callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = strings.AVAILABLE_TIMES.format(date=strings.fmt_date_weekday_long(d))
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
    return START_TIME


async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data
    if data == "cancel":
        return await _booking_cancel(update, context)
    if data == "back":
        logger.info("User %d went back from time picker", user.id)
        return await _show_location_picker(update, context)

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

    current_lat = context.user_data.get("booking_lat")
    current_lon = context.user_data.get("booking_lon")
    logger.info(f"User {user.id}: filtering durations by transit for {date_str} at {start_time} (dest: {current_lat}, {current_lon}) ({len(options)} options before filtering)")
    if current_lat is not None and current_lon is not None:
        options = await _filter_durations_by_transit(options, bookings, start_time, current_lat, current_lon)
        logger.info(f"User {user.id}: filtered durations by transit for {date_str} at {start_time}: {len(options)}")

    logger.info(f"User {user.id}: duration picker for {date_str} at {start_time}: {len(options)}")

    if not options:
        keyboard = [[InlineKeyboardButton(strings.BTN_BACK, callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query = update.callback_query
        await query.edit_message_text(
            strings.NO_DURATION,
            reply_markup=reply_markup,
        )
        return START_TIME

    keyboard = []
    for s, e in options:
        hours = (sch._to_min(e) - sch._to_min(s)) // 60
        label = f"{hours}h (fino alle {e})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"dur_{e}")])

    keyboard.append([InlineKeyboardButton(strings.BTN_BACK, callback_data="back"), InlineKeyboardButton(strings.BTN_CANCEL, callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    await query.edit_message_text(
        strings.DURATION_FOR.format(date=date_str, time=start_time),
        reply_markup=reply_markup,
    )
    return DURATION


async def duration_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data
    if data == "cancel":
        return await _booking_cancel(update, context)
    if data == "back":
        logger.info("User %d went back from duration picker", user.id)
        date_str = context.user_data["booking_date"]
        return await _show_time_picker(update, context, date_str)

    end_time = data.split("_", 1)[1]
    logger.info("User %d selected end time %s", user.id, end_time)
    context.user_data["booking_end"] = end_time
    return await _show_children_picker(update, context)


async def _show_children_picker(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    keyboard = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(str(i), callback_data=f"child_{i}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(strings.BTN_BACK, callback_data="back"), InlineKeyboardButton(strings.BTN_CANCEL, callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        strings.HOW_MANY_CHILDREN,
        reply_markup=reply_markup,
    )
    return CHILDREN


async def children_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data
    if data == "cancel":
        return await _booking_cancel(update, context)
    if data == "back":
        logger.info("User %d went back from children picker", user.id)
        date_str = context.user_data["booking_date"]
        start_time = context.user_data["booking_start"]
        return await _show_duration_picker(update, context, date_str, start_time)

    children = int(data.split("_", 1)[1])
    logger.info("User %d selected %d children", user.id, children)
    context.user_data["booking_children"] = children
    return await _show_confirmation(update, context)


async def _show_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user = update.effective_user
    date_str = context.user_data["booking_date"]
    start_time = context.user_data["booking_start"]
    end_time = context.user_data["booking_end"]
    children = context.user_data.get("booking_children", 1)
    address = context.user_data.get("booking_address", "—")
    logger.info("User %d: showing confirmation for %s %s-%s (%d children)", user.id, date_str, start_time, end_time, children)

    d = date.fromisoformat(date_str)
    start_min = sch._to_min(start_time)
    end_min = sch._to_min(end_time)
    hours = (end_min - start_min) // 60

    text = strings.BOOKING_SUMMARY.format(
        date=strings.fmt_date_long(d),
        start=start_time,
        end=end_time,
        hours=hours,
        h_label=strings.h_label(hours),
        children=children,
        name=user.first_name,
        address=address,
    )

    keyboard = [
        [
            InlineKeyboardButton(strings.BTN_YES, callback_data="confirm_yes"),
            InlineKeyboardButton(strings.BTN_NO, callback_data="confirm_no"),
        ],
        [InlineKeyboardButton(strings.BTN_BACK, callback_data="back"), InlineKeyboardButton(strings.BTN_CANCEL, callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    await query.edit_message_text(text, reply_markup=reply_markup)
    return CONFIRM


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if query.data == "cancel":
        return await _booking_cancel(update, context)

    if query.data == "confirm_no":
        logger.info("User %d declined booking confirmation", user.id)
        await query.edit_message_text(strings.BOOKING_CANCELLED_OVER)
        context.user_data.clear()
        return ConversationHandler.END

    if query.data == "back":
        logger.info("User %d went back from confirmation", user.id)
        return await _show_children_picker(update, context)

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
        await query.edit_message_text(strings.SLOT_UNAVAILABLE)
        context.user_data.clear()
        return ConversationHandler.END

    options = sch.get_duration_options(schedule, bookings, d, start_time)
    if (start_time, end_time) not in options:
        logger.info("User %d booking failed: duration %s-%s no longer available", user.id, start_time, end_time)
        await query.edit_message_text(strings.DURATION_UNAVAILABLE)
        context.user_data.clear()
        return ConversationHandler.END

    children = context.user_data.get("booking_children", 1)
    lat = context.user_data.get("booking_lat")
    lon = context.user_data.get("booking_lon")
    address = context.user_data.get("booking_address")
    booking_id = db.add_booking(
        user.id, user.first_name, date_str, start_time, end_time, children, lat, lon, address
    )
    logger.info(
        "User %d (%s) confirmed booking #%d: %s %s-%s",
        user.id, user.first_name, booking_id, date_str, start_time, end_time,
    )

    await query.edit_message_text(
        strings.BOOKING_CONFIRMED_TXT.format(
            date=strings.fmt_date_long(d),
            start=start_time,
            end=end_time,
            children=children,
            id=booking_id,
            address=address or "—",
        )
    )
    if lat and lon:
        await context.bot.send_location(chat_id=user.id, latitude=lat, longitude=lon)

    await notify_sitter(
        context.bot,
        strings.SITTER_NEW_BOOKING.format(
            id=booking_id,
            name=user.first_name,
            uid=user.id,
            date=strings.fmt_date_long(d),
            start=start_time,
            end=end_time,
            children=children,
            address=address or "—",
        ),
        latitude=lat,
        longitude=lon,
    )

    context.user_data.clear()
    return ConversationHandler.END


async def book_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("User %d cancelled booking conversation", update.effective_user.id)
    await update.message.reply_text(strings.BOOKING_CANCELLED_NEW)
    return ConversationHandler.END


async def _booking_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    logger.info("User %d cancelled booking via button", update.effective_user.id)
    await query.edit_message_text(strings.BOOKING_CANCELLED_OVER)
    context.user_data.clear()
    return ConversationHandler.END


async def book_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(
        "User %d sent unexpected input during booking: %s",
        update.effective_user.id,
        update.message.text,
    )
    await update.message.reply_text(strings.USE_BUTTONS_BOOK)
    return CONFIRM


book_conv = ConversationHandler(
    entry_points=[CommandHandler("book", book_start)],
    states={
        DATE: [
            CallbackQueryHandler(date_chosen, pattern="^(date_|noop|back|cancel)"),
        ],
        LOCATION: [
            CallbackQueryHandler(location_chosen, pattern="^(loc_\\d+|back|cancel)$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, location_received),
        ],
        START_TIME: [
            CallbackQueryHandler(time_chosen, pattern="^(time_|back|cancel)"),
        ],
        DURATION: [
            CallbackQueryHandler(duration_chosen, pattern="^(dur_|back|cancel)"),
        ],
        CHILDREN: [
            CallbackQueryHandler(children_chosen, pattern="^(child_|back|cancel)"),
        ],
        CONFIRM: [
            CallbackQueryHandler(confirm_booking, pattern="^(confirm_yes|confirm_no|back|cancel)$"),
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
        await update.message.reply_text(strings.NO_BOOKINGS)
        return

    logger.info("User %d (%s) viewed %d booking(s)", user.id, user.first_name, len(bookings))
    lines = [strings.YOUR_BOOKINGS]
    for b in bookings:
        d = date.fromisoformat(b["date"])
        c = b.get("children", 1)
        addr = b.get("address") or "—"
        lines.append(
            f"  #{b['id']} \u2014 {strings.fmt_date_abbr_long(d)} {b['start_time']}\u2013{b['end_time']} ({c} {strings.child_label(c)}) \u2014 📍 {addr}"
        )
    lines.append(strings.CANCEL_HINT)
    await update.message.reply_text("\n".join(lines))


# ── /cancel conversation ────────────────────────────────────────────────

async def cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    is_sitter = _is_sitter(update)

    if is_sitter:
        bookings = db.get_all_bookings()
    else:
        bookings = db.get_user_bookings(user.id)

    if not bookings:
        logger.info("User %d (%s) ran /cancel: no bookings", user.id, user.first_name)
        await update.message.reply_text(strings.NO_BOOKINGS_CANCEL)
        return ConversationHandler.END

    logger.info(
        "User %d (%s) started /cancel (%d bookings)", user.id, user.first_name, len(bookings)
    )

    keyboard = []
    for b in bookings:
        d = date.fromisoformat(b["date"])
        c = b.get("children", 1)
        label = f"#{b['id']} \u2014 {strings.fmt_date_abbr(d)} {b['start_time']}\u2013{b['end_time']} ({c})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"cancel_sel_{b['id']}")])

    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL_ALL, callback_data="cancel_all")])
    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL_EXIT, callback_data="cancel_exit")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(strings.SELECT_BOOKING_CANCEL, reply_markup=reply_markup)
    return CANCEL_SELECT


async def cancel_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data
    if data == "cancel_exit":
        logger.info("User %d exited cancel flow", user.id)
        await query.edit_message_text(strings.CANCELLATION_ABORTED)
        context.user_data.clear()
        return ConversationHandler.END

    if data == "cancel_all":
        logger.info("User %d selected cancel all", user.id)
        context.user_data["cancel_all"] = True

        keyboard = [
            [
                InlineKeyboardButton(strings.BTN_YES_CANCEL, callback_data="cancel_all_yes"),
                InlineKeyboardButton(strings.BTN_NO_BACK, callback_data="cancel_all_no"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(strings.CANCEL_ALL_PROMPT, reply_markup=reply_markup)
        return CANCEL_CONFIRM

    booking_id = int(data.split("_")[-1])
    context.user_data["cancel_booking_id"] = booking_id
    context.user_data["cancel_is_sitter"] = _is_sitter(update)

    if _is_sitter(update):
        bookings = db.get_all_bookings()
    else:
        bookings = db.get_user_bookings(user.id)

    booking = next((b for b in bookings if b["id"] == booking_id), None)
    if not booking:
        await query.edit_message_text(strings.BOOKING_UNAVAILABLE)
        context.user_data.clear()
        return ConversationHandler.END

    d = date.fromisoformat(booking["date"])
    c = booking.get("children", 1)
    text = strings.CANCEL_THIS_BOOKING.format(
        id=booking["id"],
        date=strings.fmt_date_long(d),
        start=booking["start_time"],
        end=booking["end_time"],
        children=f"{c} {strings.child_label(c)}",
    )

    keyboard = [
        [
            InlineKeyboardButton(strings.BTN_YES_CANCEL, callback_data="cancel_yes"),
            InlineKeyboardButton(strings.BTN_NO_BACK, callback_data="cancel_no"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)
    return CANCEL_CONFIRM


async def cancel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    data = query.data

    if context.user_data.get("cancel_all"):
        if data == "cancel_all_no":
            logger.info("User %d went back from cancel all confirmation", user.id)
            return await _show_cancel_list(update, context)

        if data == "cancel_all_yes":
            count = db.cancel_user_bookings(user.id)
            logger.info("User %d cancelled all %d bookings", user.id, count)
            await query.edit_message_text(strings.BOOKINGS_ALL_CANCELLED.format(count=count))
            if count > 0:
                await notify_sitter(
                    context.bot,
                    strings.SITTER_CANCEL_ALL_NOTE.format(name=user.first_name, count=count),
                )
            context.user_data.clear()
            return ConversationHandler.END

    if data == "cancel_no":
        logger.info("User %d went back from cancel confirmation", user.id)
        return await _show_cancel_list(update, context)

    if data == "cancel_exit":
        await query.edit_message_text(strings.CANCELLATION_ABORTED)
        context.user_data.clear()
        return ConversationHandler.END

    booking_id = context.user_data.get("cancel_booking_id")
    is_sitter = context.user_data.get("cancel_is_sitter", False)

    success = db.cancel_booking(booking_id, user.id, sitter_mode=is_sitter)
    if success:
        logger.info("User %d (%s) cancelled booking #%d", user.id, user.first_name, booking_id)
        await query.edit_message_text(strings.BOOKING_CANCELLED_OK.format(id=booking_id))
        if not is_sitter:
            await notify_sitter(
                context.bot,
                strings.SITTER_CANCEL_NOTE.format(id=booking_id, name=user.first_name),
            )
    else:
        logger.info("User %d failed to cancel booking #%d", user.id, booking_id)
        await query.edit_message_text(strings.CANCEL_FAILED)

    context.user_data.clear()
    return ConversationHandler.END


async def _show_cancel_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    is_sitter = _is_sitter(update)

    if is_sitter:
        bookings = db.get_all_bookings()
    else:
        bookings = db.get_user_bookings(user.id)

    if not bookings:
        query = update.callback_query
        await query.edit_message_text(strings.NO_BOOKINGS_CANCEL)
        context.user_data.clear()
        return ConversationHandler.END

    keyboard = []
    for b in bookings:
        d = date.fromisoformat(b["date"])
        c = b.get("children", 1)
        label = f"#{b['id']} \u2014 {strings.fmt_date_abbr(d)} {b['start_time']}\u2013{b['end_time']} ({c})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"cancel_sel_{b['id']}")])

    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL_ALL, callback_data="cancel_all")])
    keyboard.append([InlineKeyboardButton(strings.BTN_CANCEL_EXIT, callback_data="cancel_exit")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    await query.edit_message_text(strings.SELECT_BOOKING_CANCEL, reply_markup=reply_markup)
    return CANCEL_SELECT


async def cancel_abort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("User %d aborted cancel conversation", update.effective_user.id)
    await update.message.reply_text(strings.CANCELLATION_ABORTED)
    context.user_data.clear()
    return ConversationHandler.END


async def cancel_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(
        "User %d sent unexpected input during cancel: %s",
        update.effective_user.id,
        update.message.text,
    )
    await update.message.reply_text(strings.USE_BUTTONS_CANCEL)
    return CANCEL_SELECT


cancel_conv = ConversationHandler(
    entry_points=[CommandHandler("cancel", cancel_start)],
    states={
        CANCEL_SELECT: [
            CallbackQueryHandler(cancel_select, pattern="^cancel_sel_|^cancel_exit$|^cancel_all$"),
        ],
        CANCEL_CONFIRM: [
            CallbackQueryHandler(cancel_confirm, pattern="^cancel_yes$|^cancel_no$|^cancel_exit$|^cancel_all_yes$|^cancel_all_no$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_abort),
        MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_unexpected),
    ],
)


# ── /available ──────────────────────────────────────────────────────────

async def available(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    schedule = db.get_schedule()
    if not schedule:
        await update.message.reply_text(strings.NO_SCHEDULE_AVAIL)
        return

    today = date.today()
    lines = [strings.AVAILABLE_HEADER]

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
        lines.append(f"\n{strings.fmt_date_abbr_day(d)}:")
        for t in starts:
            lines.append(f"  \u2022 {t}")

    logger.info("User %d checked availability: %d days with slots", user.id, len(lines) - 1)

    if len(lines) == 1:
        await update.message.reply_text(strings.NO_AVAILABLE_SLOTS)
        return

    await update.message.reply_text("\n".join(lines))


# ── /set_schedule conversation ──────────────────────────────────────────

SCHEDULE_DAYS, SCHEDULE_DAY_ACTION, SCHEDULE_START_TIME, SCHEDULE_END_TIME, SCHEDULE_CONFIRM = range(5)


def _day_label(day_idx: int, windows: list[tuple[str, str]]) -> str:
    abbr = strings.DAY_ABBRS_IT[day_idx]
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
        await update.message.reply_text(strings.SITTER_ONLY)
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
    keyboard.append([InlineKeyboardButton(strings.BTN_DONE, callback_data="sched_done")])

    await update.message.reply_text(
        strings.TAP_DAY,
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

    lines = [f"<b>{strings.DISPLAY_NAMES_IT[day_idx]}</b>"]
    if windows:
        for s, e in windows:
            lines.append(f"  {s} \u2013 {e}")
    else:
        lines.append(strings.NO_WINDOWS_CFG)

    keyboard = [[InlineKeyboardButton(strings.BTN_ADD_WINDOW, callback_data="sched_add")]]
    if windows:
        keyboard.append([InlineKeyboardButton(strings.BTN_CLEAR_DAY, callback_data="sched_clear")])
    keyboard.append([InlineKeyboardButton(strings.BTN_BACK_DAYS, callback_data="sched_back_days")])

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
    keyboard.append([InlineKeyboardButton(strings.BTN_DONE, callback_data="sched_done")])

    await update.callback_query.edit_message_text(
        strings.TAP_DAY,
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
    keyboard.append([InlineKeyboardButton(strings.BTN_BACK, callback_data="sched_back_action")])

    await update.callback_query.edit_message_text(
        strings.SELECT_START, reply_markup=InlineKeyboardMarkup(keyboard),
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
    keyboard.append([InlineKeyboardButton(strings.BTN_BACK, callback_data="sched_back_start")])

    await update.callback_query.edit_message_text(
        strings.SELECT_END.format(start=f"{start_hour:02d}:00"),
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
    lines = [f"<b>{strings.SCHEDULE_PREVIEW}</b>"]
    for day_idx in range(7):
        windows = draft.get(day_idx, [])
        if windows:
            times = ", ".join(f"{s}\u2013{e}" for s, e in windows)
            lines.append(f"{strings.DISPLAY_NAMES_IT[day_idx]}: {times}")
        else:
            lines.append(f"{strings.DISPLAY_NAMES_IT[day_idx]}: {strings.DAY_OFF_LABEL}")
    lines.append("")
    lines.append(strings.SAVE_SCHEDULE)

    keyboard = [
        [
            InlineKeyboardButton(strings.BTN_YES, callback_data="sched_save_yes"),
            InlineKeyboardButton(strings.BTN_NO, callback_data="sched_save_no"),
        ],
        [InlineKeyboardButton(strings.BTN_BACK_DAYS, callback_data="sched_back_days")],
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
        await query.edit_message_text(strings.SCHEDULE_UNCHANGED)
        context.user_data.clear()
        return ConversationHandler.END

    draft = context.user_data["schedule_draft"]
    slots = []
    for day_idx, windows in draft.items():
        for s, e in windows:
            slots.append((day_idx, s, e))

    if not slots:
        await query.edit_message_text(strings.NO_WINDOWS_SAVE)
        context.user_data.clear()
        return ConversationHandler.END

    db.set_schedule(slots)
    logger.info("Sitter updated schedule with %d window(s)", len(slots))
    new_schedule = db.get_schedule()
    await query.edit_message_text(
        strings.SCHEDULE_UPDATED.format(schedule=sch.format_schedule(new_schedule))
    )
    context.user_data.clear()
    return ConversationHandler.END


async def set_schedule_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Sitter cancelled schedule edit")
    await update.message.reply_text(strings.SCHEDULE_CANCELLED)
    context.user_data.clear()
    return ConversationHandler.END


async def set_schedule_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(
        "Sitter sent unexpected input during schedule edit: %s",
        update.message.text,
    )
    await update.message.reply_text(strings.USE_BUTTONS_SCHEDULE)
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

def _build_timeline(bookings: list[dict], schedule: list[dict]) -> list[str]:
    if not bookings:
        return []

    by_date: dict[str, list[dict]] = {}
    for b in bookings:
        by_date.setdefault(b["date"], []).append(b)
    for day_bookings in by_date.values():
        day_bookings.sort(key=lambda b: b["start_time"])

    windows_by_day: dict[int, list[tuple[str, str]]] = {}
    for s in schedule:
        windows_by_day.setdefault(s["day_of_week"], []).append(
            (s["start_time"], s["end_time"])
        )
    for windows in windows_by_day.values():
        windows.sort()

    lines: list[str] = []
    for date_str in sorted(by_date.keys()):
        d = date.fromisoformat(date_str)
        lines.append(f"📅 {strings.fmt_date_abbr_long(d)}")

        day_bookings = by_date[date_str]
        weekday = d.weekday()
        windows = windows_by_day.get(weekday, [])

        if not windows:
            for b in day_bookings:
                lines.append(_booking_line(b))
            lines.append("")
            continue

        for win_start, win_end in windows:
            lines.append(strings.ADMIN_WINDOW_HEADER.format(start=win_start, end=win_end))
            win_bookings = [
                b for b in day_bookings
                if sch._to_min(win_start) <= sch._to_min(b["start_time"]) < sch._to_min(win_end)
            ]
            if not win_bookings:
                lines.append(strings.ADMIN_FREE_WINDOW)
            else:
                for i, b in enumerate(win_bookings):
                    lines.append(_booking_line(b))
                    if i < len(win_bookings) - 1:
                        next_b = win_bookings[i + 1]
                        gap_min = sch._to_min(next_b["start_time"]) - sch._to_min(b["end_time"])
                        if gap_min > 0:
                            lines.append(strings.ADMIN_GAP.format(minutes=gap_min))
        lines.append("")

    return lines


def _booking_line(b: dict) -> str:
    c = b.get("children", 1)
    addr = b.get("address")
    name = b["user_name"]
    if addr:
        return strings.ADMIN_BOOKING_LINE.format(
            start=b["start_time"],
            end=b["end_time"],
            id=b["id"],
            name=name,
            address=addr[:30],
            children=f"{c} {strings.child_label(c)}",
        )
    return strings.ADMIN_BOOKING_NOLOC.format(
        start=b["start_time"],
        end=b["end_time"],
        id=b["id"],
        name=name,
        children=f"{c} {strings.child_label(c)}",
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_sitter(update):
        logger.info("Non-sitter user %d tried /admin", update.effective_user.id)
        await update.message.reply_text(strings.ADMIN_SITTER_ONLY)
        return

    bookings = db.get_all_bookings()
    if not bookings:
        logger.info("Sitter viewed admin: no upcoming bookings")
        await update.message.reply_text(strings.ADMIN_NO_BOOKINGS)
        return

    schedule = db.get_schedule()
    logger.info("Sitter viewed admin: %d booking(s), %d schedule windows", len(bookings), len(schedule))

    timeline_lines = _build_timeline(bookings, schedule)
    if not timeline_lines:
        await update.message.reply_text(strings.ADMIN_NO_BOOKINGS)
        return

    header = strings.ADMIN_TIMELINE_HEADER
    chunks: list[str] = []
    chunk: list[str] = [header]

    for line in timeline_lines:
        if len("\n".join(chunk)) + len(line) + 1 > 3800:
            chunks.append("\n".join(chunk))
            chunk = [header, line]
        else:
            chunk.append(line)

    chunks.append("\n".join(chunk))

    for i, text in enumerate(chunks):
        if i == 0:
            await update.message.reply_text(text)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

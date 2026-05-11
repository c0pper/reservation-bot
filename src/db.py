import logging
import os
import sqlite3

logger = logging.getLogger(__name__)


def get_db_path() -> str:
    return os.environ.get("DATABASE_PATH", "data/reservations.db")


def get_conn() -> sqlite3.Connection:
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 6),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            children INTEGER NOT NULL DEFAULT 1,
            latitude REAL,
            longitude REAL,
            status TEXT NOT NULL DEFAULT 'confirmed'
                CHECK(status IN ('confirmed', 'cancelled')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            cancelled_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date);
        CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
        CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
    """)
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN children INTEGER NOT NULL DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN latitude REAL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN longitude REAL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN address TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def get_schedule() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT day_of_week, start_time, end_time FROM schedule ORDER BY day_of_week, start_time"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_schedule(slots: list[tuple[int, str, str]]) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM schedule")
    conn.executemany(
        "INSERT INTO schedule (day_of_week, start_time, end_time) VALUES (?, ?, ?)",
        slots,
    )
    conn.commit()
    conn.close()
    logger.info("Schedule updated with %d slots", len(slots))


def add_booking(
    user_id: int, user_name: str, date: str, start_time: str, end_time: str, children: int = 1, latitude: float | None = None, longitude: float | None = None, address: str | None = None
) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO bookings (user_id, user_name, date, start_time, end_time, children, latitude, longitude, address) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, user_name, date, start_time, end_time, children, latitude, longitude, address),
    )
    conn.commit()
    booking_id = cur.lastrowid
    conn.close()
    logger.info(
        "Booking #%d added: user=%d (%s) date=%s %s-%s",
        booking_id, user_id, user_name, date, start_time, end_time,
    )
    return booking_id


def cancel_booking(booking_id: int, user_id: int, sitter_mode: bool = False) -> bool:
    conn = get_conn()
    if sitter_mode:
        cur = conn.execute(
            "UPDATE bookings SET status = 'cancelled', cancelled_at = datetime('now') WHERE id = ? AND status = 'confirmed'",
            (booking_id,),
        )
    else:
        cur = conn.execute(
            "UPDATE bookings SET status = 'cancelled', cancelled_at = datetime('now') WHERE id = ? AND user_id = ? AND status = 'confirmed'",
            (booking_id, user_id),
        )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    if affected > 0:
        logger.info(
            "Booking #%d cancelled by user=%d (sitter_mode=%s)",
            booking_id, user_id, sitter_mode,
        )
    return affected > 0


def cancel_user_bookings(user_id: int) -> int:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE bookings SET status = 'cancelled', cancelled_at = datetime('now') WHERE user_id = ? AND status = 'confirmed'",
        (user_id,),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    logger.info("Cancelled %d bookings for user=%d", affected, user_id)
    return affected


def get_user_bookings(user_id: int, status: str = "confirmed") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, date, start_time, end_time, children, latitude, longitude, address, status FROM bookings WHERE user_id = ? AND status = ? AND date >= date('now') ORDER BY date, start_time",
        (user_id, status),
    )
    result = [dict(r) for r in rows.fetchall()]
    conn.close()
    return result


def get_bookings_for_date(date_str: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT start_time, end_time, status, latitude, longitude FROM bookings WHERE date = ? AND status = 'confirmed' ORDER BY start_time",
        (date_str,),
    )
    result = [dict(r) for r in rows.fetchall()]
    conn.close()
    return result


def get_all_bookings(status: str = "confirmed") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, user_id, user_name, date, start_time, end_time, children, latitude, longitude, address, status, created_at FROM bookings WHERE status = ? AND date >= date('now') ORDER BY date, start_time",
        (status,),
    )
    result = [dict(r) for r in rows.fetchall()]
    conn.close()
    return result

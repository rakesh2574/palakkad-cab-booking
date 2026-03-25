"""
Database schema and helpers for Kerala Cabs Booking App.
Uses SQLite for simplicity — swap to PostgreSQL/MySQL for production.

V2: Kerala-wide coverage, scheduled bookings, driving preferences.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "kerala_cabs.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    -- ============================================================
    -- CUSTOMERS  (identified by WhatsApp phone number)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS customers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        phone           TEXT    UNIQUE NOT NULL,
        name            TEXT,
        preferred_speed TEXT,
        driving_notes   TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        updated_at      TEXT    DEFAULT (datetime('now'))
    );

    -- ============================================================
    -- DRIVERS  (stationed across Kerala)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS drivers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        phone           TEXT    UNIQUE NOT NULL,
        vehicle_number  TEXT,
        vehicle_type    TEXT    DEFAULT 'sedan',
        is_available    INTEGER DEFAULT 1,
        base_area       TEXT,
        created_at      TEXT    DEFAULT (datetime('now'))
    );

    -- ============================================================
    -- BOOKINGS  (free-text locations, scheduled date/time, notes)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS bookings (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id         INTEGER NOT NULL REFERENCES customers(id),
        driver_id           INTEGER REFERENCES drivers(id),
        pickup_location     TEXT    NOT NULL,
        drop_location       TEXT    NOT NULL,
        status              TEXT    DEFAULT 'pending',
        distance_km         REAL,
        est_duration_min    INTEGER,
        actual_duration_min INTEGER,
        fare                REAL,
        travel_date         TEXT,
        travel_time         TEXT,
        driving_notes       TEXT,
        booked_at           TEXT    DEFAULT (datetime('now')),
        started_at          TEXT,
        completed_at        TEXT
    );

    -- ============================================================
    -- CONVERSATION LOG  (every WhatsApp message, in & out)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS conversations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id     INTEGER NOT NULL REFERENCES customers(id),
        direction       TEXT    NOT NULL,
        message         TEXT    NOT NULL,
        created_at      TEXT    DEFAULT (datetime('now'))
    );
    """)

    # --- Migrations for existing databases ---
    # Add new columns if they don't exist (safe for fresh + existing DBs)
    migrations = [
        ("customers", "preferred_speed", "TEXT"),
        ("customers", "driving_notes", "TEXT"),
        ("bookings", "travel_date", "TEXT"),
        ("bookings", "travel_time", "TEXT"),
        ("bookings", "driving_notes", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    conn.close()
    print("✅ Database initialised (Kerala Cabs v2).")


# -----------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------

def get_or_create_customer(phone: str, name: str = None):
    """Return customer row; create if first time."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM customers WHERE phone = ?", (phone,))
    customer = cur.fetchone()
    if not customer:
        cur.execute(
            "INSERT INTO customers (phone, name) VALUES (?, ?)",
            (phone, name or "Unknown"),
        )
        conn.commit()
        cur.execute("SELECT * FROM customers WHERE phone = ?", (phone,))
        customer = cur.fetchone()
    conn.close()
    return dict(customer)


def update_customer_name(phone: str, name: str):
    conn = get_connection()
    conn.execute(
        "UPDATE customers SET name = ?, updated_at = datetime('now') WHERE phone = ?",
        (name, phone),
    )
    conn.commit()
    conn.close()


def update_customer_preferences(phone: str, preferred_speed: str = None, driving_notes: str = None):
    """Update customer's driving preferences for future context."""
    conn = get_connection()
    if preferred_speed:
        conn.execute(
            "UPDATE customers SET preferred_speed = ?, updated_at = datetime('now') WHERE phone = ?",
            (preferred_speed, phone),
        )
    if driving_notes:
        conn.execute(
            "UPDATE customers SET driving_notes = ?, updated_at = datetime('now') WHERE phone = ?",
            (driving_notes, phone),
        )
    conn.commit()
    conn.close()


def log_conversation(customer_id: int, direction: str, message: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (customer_id, direction, message) VALUES (?, ?, ?)",
        (customer_id, direction, message),
    )
    conn.commit()
    conn.close()


def find_available_driver():
    """Find any free driver."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM drivers WHERE is_available = 1 ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_booking(customer_id, driver_id, pickup_location, drop_location,
                   distance_km, est_duration_min,
                   travel_date=None, travel_time=None, driving_notes=None):
    """Create a booking — supports immediate or future-dated rides."""
    conn = get_connection()
    cur = conn.cursor()

    # For future bookings, don't mark driver as busy yet
    is_future = travel_date is not None and travel_date.strip() != ""
    status = "scheduled" if is_future else "confirmed"

    cur.execute(
        """INSERT INTO bookings
           (customer_id, driver_id, pickup_location, drop_location,
            status, distance_km, est_duration_min,
            travel_date, travel_time, driving_notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (customer_id, driver_id, pickup_location, drop_location,
         status, distance_km, est_duration_min,
         travel_date, travel_time, driving_notes),
    )
    booking_id = cur.lastrowid

    # Only mark driver busy for immediate rides
    if not is_future:
        conn.execute("UPDATE drivers SET is_available = 0 WHERE id = ?", (driver_id,))

    conn.commit()
    conn.close()
    return booking_id, status


def complete_booking(booking_id: int, actual_duration_min: int, rate_per_min: float = 8.0):
    """Complete a trip and calculate fare based on actual duration."""
    fare = round(actual_duration_min * rate_per_min, 2)
    conn = get_connection()
    conn.execute(
        """UPDATE bookings
           SET status = 'completed',
               actual_duration_min = ?,
               fare = ?,
               completed_at = datetime('now')
           WHERE id = ?""",
        (actual_duration_min, fare, booking_id),
    )
    # Free up the driver
    row = conn.execute("SELECT driver_id FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row:
        conn.execute("UPDATE drivers SET is_available = 1 WHERE id = ?", (row["driver_id"],))
    conn.commit()
    conn.close()
    return fare


def get_customer_bookings(customer_id: int, limit: int = 5):
    conn = get_connection()
    rows = conn.execute(
        """SELECT b.*, d.name as driver_name
           FROM bookings b
           LEFT JOIN drivers d ON b.driver_id = d.id
           WHERE b.customer_id = ?
           ORDER BY b.booked_at DESC LIMIT ?""",
        (customer_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_customer_frequent_routes(customer_id: int, limit: int = 3):
    """Get most frequently booked routes for smart rebooking suggestions."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT pickup_location, drop_location, COUNT(*) as trip_count,
                  ROUND(AVG(distance_km), 1) as avg_distance,
                  ROUND(AVG(est_duration_min)) as avg_duration
           FROM bookings
           WHERE customer_id = ? AND status IN ('completed', 'confirmed', 'scheduled')
           GROUP BY pickup_location, drop_location
           ORDER BY trip_count DESC
           LIMIT ?""",
        (customer_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cancel_booking(booking_id: int):
    """Cancel a booking and free the driver."""
    conn = get_connection()
    row = conn.execute("SELECT driver_id, status FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if row:
        conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        # Free driver only if booking was confirmed (not scheduled)
        if row["status"] == "confirmed":
            conn.execute("UPDATE drivers SET is_available = 1 WHERE id = ?", (row["driver_id"],))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()

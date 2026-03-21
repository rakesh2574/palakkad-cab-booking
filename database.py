"""
Database schema and helpers for Palakkad Cab Booking App.
Uses SQLite for simplicity — swap to PostgreSQL/MySQL for production.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "palakkad_cabs.db")


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
        phone           TEXT    UNIQUE NOT NULL,       -- E.164 format e.g. +919876543210
        name            TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        updated_at      TEXT    DEFAULT (datetime('now'))
    );

    -- ============================================================
    -- MAJOR LOCATIONS in Palakkad
    -- ============================================================
    CREATE TABLE IF NOT EXISTS locations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    UNIQUE NOT NULL,        -- e.g. 'Palakkad Fort'
        lat             REAL,
        lon             REAL
    );

    -- ============================================================
    -- ROUTE MATRIX  (predefined distance & est. duration between locations)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS routes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        from_location_id INTEGER NOT NULL REFERENCES locations(id),
        to_location_id   INTEGER NOT NULL REFERENCES locations(id),
        distance_km      REAL   NOT NULL,
        est_duration_min INTEGER NOT NULL,              -- estimated minutes
        UNIQUE(from_location_id, to_location_id)
    );

    -- ============================================================
    -- DRIVERS
    -- ============================================================
    CREATE TABLE IF NOT EXISTS drivers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        phone           TEXT    UNIQUE NOT NULL,
        vehicle_number  TEXT,
        vehicle_type    TEXT    DEFAULT 'sedan',        -- sedan / suv / auto
        is_available    INTEGER DEFAULT 1,              -- 1 = free, 0 = on trip
        current_location_id INTEGER REFERENCES locations(id),
        created_at      TEXT    DEFAULT (datetime('now'))
    );

    -- ============================================================
    -- BOOKINGS
    -- ============================================================
    CREATE TABLE IF NOT EXISTS bookings (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id     INTEGER NOT NULL REFERENCES customers(id),
        driver_id       INTEGER REFERENCES drivers(id),
        from_location_id INTEGER NOT NULL REFERENCES locations(id),
        to_location_id   INTEGER NOT NULL REFERENCES locations(id),
        status          TEXT    DEFAULT 'pending',      -- pending / confirmed / in_progress / completed / cancelled
        distance_km     REAL,
        est_duration_min INTEGER,
        actual_duration_min INTEGER,
        fare            REAL,                            -- calculated on completion
        booked_at       TEXT    DEFAULT (datetime('now')),
        started_at      TEXT,
        completed_at    TEXT
    );

    -- ============================================================
    -- CONVERSATION LOG  (every WhatsApp message, in & out)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS conversations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id     INTEGER NOT NULL REFERENCES customers(id),
        direction       TEXT    NOT NULL,                -- 'in' or 'out'
        message         TEXT    NOT NULL,
        created_at      TEXT    DEFAULT (datetime('now'))
    );
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialised.")


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


def log_conversation(customer_id: int, direction: str, message: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (customer_id, direction, message) VALUES (?, ?, ?)",
        (customer_id, direction, message),
    )
    conn.commit()
    conn.close()


def get_locations():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM locations ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_location(name_fragment: str):
    """Fuzzy-ish location lookup."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM locations WHERE LOWER(name) LIKE ?",
        (f"%{name_fragment.lower()}%",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_route(from_id: int, to_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM routes WHERE from_location_id = ? AND to_location_id = ?",
        (from_id, to_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def find_available_driver(location_id: int = None):
    """Find a free driver, preferring one near the pickup location."""
    conn = get_connection()
    if location_id:
        row = conn.execute(
            "SELECT * FROM drivers WHERE is_available = 1 AND current_location_id = ? LIMIT 1",
            (location_id,),
        ).fetchone()
        if row:
            conn.close()
            return dict(row)
    row = conn.execute(
        "SELECT * FROM drivers WHERE is_available = 1 ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_booking(customer_id, driver_id, from_loc_id, to_loc_id, distance_km, est_duration_min):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO bookings
           (customer_id, driver_id, from_location_id, to_location_id,
            status, distance_km, est_duration_min)
           VALUES (?, ?, ?, ?, 'confirmed', ?, ?)""",
        (customer_id, driver_id, from_loc_id, to_loc_id, distance_km, est_duration_min),
    )
    booking_id = cur.lastrowid
    # Mark driver busy
    conn.execute("UPDATE drivers SET is_available = 0 WHERE id = ?", (driver_id,))
    conn.commit()
    conn.close()
    return booking_id


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
        """SELECT b.*, lf.name as from_name, lt.name as to_name, d.name as driver_name
           FROM bookings b
           JOIN locations lf ON b.from_location_id = lf.id
           JOIN locations lt ON b.to_location_id = lt.id
           LEFT JOIN drivers d ON b.driver_id = d.id
           WHERE b.customer_id = ?
           ORDER BY b.booked_at DESC LIMIT ?""",
        (customer_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()

"""
Fish Hub database layer — shares the cab booking SQLite DB.
Adds ONLY fish-specific tables. Re-uses customers + access_pins from cab database.
"""

import sys, os
from datetime import date

# Re-use cab booking's connection helper so both modules hit the same DB file
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as cabdb  # noqa: E402


def init_fish_tables():
    """Create fish-specific tables in the shared DB (safe to call repeatedly)."""
    conn = cabdb.get_connection()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS fish_catalog (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        name                 TEXT UNIQUE NOT NULL,
        malayalam_name       TEXT,
        speciality           TEXT,
        typical_price_per_kg REAL
    );

    CREATE TABLE IF NOT EXISTS fish_inventory (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        inventory_date TEXT NOT NULL,
        fish_name      TEXT NOT NULL,
        available_kg   REAL NOT NULL,
        reserved_kg    REAL DEFAULT 0,
        price_per_kg   REAL NOT NULL,
        notes          TEXT,
        created_at     TEXT DEFAULT (datetime('now')),
        UNIQUE(inventory_date, fish_name)
    );

    CREATE TABLE IF NOT EXISTS fish_orders (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_phone  TEXT NOT NULL,
        customer_name   TEXT,
        fish_name       TEXT NOT NULL,
        quantity_kg     REAL NOT NULL,
        price_per_kg    REAL NOT NULL,
        total_price     REAL NOT NULL,
        delivery_date   TEXT NOT NULL,
        delivery_slot   TEXT NOT NULL,
        status          TEXT DEFAULT 'confirmed',
        created_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS fish_customer_prefs (
        phone           TEXT PRIMARY KEY,
        preferences     TEXT,
        updated_at      TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    conn.close()


# ---------------- Fish catalog ----------------

def upsert_fish_catalog(name, malayalam_name="", speciality="", typical_price=0):
    conn = cabdb.get_connection()
    cur = conn.cursor()
    existing = cur.execute("SELECT id FROM fish_catalog WHERE name = ?", (name,)).fetchone()
    if existing:
        cur.execute(
            "UPDATE fish_catalog SET malayalam_name=?, speciality=?, typical_price_per_kg=? WHERE name=?",
            (malayalam_name, speciality, typical_price, name),
        )
    else:
        cur.execute(
            "INSERT INTO fish_catalog (name, malayalam_name, speciality, typical_price_per_kg) VALUES (?, ?, ?, ?)",
            (name, malayalam_name, speciality, typical_price),
        )
    conn.commit()
    conn.close()


def get_fish_catalog():
    conn = cabdb.get_connection()
    rows = conn.execute("SELECT * FROM fish_catalog ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------- Inventory ----------------

def upsert_inventory(inventory_date, fish_name, available_kg, price_per_kg, notes=""):
    conn = cabdb.get_connection()
    cur = conn.cursor()
    existing = cur.execute(
        "SELECT id FROM fish_inventory WHERE inventory_date=? AND fish_name=? COLLATE NOCASE",
        (inventory_date, fish_name),
    ).fetchone()
    if existing:
        cur.execute(
            "UPDATE fish_inventory SET available_kg=?, price_per_kg=?, notes=? WHERE id=?",
            (available_kg, price_per_kg, notes, existing["id"]),
        )
    else:
        cur.execute(
            "INSERT INTO fish_inventory (inventory_date, fish_name, available_kg, price_per_kg, notes) VALUES (?, ?, ?, ?, ?)",
            (inventory_date, fish_name, available_kg, price_per_kg, notes),
        )
    conn.commit()
    conn.close()


def get_today_inventory(inventory_date=None):
    if inventory_date is None:
        inventory_date = date.today().isoformat()
    conn = cabdb.get_connection()
    rows = conn.execute(
        """SELECT i.*, c.malayalam_name, c.speciality
           FROM fish_inventory i
           LEFT JOIN fish_catalog c ON c.name = i.fish_name COLLATE NOCASE
           WHERE i.inventory_date = ?
           ORDER BY i.fish_name""",
        (inventory_date,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_available_kg(inventory_date, fish_name):
    conn = cabdb.get_connection()
    row = conn.execute(
        """SELECT available_kg, reserved_kg FROM fish_inventory
           WHERE inventory_date=? AND fish_name=? COLLATE NOCASE""",
        (inventory_date, fish_name),
    ).fetchone()
    conn.close()
    if not row:
        return 0.0
    return float(row["available_kg"]) - float(row["reserved_kg"])


def reserve_inventory(inventory_date, fish_name, quantity_kg):
    conn = cabdb.get_connection()
    cur = conn.cursor()
    row = cur.execute(
        """SELECT id, available_kg, reserved_kg FROM fish_inventory
           WHERE inventory_date=? AND fish_name=? COLLATE NOCASE""",
        (inventory_date, fish_name),
    ).fetchone()
    if not row:
        conn.close()
        return False
    remaining = float(row["available_kg"]) - float(row["reserved_kg"])
    if remaining < quantity_kg:
        conn.close()
        return False
    cur.execute(
        "UPDATE fish_inventory SET reserved_kg = reserved_kg + ? WHERE id=?",
        (quantity_kg, row["id"]),
    )
    conn.commit()
    conn.close()
    return True


# ---------------- Orders ----------------

def create_order(customer_phone, customer_name, fish_name, quantity_kg,
                 price_per_kg, delivery_date, delivery_slot):
    total = round(quantity_kg * price_per_kg, 2)
    conn = cabdb.get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO fish_orders
           (customer_phone, customer_name, fish_name, quantity_kg,
            price_per_kg, total_price, delivery_date, delivery_slot)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (customer_phone, customer_name, fish_name, quantity_kg,
         price_per_kg, total, delivery_date, delivery_slot),
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def get_customer_orders(phone, limit=10):
    conn = cabdb.get_connection()
    rows = conn.execute(
        "SELECT * FROM fish_orders WHERE customer_phone=? ORDER BY created_at DESC LIMIT ?",
        (phone, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_customer_favourite_fish(phone, limit=3):
    conn = cabdb.get_connection()
    rows = conn.execute(
        """SELECT fish_name, COUNT(*) as order_count, SUM(quantity_kg) as total_kg
           FROM fish_orders WHERE customer_phone=? AND status!='cancelled'
           GROUP BY fish_name ORDER BY order_count DESC, total_kg DESC LIMIT ?""",
        (phone, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cancel_order(order_id, phone):
    conn = cabdb.get_connection()
    cur = conn.cursor()
    order = cur.execute(
        "SELECT * FROM fish_orders WHERE id=? AND customer_phone=?",
        (order_id, phone),
    ).fetchone()
    if not order or order["status"] == "cancelled":
        conn.close()
        return False
    cur.execute("UPDATE fish_orders SET status='cancelled' WHERE id=?", (order_id,))
    cur.execute(
        """UPDATE fish_inventory SET reserved_kg = MAX(0, reserved_kg - ?)
           WHERE inventory_date=? AND fish_name=? COLLATE NOCASE""",
        (order["quantity_kg"], order["delivery_date"], order["fish_name"]),
    )
    conn.commit()
    conn.close()
    return True


def list_all_orders(limit=500):
    conn = cabdb.get_connection()
    rows = conn.execute(
        "SELECT * FROM fish_orders ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------- Customer preferences (fish-specific) ----------------

def save_preferences(phone, prefs_text):
    conn = cabdb.get_connection()
    conn.execute(
        """INSERT INTO fish_customer_prefs (phone, preferences, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(phone) DO UPDATE SET preferences=excluded.preferences, updated_at=datetime('now')""",
        (phone, prefs_text),
    )
    conn.commit()
    conn.close()


def get_preferences(phone):
    conn = cabdb.get_connection()
    row = conn.execute(
        "SELECT preferences FROM fish_customer_prefs WHERE phone=?", (phone,)
    ).fetchone()
    conn.close()
    return row["preferences"] if row else ""

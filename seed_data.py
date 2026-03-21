"""
Seed script — populates the database with Palakkad locations,
routes, and sample drivers.

Run once:  python seed_data.py
"""

import database as db


def seed():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    # ── LOCATIONS (major places in Palakkad) ──
    locations = [
        ("Palakkad Fort", 10.7751, 76.6538),
        ("Palakkad Town Bus Stand", 10.7767, 76.6554),
        ("Olavakkode Railway Station", 10.7882, 76.6390),
        ("Palakkad Junction Railway Station", 10.7720, 76.6490),
        ("Kalmandapam", 10.7690, 76.6380),
        ("Chandranagar", 10.7850, 76.6480),
        ("Nurani", 10.7800, 76.6600),
        ("Kongad", 10.7980, 76.6200),
        ("Mannarkkad", 10.9920, 76.4600),
        ("Ottapalam", 10.7700, 76.3700),
        ("Shoranur Junction", 10.7620, 76.2720),
        ("Chittur", 10.7000, 76.7400),
        ("Malampuzha Dam", 10.8300, 76.6900),
        ("Nemmara", 10.5900, 76.6300),
        ("Pattambi", 10.8100, 76.1900),
        ("Alathur", 10.6500, 76.5400),
        ("Kollengode", 10.6100, 76.6900),
        ("Kanjikode", 10.7580, 76.7120),
        ("Walayar", 10.7450, 76.8100),
        ("Pudussery", 10.7560, 76.6700),
    ]

    cur.executemany(
        "INSERT OR IGNORE INTO locations (name, lat, lon) VALUES (?, ?, ?)",
        locations,
    )
    conn.commit()

    # Build a quick name→id map
    rows = conn.execute("SELECT id, name FROM locations").fetchall()
    loc_map = {r["name"]: r["id"] for r in rows}

    # ── ROUTES (common routes with distance and est. duration) ──
    # (from, to, distance_km, est_duration_min)
    routes_data = [
        ("Palakkad Fort", "Palakkad Town Bus Stand", 1.0, 5),
        ("Palakkad Fort", "Palakkad Junction Railway Station", 1.5, 7),
        ("Palakkad Fort", "Olavakkode Railway Station", 3.0, 12),
        ("Palakkad Fort", "Kalmandapam", 2.5, 10),
        ("Palakkad Fort", "Chandranagar", 2.0, 8),
        ("Palakkad Fort", "Nurani", 2.0, 8),
        ("Palakkad Fort", "Malampuzha Dam", 10.0, 25),
        ("Palakkad Fort", "Chittur", 12.0, 30),
        ("Palakkad Fort", "Kanjikode", 8.0, 20),
        ("Palakkad Fort", "Walayar", 14.0, 30),
        ("Palakkad Town Bus Stand", "Olavakkode Railway Station", 2.5, 10),
        ("Palakkad Town Bus Stand", "Palakkad Junction Railway Station", 1.0, 5),
        ("Palakkad Town Bus Stand", "Mannarkkad", 35.0, 55),
        ("Palakkad Town Bus Stand", "Ottapalam", 30.0, 50),
        ("Palakkad Town Bus Stand", "Shoranur Junction", 40.0, 60),
        ("Palakkad Town Bus Stand", "Nemmara", 25.0, 45),
        ("Palakkad Town Bus Stand", "Alathur", 20.0, 35),
        ("Palakkad Town Bus Stand", "Kongad", 5.0, 12),
        ("Palakkad Junction Railway Station", "Olavakkode Railway Station", 2.5, 10),
        ("Palakkad Junction Railway Station", "Kanjikode", 7.0, 18),
        ("Palakkad Junction Railway Station", "Walayar", 13.0, 28),
        ("Palakkad Junction Railway Station", "Malampuzha Dam", 11.0, 25),
        ("Palakkad Junction Railway Station", "Chittur", 13.0, 30),
        ("Olavakkode Railway Station", "Shoranur Junction", 38.0, 55),
        ("Olavakkode Railway Station", "Kongad", 3.5, 10),
        ("Olavakkode Railway Station", "Mannarkkad", 33.0, 50),
        ("Kalmandapam", "Malampuzha Dam", 8.0, 20),
        ("Kalmandapam", "Chittur", 10.0, 25),
        ("Nurani", "Kanjikode", 7.0, 18),
        ("Nurani", "Pudussery", 3.0, 8),
        ("Mannarkkad", "Nemmara", 50.0, 75),
        ("Ottapalam", "Shoranur Junction", 12.0, 20),
        ("Ottapalam", "Pattambi", 8.0, 15),
        ("Shoranur Junction", "Pattambi", 12.0, 20),
        ("Chittur", "Kollengode", 12.0, 25),
        ("Chittur", "Nemmara", 18.0, 35),
        ("Alathur", "Nemmara", 12.0, 25),
        ("Alathur", "Kollengode", 8.0, 18),
        ("Kanjikode", "Walayar", 7.0, 15),
        ("Kongad", "Mannarkkad", 30.0, 45),
    ]

    for from_name, to_name, dist, dur in routes_data:
        from_id = loc_map.get(from_name)
        to_id = loc_map.get(to_name)
        if from_id and to_id:
            cur.execute(
                "INSERT OR IGNORE INTO routes (from_location_id, to_location_id, distance_km, est_duration_min) VALUES (?, ?, ?, ?)",
                (from_id, to_id, dist, dur),
            )
            # Also insert reverse route (same distance/duration)
            cur.execute(
                "INSERT OR IGNORE INTO routes (from_location_id, to_location_id, distance_km, est_duration_min) VALUES (?, ?, ?, ?)",
                (to_id, from_id, dist, dur),
            )
    conn.commit()

    # ── SAMPLE DRIVERS ──
    drivers = [
        ("Suresh Kumar", "+919876543001", "KL-46-A-1234", "sedan", 1, "Palakkad Fort"),
        ("Rajan Pillai", "+919876543002", "KL-46-B-5678", "sedan", 1, "Palakkad Town Bus Stand"),
        ("Anil Mohan", "+919876543003", "KL-46-C-9012", "suv", 1, "Olavakkode Railway Station"),
        ("Vipin Das", "+919876543004", "KL-46-D-3456", "sedan", 1, "Palakkad Junction Railway Station"),
        ("Rajesh Nair", "+919876543005", "KL-46-E-7890", "suv", 1, "Kalmandapam"),
        ("Manoj K", "+919876543006", "KL-46-F-1122", "auto", 1, "Nurani"),
        ("Dileep Thomas", "+919876543007", "KL-46-G-3344", "sedan", 1, "Chandranagar"),
        ("Biju P", "+919876543008", "KL-46-H-5566", "sedan", 1, "Mannarkkad"),
        ("Sathyan M", "+919876543009", "KL-46-J-7788", "suv", 1, "Chittur"),
        ("Pramod V", "+919876543010", "KL-46-K-9900", "sedan", 1, "Kongad"),
    ]

    for name, phone, vehicle_num, v_type, available, loc_name in drivers:
        loc_id = loc_map.get(loc_name)
        cur.execute(
            "INSERT OR IGNORE INTO drivers (name, phone, vehicle_number, vehicle_type, is_available, current_location_id) VALUES (?, ?, ?, ?, ?, ?)",
            (name, phone, vehicle_num, v_type, available, loc_id),
        )
    conn.commit()
    conn.close()

    print("🌱 Seed data loaded successfully!")
    print(f"   • {len(locations)} locations")
    print(f"   • {len(routes_data) * 2} routes (both directions)")
    print(f"   • {len(drivers)} drivers")


if __name__ == "__main__":
    seed()

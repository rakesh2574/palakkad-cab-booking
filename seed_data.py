"""
Seed script — populates the database with Palakkad locations,
routes, and sample drivers.

Run once:  python seed_data.py
"""

import math
import database as db


def seed():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    # ── LOCATIONS (comprehensive list of places in Palakkad district) ──
    locations = [
        # === PALAKKAD TOWN & SURROUNDINGS ===
        ("Palakkad Fort", 10.7751, 76.6538),
        ("Palakkad Town Bus Stand", 10.7767, 76.6554),
        ("Olavakkode Railway Station", 10.7882, 76.6390),
        ("Palakkad Junction Railway Station", 10.7720, 76.6490),
        ("Kalmandapam", 10.7690, 76.6380),
        ("Chandranagar", 10.7850, 76.6480),
        ("Nurani", 10.7800, 76.6600),
        ("Pudussery", 10.7560, 76.6700),
        ("Puthur", 10.7700, 76.6350),
        ("Sultanpet", 10.7780, 76.6520),
        ("Kalleppully", 10.7830, 76.6450),
        ("Head Post Office", 10.7760, 76.6540),
        ("Manjakulam", 10.7720, 76.6480),
        ("Kunissery", 10.7650, 76.6420),
        ("English Church Road", 10.7740, 76.6530),
        ("Court Road", 10.7755, 76.6545),
        ("Stadium", 10.7710, 76.6500),
        ("Chunnambuthara", 10.7680, 76.6460),
        ("Coimbatore Gate", 10.7730, 76.6600),
        ("Mettupalayam Street", 10.7745, 76.6555),

        # === NORTH PALAKKAD ===
        ("Kongad", 10.7980, 76.6200),
        ("Pirayiri", 10.8050, 76.6350),
        ("Malampuzha", 10.8300, 76.6800),
        ("Malampuzha Dam", 10.8300, 76.6900),
        ("Malampuzha Garden", 10.8310, 76.6880),
        ("Kava", 10.8200, 76.6600),
        ("Puduppariyaram", 10.8100, 76.6500),
        ("Koduvayur", 10.8500, 76.6400),
        ("Puthunagaram", 10.7900, 76.6550),
        ("Kallekulangara", 10.7950, 76.6500),
        ("Mundur", 10.8400, 76.5800),
        ("Kannambra", 10.8600, 76.5600),
        ("Elappully", 10.8100, 76.6300),

        # === EAST PALAKKAD (towards Coimbatore) ===
        ("Kanjikode", 10.7580, 76.7120),
        ("Walayar", 10.7450, 76.8100),
        ("Walayar Check Post", 10.7440, 76.8150),
        ("Pudussery East", 10.7550, 76.6800),
        ("Pudussery West", 10.7540, 76.6650),
        ("Kanjikode Industrial Area", 10.7600, 76.7200),
        ("Marutharoad", 10.7500, 76.7000),
        ("Chittilanchery", 10.7480, 76.7300),

        # === SOUTH PALAKKAD (Chittur area) ===
        ("Chittur", 10.7000, 76.7400),
        ("Chittur Thathamangalam", 10.7050, 76.7350),
        ("Tattamangalam", 10.7100, 76.7300),
        ("Eruthenpathy", 10.6900, 76.7200),
        ("Vadakkenchery", 10.6600, 76.7000),
        ("Perumatty", 10.7150, 76.7100),
        ("Nallepilly", 10.6800, 76.7150),
        ("Kozhinjampara", 10.6500, 76.7300),
        ("Muttikulangara", 10.7200, 76.7000),
        ("Panniyankara", 10.7050, 76.7100),

        # === KOLLENGODE & NEMMARA AREA ===
        ("Kollengode", 10.6100, 76.6900),
        ("Nemmara", 10.5900, 76.6300),
        ("Pallassana", 10.6200, 76.6500),
        ("Melarcode", 10.6000, 76.6100),
        ("Elavanchery", 10.5800, 76.6400),
        ("Ayilur", 10.5700, 76.6200),
        ("Thiruvilwamala", 10.5500, 76.6000),
        ("Pothundi Dam", 10.5600, 76.6800),

        # === ALATHUR AREA ===
        ("Alathur", 10.6500, 76.5400),
        ("Kavassery", 10.6600, 76.5200),
        ("Vadakkumpuram", 10.6400, 76.5300),
        ("Tharur", 10.6700, 76.5600),
        ("Kottayi", 10.6300, 76.5100),
        ("Puthukkode", 10.6200, 76.5000),

        # === MANNARKKAD & ATTAPPADI AREA ===
        ("Mannarkkad", 10.9920, 76.4600),
        ("Agali", 10.9500, 76.5800),
        ("Attappadi", 11.0500, 76.5500),
        ("Sholayur", 11.0200, 76.5200),
        ("Anakkatti", 11.0000, 76.5000),
        ("Thachampara", 10.9600, 76.4800),
        ("Karakurissi", 10.9700, 76.4500),
        ("Pallikurup", 10.9800, 76.4700),
        ("Pothukallu", 10.9400, 76.5500),

        # === OTTAPALAM AREA ===
        ("Ottapalam", 10.7700, 76.3700),
        ("Lakkidi", 10.7800, 76.3500),
        ("Vaniyamkulam", 10.7600, 76.3800),
        ("Thrithala", 10.7500, 76.3400),
        ("Pattithara", 10.7650, 76.3600),
        ("Kadambazhipuram", 10.7750, 76.3900),
        ("Cherpulassery", 10.8700, 76.3100),
        ("Vellinezhi", 10.7400, 76.3300),
        ("Shornur Road", 10.7650, 76.3200),

        # === SHORANUR & PATTAMBI AREA ===
        ("Shoranur Junction", 10.7620, 76.2720),
        ("Shoranur Town", 10.7600, 76.2800),
        ("Pattambi", 10.8100, 76.1900),
        ("Ongallur", 10.7900, 76.2500),
        ("Thrikkadeeri", 10.7800, 76.2300),
        ("Vallappuzha", 10.7700, 76.2600),
        ("Kulukkallur", 10.7650, 76.2400),

        # === TOURIST & PILGRIMAGE SPOTS ===
        ("Dhoni Hills", 10.7400, 76.7500),
        ("Kalpathy Heritage Village", 10.7780, 76.6450),
        ("Tipu Sultan Fort", 10.7751, 76.6540),
        ("Jain Temple Jainimedu", 10.7800, 76.6500),
        ("Fantasy Park Malampuzha", 10.8320, 76.6870),
        ("Rock Garden Malampuzha", 10.8290, 76.6910),
        ("Parambikulam Tiger Reserve", 10.4300, 76.7700),
        ("Silent Valley National Park", 11.0800, 76.4300),
        ("Nelliampathy Hills", 10.5300, 76.6800),
        ("Seethargundu Viewpoint", 10.5200, 76.6700),
        ("Kanjirapuzha Dam", 10.6400, 76.7100),
        ("Meenvallam Waterfalls", 10.5400, 76.6600),
        ("Siruvani Dam", 10.8500, 76.7200),
        ("Palakkad Gap", 10.7500, 76.7500),
        ("Kalpathy Ratholsavam Temple", 10.7785, 76.6440),

        # === HOSPITALS & LANDMARKS ===
        ("District Hospital Palakkad", 10.7770, 76.6520),
        ("KIMS Hospital", 10.7650, 76.6580),
        ("Baby Memorial Hospital", 10.7740, 76.6510),
        ("NSS Engineering College", 10.7960, 76.6470),
        ("Govt Victoria College", 10.7760, 76.6530),
        ("ALP School Palakkad", 10.7730, 76.6490),
    ]

    cur.executemany(
        "INSERT OR IGNORE INTO locations (name, lat, lon) VALUES (?, ?, ?)",
        locations,
    )
    conn.commit()

    # Build a quick name→id map
    rows = conn.execute("SELECT id, name, lat, lon FROM locations").fetchall()
    loc_map = {r["name"]: r["id"] for r in rows}
    loc_coords = {r["name"]: (r["lat"], r["lon"]) for r in rows}

    # ── AUTO-GENERATE ROUTES between nearby locations ──
    # Instead of manually defining every route, calculate distance from coordinates
    # and generate routes for locations within 60km of each other

    def haversine_km(lat1, lon1, lat2, lon2):
        """Calculate distance between two lat/lon points in km."""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    def estimate_duration(distance_km):
        """Estimate driving duration based on distance (avg 30 km/h in Palakkad)."""
        return max(5, round(distance_km / 30 * 60))  # minutes, min 5 min

    route_count = 0
    loc_names = list(loc_coords.keys())
    for i, name_a in enumerate(loc_names):
        for name_b in loc_names[i+1:]:
            lat1, lon1 = loc_coords[name_a]
            lat2, lon2 = loc_coords[name_b]
            dist = round(haversine_km(lat1, lon1, lat2, lon2), 1)

            # Only create routes for locations within 60km
            if dist <= 60 and dist > 0.1:
                duration = estimate_duration(dist)
                # Road distance is typically 1.3x straight-line distance
                road_dist = round(dist * 1.3, 1)

                cur.execute(
                    "INSERT OR IGNORE INTO routes (from_location_id, to_location_id, distance_km, est_duration_min) VALUES (?, ?, ?, ?)",
                    (loc_map[name_a], loc_map[name_b], road_dist, duration),
                )
                cur.execute(
                    "INSERT OR IGNORE INTO routes (from_location_id, to_location_id, distance_km, est_duration_min) VALUES (?, ?, ?, ?)",
                    (loc_map[name_b], loc_map[name_a], road_dist, duration),
                )
                route_count += 2

    conn.commit()

    # ── SAMPLE DRIVERS (stationed across the district) ──
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
        ("Gireesh R", "+919876543011", "KL-46-L-1010", "sedan", 1, "Ottapalam"),
        ("Sreejith B", "+919876543012", "KL-46-M-2020", "suv", 1, "Shoranur Junction"),
        ("Babu M", "+919876543013", "KL-46-N-3030", "sedan", 1, "Alathur"),
        ("Deepak K", "+919876543014", "KL-46-P-4040", "sedan", 1, "Nemmara"),
        ("Ratheesh V", "+919876543015", "KL-46-Q-5050", "suv", 1, "Malampuzha Dam"),
        ("Shibu S", "+919876543016", "KL-46-R-6060", "sedan", 1, "Pattambi"),
        ("Jayan T", "+919876543017", "KL-46-S-7070", "sedan", 1, "Kanjikode"),
        ("Sajith N", "+919876543018", "KL-46-T-8080", "auto", 1, "Sultanpet"),
        ("Vinod G", "+919876543019", "KL-46-U-9090", "sedan", 1, "Kollengode"),
        ("Pradeep J", "+919876543020", "KL-46-V-1111", "suv", 1, "Cherpulassery"),
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
    print(f"   • {route_count} routes (auto-generated)")
    print(f"   • {len(drivers)} drivers")


if __name__ == "__main__":
    seed()

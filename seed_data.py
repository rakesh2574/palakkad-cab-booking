"""
Seed script — populates the database with sample drivers.
Locations are now handled dynamically by GPT — no fixed location list needed.

Run once:  python seed_data.py
"""

import database as db


def seed():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    # ── SAMPLE DRIVERS (stationed across the district) ──
    drivers = [
        ("Suresh Kumar", "+919876543001", "KL-46-A-1234", "sedan", 1, "Palakkad Town"),
        ("Rajan Pillai", "+919876543002", "KL-46-B-5678", "sedan", 1, "Palakkad Town"),
        ("Anil Mohan", "+919876543003", "KL-46-C-9012", "suv", 1, "Olavakkode"),
        ("Vipin Das", "+919876543004", "KL-46-D-3456", "sedan", 1, "Palakkad Junction"),
        ("Rajesh Nair", "+919876543005", "KL-46-E-7890", "suv", 1, "Kalmandapam"),
        ("Manoj K", "+919876543006", "KL-46-F-1122", "auto", 1, "Nurani"),
        ("Dileep Thomas", "+919876543007", "KL-46-G-3344", "sedan", 1, "Chandranagar"),
        ("Biju P", "+919876543008", "KL-46-H-5566", "sedan", 1, "Mannarkkad"),
        ("Sathyan M", "+919876543009", "KL-46-J-7788", "suv", 1, "Chittur"),
        ("Pramod V", "+919876543010", "KL-46-K-9900", "sedan", 1, "Kongad"),
        ("Gireesh R", "+919876543011", "KL-46-L-1010", "sedan", 1, "Ottapalam"),
        ("Sreejith B", "+919876543012", "KL-46-M-2020", "suv", 1, "Shoranur"),
        ("Babu M", "+919876543013", "KL-46-N-3030", "sedan", 1, "Alathur"),
        ("Deepak K", "+919876543014", "KL-46-P-4040", "sedan", 1, "Nemmara"),
        ("Ratheesh V", "+919876543015", "KL-46-Q-5050", "suv", 1, "Malampuzha"),
        ("Shibu S", "+919876543016", "KL-46-R-6060", "sedan", 1, "Pattambi"),
        ("Jayan T", "+919876543017", "KL-46-S-7070", "sedan", 1, "Kanjikode"),
        ("Sajith N", "+919876543018", "KL-46-T-8080", "auto", 1, "Sultanpet"),
        ("Vinod G", "+919876543019", "KL-46-U-9090", "sedan", 1, "Kollengode"),
        ("Pradeep J", "+919876543020", "KL-46-V-1111", "suv", 1, "Cherpulassery"),
    ]

    for name, phone, vehicle_num, v_type, available, base_area in drivers:
        cur.execute(
            "INSERT OR IGNORE INTO drivers (name, phone, vehicle_number, vehicle_type, is_available, base_area) VALUES (?, ?, ?, ?, ?, ?)",
            (name, phone, vehicle_num, v_type, available, base_area),
        )
    conn.commit()
    conn.close()

    print("🌱 Seed data loaded successfully!")
    print(f"   • {len(drivers)} drivers")
    print("   • Locations: unlimited (GPT-estimated)")


if __name__ == "__main__":
    seed()

"""
Seed script — populates the database with sample drivers across Kerala.
V2: Drivers stationed across all 14 districts.

Run once:  python seed_data.py
"""

import database as db


def seed():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    # ── SAMPLE DRIVERS (stationed across Kerala — all 14 districts) ──
    drivers = [
        # Thiruvananthapuram
        ("Arun Kumar", "+919876543001", "KL-01-A-1234", "sedan", 1, "Thiruvananthapuram"),
        ("Bindu S", "+919876543002", "KL-01-B-5678", "suv", 1, "Kovalam"),
        # Kollam
        ("Sajan Thomas", "+919876543003", "KL-02-C-9012", "sedan", 1, "Kollam Town"),
        # Pathanamthitta
        ("Reji Mathew", "+919876543004", "KL-03-D-3456", "suv", 1, "Pathanamthitta"),
        # Alappuzha
        ("Vishnu P", "+919876543005", "KL-04-E-7890", "sedan", 1, "Alappuzha"),
        ("Sunil B", "+919876543006", "KL-04-F-1122", "sedan", 1, "Cherthala"),
        # Kottayam
        ("George K", "+919876543007", "KL-05-G-3344", "sedan", 1, "Kottayam"),
        # Idukki
        ("Manoj R", "+919876543008", "KL-06-H-5566", "suv", 1, "Munnar"),
        # Ernakulam
        ("Rajan Pillai", "+919876543009", "KL-07-J-7788", "sedan", 1, "Ernakulam"),
        ("Dileep Das", "+919876543010", "KL-07-K-9900", "sedan", 1, "Fort Kochi"),
        ("Priya M", "+919876543011", "KL-07-L-1010", "suv", 1, "Aluva"),
        # Thrissur
        ("Sathyan M", "+919876543012", "KL-08-M-2020", "sedan", 1, "Thrissur"),
        ("Babu V", "+919876543013", "KL-08-N-3030", "sedan", 1, "Guruvayur"),
        # Palakkad
        ("Suresh Kumar", "+919876543014", "KL-10-P-4040", "sedan", 1, "Palakkad Town"),
        ("Rajesh Nair", "+919876543015", "KL-10-Q-5050", "suv", 1, "Malampuzha"),
        # Malappuram
        ("Shibu S", "+919876543016", "KL-11-R-6060", "sedan", 1, "Malappuram"),
        ("Ajith N", "+919876543017", "KL-11-S-7070", "sedan", 1, "Manjeri"),
        # Kozhikode
        ("Vipin Das", "+919876543018", "KL-12-T-8080", "sedan", 1, "Kozhikode"),
        ("Gireesh R", "+919876543019", "KL-12-U-9090", "suv", 1, "Vadakara"),
        # Wayanad
        ("Deepak K", "+919876543020", "KL-13-V-1111", "suv", 1, "Kalpetta"),
        # Kannur
        ("Pramod V", "+919876543021", "KL-14-W-2222", "sedan", 1, "Kannur"),
        ("Jayan T", "+919876543022", "KL-14-X-3333", "sedan", 1, "Thalassery"),
        # Kasaragod
        ("Vinod G", "+919876543023", "KL-15-Y-4444", "sedan", 1, "Kasaragod"),
        ("Sajith N", "+919876543024", "KL-15-Z-5555", "suv", 1, "Bekal"),
    ]

    for name, phone, vehicle_num, v_type, available, base_area in drivers:
        cur.execute(
            "INSERT OR IGNORE INTO drivers (name, phone, vehicle_number, vehicle_type, is_available, base_area) VALUES (?, ?, ?, ?, ?, ?)",
            (name, phone, vehicle_num, v_type, available, base_area),
        )
    conn.commit()
    conn.close()

    print("🌱 Seed data loaded successfully!")
    print(f"   • {len(drivers)} drivers across all 14 Kerala districts")
    print("   • Locations: unlimited (GPT-estimated, Kerala-wide)")


if __name__ == "__main__":
    seed()

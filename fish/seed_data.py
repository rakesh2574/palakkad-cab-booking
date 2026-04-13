"""Seed Kerala fish catalog."""

from . import database as fdb


KERALA_FISH_CATALOG = [
    {"name": "Seer Fish", "malayalam_name": "Neymeen (നെയ്മീൻ)",
     "speciality": "King of Kerala fish. Firm, meaty, very low bones. Perfect for fry, curry, mappas. Premium price.",
     "typical_price_per_kg": 900},
    {"name": "Pomfret", "malayalam_name": "Aavoli (ആവോലി)",
     "speciality": "Delicate white flesh, mild flavour. Best pan-fried whole or in tamarind curry.",
     "typical_price_per_kg": 800},
    {"name": "Sardine", "malayalam_name": "Mathi / Chaala (മത്തി)",
     "speciality": "Kerala staple. Rich in omega-3. Spicy mulakittathu or fried crisp.",
     "typical_price_per_kg": 180},
    {"name": "Mackerel", "malayalam_name": "Ayala (അയല)",
     "speciality": "Strong flavour, meaty. Excellent for fry and coconut curry.",
     "typical_price_per_kg": 220},
    {"name": "Prawns (Medium)", "malayalam_name": "Chemmeen (ചെമ്മീൻ)",
     "speciality": "Fresh from backwaters. Perfect for roast, biryani, stew.",
     "typical_price_per_kg": 650},
    {"name": "Prawns (Large)", "malayalam_name": "Konju (കൊഞ്ച്)",
     "speciality": "Jumbo size, sweet flesh. Butter garlic roast or Kerala roast. Limited stock.",
     "typical_price_per_kg": 1200},
    {"name": "Pearl Spot", "malayalam_name": "Karimeen (കരിമീൻ)",
     "speciality": "Backwater delicacy, Kerala state fish. Pollichathu in banana leaf is legendary.",
     "typical_price_per_kg": 850},
    {"name": "Red Snapper", "malayalam_name": "Chemballi (ചെമ്പല്ലി)",
     "speciality": "Sweet, firm flesh. Perfect for grilling or masala fry.",
     "typical_price_per_kg": 700},
    {"name": "Tuna", "malayalam_name": "Choora (ചൂര)",
     "speciality": "Meaty, less bones. Great for thick curry and pickle.",
     "typical_price_per_kg": 280},
    {"name": "Squid", "malayalam_name": "Koonthal (കൂന്തൽ)",
     "speciality": "Cleaned and ready. Roast, masala, or fry. Kids love it.",
     "typical_price_per_kg": 500},
    {"name": "Crab", "malayalam_name": "Njandu (ഞണ്ട്)",
     "speciality": "Live backwater crabs. Roast or coconut curry. Weight including shell.",
     "typical_price_per_kg": 600},
    {"name": "Anchovy", "malayalam_name": "Kozhuva / Natholi (നെത്തോലി)",
     "speciality": "Tiny, crispy fry in minutes. Super fresh, great with rice.",
     "typical_price_per_kg": 200},
    {"name": "Barracuda", "malayalam_name": "Sheelavu (ശീലാവ്)",
     "speciality": "Long fish, firm white flesh. Best as thick slices in masala curry.",
     "typical_price_per_kg": 400},
    {"name": "Tilapia", "malayalam_name": "Tilapia",
     "speciality": "Fresh-water fish, mild taste. Economical everyday choice.",
     "typical_price_per_kg": 220},
]


def seed_fish_catalog():
    fdb.init_fish_tables()
    for fish in KERALA_FISH_CATALOG:
        fdb.upsert_fish_catalog(
            name=fish["name"],
            malayalam_name=fish["malayalam_name"],
            speciality=fish["speciality"],
            typical_price=fish["typical_price_per_kg"],
        )
    return len(fdb.get_fish_catalog())


if __name__ == "__main__":
    n = seed_fish_catalog()
    print(f"Seeded fish catalog: {n} varieties.")

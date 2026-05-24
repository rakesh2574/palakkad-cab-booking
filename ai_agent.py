"""
AI Booking Agent — powered by GPT-4o mini.

The agent interprets WhatsApp messages and calls database helpers
to manage bookings. Uses OpenRouteService for real distance/duration.

V3: Vignesh persona, cross-state, round trips, full-day, real routing.
"""

import os
import json
from openai import OpenAI
import database as db
import route_calculator as rc

# Lazy-initialize the OpenAI client (created on first use, not at import time)
_client = None

def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client

# ── Per-customer session state (in-memory; use Redis in production) ──
sessions: dict = {}

RATE_PER_MIN = float(os.getenv("RATE_PER_MIN", "8.0"))

def _build_system_prompt():
    """Build system prompt with today's date so GPT knows what 'nale'/'tomorrow' means."""
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    tomorrow_str = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after_str = (now_ist + timedelta(days=2)).strftime("%Y-%m-%d")
    day_name = now_ist.strftime("%A")
    time_str = now_ist.strftime("%H:%M")

    # Build upcoming weekday map for "next Sunday", "this Friday" etc.
    weekday_map_lines = []
    for i in range(14):  # next 14 days
        d = now_ist + timedelta(days=i)
        label = "today" if i == 0 else "tomorrow" if i == 1 else ""
        weekday_map_lines.append(f"  {d.strftime('%A')} {d.strftime('%Y-%m-%d')}{f' ({label})' if label else ''}")
    weekday_map = "\n".join(weekday_map_lines)

    return f"""You are *Vignesh*, the owner of a driver-on-demand service based in Palakkad, Kerala 🚗.
Customers message you directly on WhatsApp to book drivers. You're like their trusted go-to person for all driver needs.

TODAY'S DATE: {today_str} ({day_name}), Current time: {time_str} IST.
TOMORROW'S DATE: {tomorrow_str}

UPCOMING DAYS (use this to resolve "next Sunday", "this Friday", "varunna Monday", etc.):
{weekday_map}

Use this to correctly interpret dates:
- "today"/"innu" = {today_str}
- "tomorrow"/"nale"/"naale" = {tomorrow_str}
- "day after"/"marranne divasam" = {day_after_str}
- "next [weekday]" / "varunna [weekday]" / "this [weekday]" → look up the UPCOMING DAYS table above
- "adutha aazhcha" / "next week" → the Monday of next week from the table above
CRITICAL: "nale" ALWAYS means {tomorrow_str}, NEVER {today_str}. Double-check your date!

CRITICAL IDENTITY RULES:
- YOUR name is Vignesh. You are the OWNER running this service.
- The CUSTOMER is the person chatting with you. They are NOT Vignesh. NEVER call the customer "Vignesh".
- The customer's name is provided in the system context as [Customer Name: ...]. Use THAT name for the customer.
- If the customer's name shows as "Unknown", ask their name and district (home base). Use set_name to save name.
- If the customer's name is ALREADY KNOWN (not "Unknown"), NEVER ask for their name again. Just greet them and get to business.
- NEVER confuse your own name with the customer's name.

YOUR PERSONALITY & LANGUAGE:
- Professional, warm, and efficient — like a reliable business owner who knows each customer
- ALWAYS reply in FORMAL ENGLISH only. Never use Malayalam/Manglish words in your replies.
- You UNDERSTAND Malayalam/Manglish input perfectly, but you RESPOND only in clear, professional English.
- Keep messages short and WhatsApp-friendly — ask only what's truly missing, never repeat questions.
- NEVER ask for something the customer already told you in this conversation. READ THE CHAT HISTORY.

MANGLISH & MALAYALAM UNDERSTANDING:
Your customers are Malayalis. They write in MANGLISH (Malayalam in English script) or mix Malayalam+English.
You MUST understand these patterns fluently:
- "nale"/"naale" = tomorrow, "innu" = today, "ravile" = morning, "vaikunneram"/"vaikeettu" = evening
- "ethanam"/"ethikaanum" = need to ARRIVE by (this is ARRIVAL/EVENT time, NOT departure!)
- "pokanam"/"pokaam" = need to go/leave (this is DEPARTURE/PICKUP time)
- "manik"/"maniku" = at (time) — "9 manik" = at 9 o'clock
- "seri"/"sheri" = okay, "venda" = don't want/cancel, "shariyaan" = confirmed
- "cab venam"/"driver venam" = need a cab/driver
- "ividunnu" = from here (ask where exactly)
- "UP and DN"/"to and fro" = round trip

TIME UNDERSTANDING:
- "3pm pokanam" / "3 manik pickup" = PICKUP TIME → set report_time="15:00"
- "10 manik ethanam" / "10nu reach aakanam" = ARRIVAL TIME → set event_time="10:00"
  (the system will automatically calculate when driver should pick up based on route duration)
- When customer gives a time like "by 3pm" with a destination, it usually means PICKUP TIME unless they specifically say "reach by" or "ethanam"

WHAT YOU CAN HELP WITH:
- Driver bookings anywhere in Kerala + nearby TN/Karnataka cities
- Round trips, full-day/hourly hire, multi-stop trips, vehicle pickups
- Airport/railway drops and pickups, scheduling, rebooking, cancelling

WHAT YOU MUST POLITELY DECLINE:
- Politics, general knowledge, personal advice, medical, recipes, jokes

COVERAGE AREA:
- Primary: All of Kerala — all 14 districts
- Extended: Coimbatore, Pollachi, Palani, Ooty, Coonoor, Kodaikanal, Madurai, Chennai, Mangalore, Mysore, Bangalore

NEW CUSTOMER ONBOARDING:
When a customer's name is "Unknown", collect this info ONCE (it's saved permanently):
1. Name → save with set_name action
2. District/home base → save in special_notes of first booking OR mention in driving_notes
These are saved in context for all future conversations. Don't ask again.

BOOKING — WHAT YOU NEED (KEEP IT SIMPLE):
To fire create_booking, you need these things. Collect what's missing in ONE natural question, not one at a time:

★ MANDATORY — must have ALL of these before firing create_booking:

1. PICKUP LANDMARK — MUST be a specific place/landmark (driver needs to find the customer!)
   → "Kottayam" or "Palakkad" ALONE is NOT enough for pickup.
   → A DISTRICT NAME IS NOT A PICKUP LOCATION. These are districts, NOT valid pickups:
     Thiruvananthapuram, Kollam, Pathanamthitta, Alappuzha, Kottayam, Idukki, Ernakulam, Kochi,
     Thrissur, Palakkad, Malappuram, Kozhikode, Wayanad, Kannur, Kasaragod
   → If customer says "Palakkad to Kakkanad", you MUST ask: "Where in Palakkad should the driver pick you up? A landmark, bus stand, or area name please."
   → ALWAYS ask for a specific landmark/area when pickup is just a district name. Combine this with other missing items in ONE message.
   → GOOD pickup: "Kattans Hotel Bypass", "Railway Station", "Ramanathapuram", "Bus Stand Kottayam", "Koppam"
   → BAD pickup: "Kottayam", "Palakkad", "Thrissur" (driver won't know where to go!)
   → Customer's home district is known from context. If they say "Koppam" and they're from Palakkad, you know from_district="Palakkad".
   → NEVER fire create_booking with a bare district name as "from". Always get a specific place first.

2. PICKUP DISTRICT — the district where the pickup is (e.g., "Palakkad", "Ernakulam")

3. DROP DISTRICT — where the customer is heading. A district/city name is perfectly fine!
   → "Kochi", "Thrissur", "Ernakulam" are all valid drops — we need at least the district for route/fare calculation.
   → If customer also gives a specific drop landmark (e.g., "Kakkanad"), great — use it as "to" and set to_district="Ernakulam".
   → If customer only gives a district (e.g., "Thrissur"), set to="Thrissur" and to_district="Thrissur". That's fine — the driver will get the exact spot during the ride.
   → Do NOT insist on a specific landmark for drop — district is enough.

4. DATE — today/tomorrow/specific date

5. TIME — pickup time or arrival time
   → This is the ONLY time you need. It's either when the driver should come (report_time) or when customer needs to reach (event_time).
   → NEVER ask for "drop time" or "arrival time at destination" — the customer doesn't know that, it depends on traffic!
   → If they said "by 3pm" in an earlier message, USE IT. Don't ask again.

★ OPTIONAL — nice to have, but NOT required:

6. NOTES — any preferences (optional, don't push for it)

CONTACT NUMBER HANDLING:
- You already have the customer's WhatsApp number from the system context.
- Before confirming any booking, ask: "Shall I proceed with the same contact number, or would you like to update it for this trip?"
- This covers cases where they're booking for someone else (family member, colleague, etc.)
- If they say "same number", "this one", "yes" → use their WhatsApp number from context (set contact_phone to null, system will use WhatsApp number)
- If they give a different number → save it in contact_phone
- NEVER bluntly ask "What is your phone number?" — you already have it!

⛔ CRITICAL DON'TS:
- NEVER ask for the customer's name if it's already known (not "Unknown" in context). Just greet and proceed.
- NEVER bluntly ask "What is your phone number?" — you already have it!
- NEVER validate times yourself! Do NOT compare the current time with the requested time. Just accept whatever time the customer gives and fire create_booking — the SYSTEM will check if the time has passed and show an error if needed. You are NOT a clock.
  ❌ BAD: "3 PM has already passed" (YOU DON'T KNOW THIS — the system checks it!)
  ❌ BAD: "The time of 5:30 PM is in the future, so this is valid."
  ✅ GOOD: Just fire create_booking with report_time="15:00" and let the system handle validation.
- NEVER ask for "drop time" or "how long the trip will take" — the system calculates this.
- NEVER ask the same question twice — read the conversation history!
- NEVER ask questions one by one in separate messages — combine missing items into ONE message.
- NEVER invent a time — if customer didn't say when, ask ONCE.
- For multiple trips: each trip needs its OWN time. Don't copy time from one trip to another.
- NEVER expose internal calculations or technical details to the customer! You are a business owner, not a computer.
  ❌ BAD: "The current time is 11:35 AM, and the requested pickup time of 5:30 PM is in the future, so this is valid."
  ❌ BAD: "I've calculated the route distance as 85.2 km and estimated duration is 2 hours 15 minutes with buffer."
  ❌ BAD: "The system shows travel_date is 2026-05-25 which is a valid future date."
  ✅ GOOD: "5:30 PM this evening — got it! Let me check the route for you."
  ✅ GOOD: "Sure, I'll arrange a driver for tomorrow morning at 9 AM."
  ✅ GOOD: "Got it — pickup from Koppam to Kakkanad on the 25th at 6 AM. Let me check availability."
  Just acknowledge what the customer said naturally and move forward. No internal timestamps, no "current time is X", no validation commentary.

BOOKING FLOW:
1. Customer says what they need → extract as much as possible from their message
2. If anything from the 5 items above is missing, ask for ALL missing items in ONE message
3. Once you have everything → fire create_booking immediately with a short acknowledgment
   "Sure, let me check the route and arrange a driver for you!"
4. The system shows a CONFIRMATION PREVIEW with real route data. Customer confirms → booking created.
5. Do NOT estimate distance/fare/time yourself — the system does this automatically.

MULTIPLE BOOKINGS:
If customer requests multiple trips in one message:
- Extract what you can for each trip
- Ask for missing details for ALL trips in ONE combined message
- Each trip's time is independent — never copy time between trips
- Use create_multiple_bookings when all trips are complete

You MUST respond with a JSON object (and nothing else) in this format:
{{{{
  "reply": "Your WhatsApp reply message to the customer",
  "action": null or one of ["set_name", "create_booking", "create_multiple_bookings", "check_bookings", "cancel_booking", "save_preferences"],
  "action_data": {{{{}}}}
}}}}

For "set_name" action_data: {{{{ "name": "Customer Name" }}}}
For "create_booking" action_data:
  ── MANDATORY FIELDS (do NOT fire create_booking without these): ──
  {{{{
    "from": "Specific pickup landmark (e.g., 'Koppam', 'Railway Station', 'Bus Stand')",
    "from_district": "District of pickup (e.g., 'Palakkad', 'Ernakulam')",
    "to": "Drop location — district name is fine (e.g., 'Thrissur', 'Kochi') or specific (e.g., 'Kakkanad')",
    "to_district": "District of drop (e.g., 'Ernakulam', 'Thrissur'). If customer just says 'Thrissur', set both to='Thrissur' and to_district='Thrissur'.",
    "travel_date": "YYYY-MM-DD (use {today_str} for today, {tomorrow_str} for tomorrow)",
    "report_time": "HH:MM" or null (pickup/departure time — when driver should come),
    "event_time": "HH:MM" or null (arrival time — when customer must reach destination)
  }}}}
  → At least ONE of report_time or event_time MUST be provided.
  → "ethanam"/"reach by X" → set event_time. "pokanam"/"leave at X" → set report_time.

  ── OPTIONAL FIELDS (include when available): ──
  {{{{
    "trip_type": "one_way" (default) / "round_trip" / "full_day",
    "booking_type": "point_to_point" (default) / "hourly" / "full_day" / "vehicle_pickup",
    "contact_name": "Third-party contact name if booking for someone else",
    "contact_phone": "Different phone number if not the customer's WhatsApp",
    "stops": ["Intermediate stop 1", "Stop 2"],
    "vehicle_info": "Car details for vehicle pickup jobs",
    "special_notes": "Any notes, preferences, e-pass, documents",
    "driving_notes": "Speed preference, route preference etc.",
    "end_time": "HH:MM — for full-day/hourly hires",
    "travel_dates": ["YYYY-MM-DD", ...] — for multi-day bookings,
    "customer_name": "Name if new customer just shared it"
  }}}}

  RULES:
  • DISTRICT FIELDS ARE MANDATORY. If unsure which district, ASK the customer.
  • Outside Kerala → use city name as district (e.g., "Coimbatore", "Bangalore").
  • "nale"/"tomorrow" = {tomorrow_str}. Always calculate from today = {today_str}.
  • trip_type: "round_trip" for to-and-fro / UP-DN trips.
For "create_multiple_bookings" action_data: {{{{
  "bookings": [
    {{{{ same fields as create_booking above }}}},
    {{{{ same fields as create_booking above }}}}
  ]
}}}}
For "check_bookings" action_data: {{{{}}}}
For "cancel_booking" action_data: {{{{ "booking_id": 123 }}}}
For "save_preferences" action_data: {{{{ "preferred_speed": "slow/normal/fast", "driving_notes": "any notes" }}}}
"""


def _get_conversation_history(customer_id: int, limit: int = 10) -> list[dict]:
    """Pull recent conversation from DB to feed as context."""
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT direction, message FROM conversations WHERE customer_id = ? ORDER BY id DESC LIMIT ?",
        (customer_id, limit),
    ).fetchall()
    conn.close()
    history = []
    for r in reversed(rows):
        role = "user" if r["direction"] == "in" else "assistant"
        history.append({"role": role, "content": r["message"]})
    return history


def process_message(phone: str, incoming_msg: str) -> str:
    """
    Main entry point: take an incoming WhatsApp message,
    run it through GPT-4o mini, execute any actions, return reply text.
    """
    # 1. Get or create the customer
    customer = db.get_or_create_customer(phone)
    customer_id = customer["id"]

    # 2. Log incoming message
    db.log_conversation(customer_id, "in", incoming_msg)

    # 2b. Check for pending booking confirmation
    session = sessions.get(phone, {})
    pending = session.get("pending_booking")
    if pending:
        # Check if customer is confirming or rejecting
        msg_lower = incoming_msg.strip().lower()
        confirm_words = {"yes", "ya", "yep", "ok", "okay", "seri", "sheri", "sheriyaan",
                         "sheriyano", "athe", "poyikko", "book", "confirm", "book cheyy",
                         "book cheyyoo", "go ahead", "proceed", "aam", "hmm", "done",
                         "shariyaan", "shari", "angane", "angane aavatte", "aakatte",
                         "sure", "thanne", "avide thanne", "correct"}
        reject_words = {"no", "nope", "venda", "vendaa", "alla", "allaa", "cancel",
                        "vende", "change", "maaranam", "maattanam", "wrong", "thettaanu"}

        is_confirm = any(w in msg_lower for w in confirm_words)
        is_reject = any(w in msg_lower for w in reject_words)

        if is_confirm and not is_reject:
            # Customer confirmed — actually create the booking(s) now
            if pending.get("multiple"):
                # Multiple bookings
                replies = []
                for bk in pending["bookings"]:
                    r = _handle_create_booking(customer_id, bk["action_data"], bk["route_data"])
                    replies.append(r)
                reply = "\n\n---\n\n".join(replies)
            else:
                reply = _handle_create_booking(customer_id, pending["action_data"], pending["route_data"])
            sessions.pop(phone, None)
            db.log_conversation(customer_id, "out", reply)
            return reply
        elif is_reject and len(msg_lower.split()) <= 3:
            # Only treat as cancellation if it's a SHORT rejection like "no", "venda", "cancel"
            # If the message is longer (e.g., "no, I said 6 AM today"), it's a CORRECTION — let GPT handle it
            sessions.pop(phone, None)
            reply = "No problem, the booking has been cancelled. Would you like to make any changes and rebook? 🙏"
            db.log_conversation(customer_id, "out", reply)
            return reply
        # Longer messages with "no" or corrections — let GPT handle and re-propose
        sessions.pop(phone, None)

    # 3. Build messages for OpenAI
    messages = [{"role": "system", "content": _build_system_prompt()}]

    # Add customer context
    cust_name = customer['name']
    pref_speed = customer.get('preferred_speed') or ''
    pref_notes = customer.get('driving_notes') or ''

    if cust_name == "Unknown":
        customer_context = f"[CUSTOMER INFO — Phone: {phone} (ALREADY KNOWN — never ask for phone number!), Name: not yet known (ask their name and home district). YOU are Vignesh, the service owner.]"
    else:
        customer_context = f"[CUSTOMER INFO — Phone: {phone} (ALREADY KNOWN — never ask for phone number!), Customer Name: {cust_name}. YOU are Vignesh the service owner. The CUSTOMER's name is {cust_name}.]"

    # Add driving preferences if known
    if pref_speed or pref_notes:
        customer_context += f"\n[DRIVING PREFERENCES — Speed: {pref_speed or 'not set'}, Notes: {pref_notes or 'none'}. Use these to personalize the experience.]"

    # Add recent bookings
    recent_bookings = db.get_customer_bookings(customer_id, limit=3)
    if recent_bookings:
        booking_summary = "\n".join(
            f"  - #{b['id']}: {b['pickup_location']} → {b['drop_location']} | {b['status']} | ₹{b['fare'] or 'TBD'} | Date: {b.get('travel_date') or 'immediate'}"
            for b in recent_bookings
        )
        customer_context += f"\n[Recent bookings:\n{booking_summary}]"

    # Add frequent routes for smart rebooking
    frequent_routes = db.get_customer_frequent_routes(customer_id, limit=3)
    if frequent_routes:
        route_summary = "\n".join(
            f"  - {r['pickup_location']} → {r['drop_location']} ({r['trip_count']} trips, ~{r['avg_distance']} km)"
            for r in frequent_routes
        )
        customer_context += f"\n[FREQUENT ROUTES (suggest rebooking!):\n{route_summary}]"

    messages.append({"role": "system", "content": customer_context})

    # Add conversation history
    history = _get_conversation_history(customer_id, limit=10)
    messages.extend(history)

    # Add current message
    messages.append({"role": "user", "content": incoming_msg})

    # 4. Call GPT-4o mini
    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        result = json.loads(raw)
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        reply = "Sorry, I'm having a small technical issue. Please try again in a moment! 🙏"
        db.log_conversation(customer_id, "out", reply)
        return reply

    reply = result.get("reply", "Sorry, I didn't understand that. Could you rephrase?")
    action = result.get("action")
    action_data = result.get("action_data", {})

    # 5. Execute actions
    if action == "set_name":
        name = action_data.get("name", "").strip()
        if name:
            db.update_customer_name(phone, name)

    elif action == "create_booking":
        # Store proposed booking in session — DON'T create yet
        # The confirmation message with real route data will be sent
        reply = _handle_propose_booking(customer_id, phone, action_data, reply)

    elif action == "create_multiple_bookings":
        # Handle multiple bookings in one message
        bookings_list = action_data.get("bookings", [])
        if not bookings_list:
            reply = "I couldn't identify the booking details. Could you please describe each trip separately?"
        else:
            reply = _handle_propose_multiple_bookings(customer_id, phone, bookings_list, reply)

    elif action == "check_bookings":
        bookings = db.get_customer_bookings(customer_id, limit=5)
        if bookings:
            lines = []
            for b in bookings:
                fare_str = f"₹{b['fare']}" if b["fare"] else "pending"
                date_str = f" | 📅 {b.get('travel_date') or 'immediate'}" if b.get('travel_date') else ""
                lines.append(
                    f"🚗 #{b['id']}: {b['pickup_location']} → {b['drop_location']} | {b['status']} | {fare_str}{date_str}"
                )
            reply += "\n\n" + "\n".join(lines)
        else:
            reply += "\n\nYou don't have any bookings yet!"

    elif action == "cancel_booking":
        bid = action_data.get("booking_id")
        if bid:
            db.cancel_booking(bid)

    elif action == "save_preferences":
        pref_speed = action_data.get("preferred_speed")
        pref_notes = action_data.get("driving_notes")
        if pref_speed or pref_notes:
            db.update_customer_preferences(phone, pref_speed, pref_notes)

    # 6. Log outgoing message
    db.log_conversation(customer_id, "out", reply)

    return reply


BUFFER_MINUTES = int(os.getenv("BUFFER_MINUTES", "60"))

# Kerala district names — used to detect when GPT sends just a district name
# instead of a specific place/landmark as pickup or drop
KERALA_DISTRICTS = {
    "thiruvananthapuram", "trivandrum", "kollam", "pathanamthitta", "alappuzha",
    "alleppey", "kottayam", "idukki", "ernakulam", "kochi", "cochin",
    "thrissur", "trichur", "palakkad", "palghat", "malappuram", "kozhikode",
    "calicut", "wayanad", "kannur", "cannanore", "kasaragod",
}


def _is_just_district(place: str) -> bool:
    """Check if a place name is just a district/city name without a specific landmark."""
    normalized = place.strip().lower()
    # Remove common suffixes
    for suffix in [" town", " city", " district"]:
        normalized = normalized.replace(suffix, "")
    normalized = normalized.strip()
    return normalized in KERALA_DISTRICTS

# Ghat / mountain road destinations — ORS underestimates these by 30-50%
# because it doesn't account for hairpin bends, steep gradients, slow trucks, fog
GHAT_KEYWORDS = {
    "munnar", "wayanad", "kalpetta", "sultan bathery", "sulthan bathery",
    "mananthavady", "ooty", "coonoor", "kodaikanal", "vagamon", "ponmudi",
    "nelliyampathy", "silent valley", "agumbe", "coorg", "madikeri",
    "valparai", "topslip", "parambikulam", "thekkady", "kumily", "idukki",
    "devikulam", "vythiri", "lakkidi", "thamarassery", "nilambur",
}


def _is_ghat_route(from_name: str, to_name: str, stops: list = None) -> bool:
    """Check if route passes through known ghat/hill sections."""
    all_places = [from_name, to_name] + (stops or [])
    text = " ".join(all_places).lower()
    return any(kw in text for kw in GHAT_KEYWORDS)


def _build_geocode_name(place: str, district: str) -> str:
    """Combine place name with district for accurate geocoding.
    e.g., 'Koppam' + 'Palakkad' → 'Koppam, Palakkad, Kerala, India'"""
    if not district:
        return place
    # Don't duplicate if place already contains the district
    if district.lower() in place.lower():
        return f"{place}, Kerala, India"
    return f"{place}, {district}, Kerala, India"


def _compute_route_data(action_data: dict) -> dict:
    """Call OpenRouteService to get real distance/duration and compute fare.
    Returns a dict with all computed route info."""
    from_name = action_data.get("from", "")
    to_name = action_data.get("to", "")
    from_district = action_data.get("from_district", "")
    to_district = action_data.get("to_district", "")
    est_distance = action_data.get("est_distance_km", 10.0)
    est_duration = action_data.get("est_duration_min", 20)
    trip_type = action_data.get("trip_type", "one_way")
    booking_type = action_data.get("booking_type", "point_to_point")
    stops = action_data.get("stops")
    event_time = action_data.get("event_time")

    route_source = "gpt_estimate"
    is_ghat = _is_ghat_route(from_name, to_name, stops)

    # Build geocode-friendly names with district for accurate location matching
    from_geocode = _build_geocode_name(from_name, from_district)
    to_geocode = _build_geocode_name(to_name, to_district)

    # ── REAL ROUTING via OpenRouteService ──
    if stops and isinstance(stops, list) and len(stops) > 0:
        all_places = [from_geocode] + stops + [to_geocode]
        route = rc.get_route_with_stops(all_places)
        if route:
            est_distance = route["distance_km"]
            est_duration = route["duration_min"]
            route_source = "openrouteservice"
            print(f"📍 Multi-stop route: {' → '.join(all_places)} = {est_distance}km, {est_duration}min")
    else:
        route = rc.get_route(from_geocode, to_geocode)
        if route:
            est_distance = route["distance_km"]
            est_duration = route["duration_min"]
            route_source = "openrouteservice"
            print(f"📍 Route: {from_geocode} → {to_geocode} = {est_distance}km, {est_duration}min")
        else:
            print(f"⚠️ Route API failed for {from_geocode} → {to_geocode}, using GPT estimate")

    # For ghat/mountain routes, add 80% to ORS duration (it severely underestimates
    # hairpin bends, steep gradients, slow trucks, fog on ghat roads)
    if is_ghat and route_source == "openrouteservice":
        original = est_duration
        est_duration = int(est_duration * 1.8)
        print(f"⛰️ Ghat route detected! Duration adjusted: {original}min → {est_duration}min (+80%)")

    # Add buffer (30 min default) to duration for real-world conditions
    est_duration_with_buffer = est_duration + BUFFER_MINUTES
    est_fare = round(est_duration_with_buffer * RATE_PER_MIN, 2)

    # Adjust for round trips
    if trip_type == "round_trip":
        if route_source == "openrouteservice":
            return_route = rc.get_route(to_geocode, from_geocode)
            if return_route:
                est_distance = round(est_distance + return_route["distance_km"], 1)
                return_duration = return_route["duration_min"]
                est_duration = est_duration + return_duration
                est_duration_with_buffer = est_duration + BUFFER_MINUTES * 2  # buffer for both legs
                est_fare = round(est_duration_with_buffer * RATE_PER_MIN, 2)
                print(f"🔄 Round trip total: {est_distance}km, {est_duration}min")
            else:
                est_distance = round(est_distance * 1.8, 1)
                est_duration_with_buffer = int(est_duration * 1.8) + BUFFER_MINUTES * 2
                est_fare = round(est_duration_with_buffer * RATE_PER_MIN, 2)
        else:
            est_distance = round(est_distance * 1.8, 1)
            est_duration_with_buffer = int(est_duration * 1.8) + BUFFER_MINUTES * 2
            est_fare = round(est_duration_with_buffer * RATE_PER_MIN, 2)
    elif trip_type == "full_day" or booking_type == "full_day":
        est_fare = round(RATE_PER_MIN * max(est_duration_with_buffer, 480), 2)

    # Calculate suggested report time if customer gave ONLY arrival (event) time
    # If customer gave BOTH report_time AND event_time, report_time wins (they said when to pick up)
    DRIVER_EARLY_BUFFER = 15
    suggested_report_time = None
    report_time = action_data.get("report_time")

    if event_time and not report_time and est_duration:
        # Customer only gave arrival time — back-calculate pickup time
        try:
            from datetime import datetime, timedelta
            evt = datetime.strptime(event_time, "%H:%M")
            # departure = arrival_time - travel_duration - buffer
            depart = evt - timedelta(minutes=est_duration + BUFFER_MINUTES)
            # driver arrives 15 min before departure, rounded down to nearest 5 min
            report = depart - timedelta(minutes=DRIVER_EARLY_BUFFER)
            # Round down to nearest 5 minutes
            report = report.replace(minute=(report.minute // 5) * 5)
            suggested_report_time = report.strftime("%H:%M")
            print(f"🕐 Event at {event_time}, travel {est_duration}min + {BUFFER_MINUTES}min buffer → depart {depart.strftime('%H:%M')} → driver report at {suggested_report_time}")
        except Exception:
            pass
    elif event_time and report_time:
        # Customer gave both pickup AND arrival time — pickup time takes priority
        print(f"🕐 Customer gave both report_time={report_time} and event_time={event_time}. Using customer's pickup time.")

    return {
        "distance_km": est_distance,
        "duration_min": est_duration,
        "duration_with_buffer_min": est_duration_with_buffer,
        "fare": est_fare,
        "route_source": route_source,
        "suggested_report_time": suggested_report_time,
        "is_ghat": is_ghat,
    }


def _handle_propose_booking(customer_id: int, phone: str, action_data: dict, gpt_reply: str) -> str:
    """Compute route, show preview, and ask customer to confirm before creating booking."""
    from_name = action_data.get("from", "")
    to_name = action_data.get("to", "")

    if not from_name or not to_name:
        missing = []
        if not from_name:
            missing.append("pickup location (with a landmark or area name)")
        if not to_name:
            missing.append("drop-off location (even a district name is fine)")
        return f"Could you please share the {' and '.join(missing)}? I'll arrange a driver right away! 🚗"

    # Catch nonsensical same-location trips
    if from_name.strip().lower() == to_name.strip().lower():
        return f"The pickup and drop location are both '{from_name}'. Could you please clarify the correct pickup and destination?"

    # ── PICKUP MUST BE SPECIFIC (not just a district name) ──
    # Pickup needs a specific landmark/area so the driver knows where to go
    if _is_just_district(from_name):
        from_district = action_data.get("from_district", from_name)
        return f"Could you share a specific pickup location in {from_district}? For example, a landmark, hotel, bus stand, or area name — so the driver knows exactly where to come."

    # Drop can be just a district/city — that's fine, they're heading to that area
    # Drop can also be empty — customer may decide during the ride
    # But if from_district or to_district is missing, fill from the name if possible
    if not action_data.get("from_district"):
        action_data["from_district"] = from_name.split(",")[-1].strip() if "," in from_name else ""
    if not action_data.get("to_district"):
        if _is_just_district(to_name):
            action_data["to_district"] = to_name
        else:
            action_data["to_district"] = to_name.split(",")[-1].strip() if "," in to_name else ""

    # ── PAST DATE VALIDATION ──
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    travel_date_val = action_data.get("travel_date")
    travel_dates_val = action_data.get("travel_dates")

    # Check single travel_date
    if travel_date_val:
        try:
            if travel_date_val < today_str:
                return f"Sorry, {travel_date_val} is a past date. Could you please provide a valid future date? Today is {today_str}. 🙏"
        except Exception:
            pass

    # Check multi-date travel_dates
    if travel_dates_val and isinstance(travel_dates_val, list):
        past_dates = [d for d in travel_dates_val if d < today_str]
        if past_dates:
            return f"Sorry, these dates are in the past: {', '.join(past_dates)}. Could you please provide valid future dates? Today is {today_str}. 🙏"

    # ── PAST TIME VALIDATION (for today's bookings) ──
    # If booking is for today, check if the pickup/report time has already passed
    report_time_val = action_data.get("report_time")
    event_time_val = action_data.get("event_time")
    pickup_time_str = report_time_val or event_time_val  # whichever was given
    is_today = (travel_date_val == today_str) or (not travel_date_val)  # null date = immediate/today

    if is_today and pickup_time_str:
        try:
            pickup_hour, pickup_min = map(int, pickup_time_str.split(":"))
            current_hour = now_ist.hour
            current_min = now_ist.minute
            if pickup_hour < current_hour or (pickup_hour == current_hour and pickup_min <= current_min):
                current_time_str = now_ist.strftime("%I:%M %p").lstrip("0")
                # Format pickup time for display (e.g., "15:00" → "3:00 PM")
                try:
                    from datetime import datetime as _dt
                    pickup_display = _dt.strptime(pickup_time_str, "%H:%M").strftime("%I:%M %p").lstrip("0")
                except Exception:
                    pickup_display = pickup_time_str
                return f"That time has already passed — it's {current_time_str} now. Would you like to schedule for a later time today, or shall we book for tomorrow? 🙏"
        except Exception:
            pass

    # Save customer name if provided
    cust_name = action_data.get("customer_name")
    if cust_name:
        db.update_customer_name(phone, cust_name)

    # Get real route data
    route_data = _compute_route_data(action_data)

    # Store in session for confirmation
    sessions[phone] = {
        "pending_booking": {
            "action_data": action_data,
            "route_data": route_data,
        }
    }

    # Build preview message
    trip_type = action_data.get("trip_type", "one_way")
    booking_type = action_data.get("booking_type", "point_to_point")
    report_time = action_data.get("report_time")
    event_time = action_data.get("event_time")
    travel_date = action_data.get("travel_date")
    travel_dates = action_data.get("travel_dates")
    stops = action_data.get("stops")
    vehicle_info = action_data.get("vehicle_info")
    contact_name = action_data.get("contact_name")
    special_notes = action_data.get("special_notes")
    end_time = action_data.get("end_time")

    trip_label = {"round_trip": "🔄 Round Trip", "full_day": "📆 Full Day", "one_way": "➡️ One Way"}.get(trip_type, "")

    # Convert duration to hours and minutes for display
    dur = route_data['duration_with_buffer_min']
    dur_hours = dur // 60
    dur_mins = dur % 60
    if dur_hours > 0 and dur_mins > 0:
        dur_display = f"~{dur_hours} hr {dur_mins} min"
    elif dur_hours > 0:
        dur_display = f"~{dur_hours} hr"
    else:
        dur_display = f"~{dur_mins} min"

    lines = [
        "Thanks for the details! 🙏",
        "Checked route and driver availability — here's what I have:",
        "",
    ]
    if trip_label:
        lines.append(trip_label)

    from_district = action_data.get("from_district", "")
    to_district = action_data.get("to_district", "")
    from_display = f"{from_name}, {from_district}" if from_district and from_district.lower() not in from_name.lower() else from_name
    to_display = f"{to_name}, {to_district}" if to_district and to_district.lower() not in to_name.lower() else to_name

    if booking_type == "vehicle_pickup" and vehicle_info:
        lines.append(f"🚘 *Vehicle:* {vehicle_info}")
        lines.append(f"📍 *Pickup from:* {from_display}")
        lines.append(f"📍 *Deliver to:* {to_display}")
    else:
        lines.append(f"📍 *Pickup:* {from_display}")
        lines.append(f"📍 *Drop:* {to_display}")

    if stops and isinstance(stops, list):
        lines.append(f"🛑 *Stops:* {' → '.join(stops)}")

    # Dates
    if travel_dates and isinstance(travel_dates, list) and len(travel_dates) > 1:
        lines.append(f"📅 *Dates:* {', '.join(travel_dates)}")
    elif travel_date:
        lines.append(f"📅 *Date:* {travel_date}")

    # Time handling — priority: customer's explicit pickup time > calculated pickup from event time
    if report_time and event_time:
        lines.append(f"🚗 *Driver will pick you up at:* {report_time}")
        lines.append(f"🎯 *Target arrival:* {event_time}")
    elif event_time:
        lines.append(f"🕐 *Reach by:* {event_time}")
        if route_data.get("suggested_report_time"):
            lines.append(f"🚗 *Driver will pick you up at:* {route_data['suggested_report_time']}")
    elif report_time:
        lines.append(f"🚗 *Driver will pick you up at:* {report_time}")
    if end_time:
        lines.append(f"🏁 *Until:* {end_time}")

    # Route info
    lines.append(f"📏 *Distance:* {route_data['distance_km']} km")
    ghat_note = " ⛰️" if route_data.get("is_ghat") else ""
    lines.append(f"⏱️ *Est. travel time:* {dur_display}{ghat_note}")
    lines.append(f"💰 *Est. Fare:* ₹{route_data['fare']}")

    if contact_name:
        lines.append(f"👤 *Contact:* {contact_name}")
    if special_notes:
        lines.append(f"📝 *Notes:* {special_notes}")

    lines.append("")
    lines.append("*Shall I confirm this booking?* ✅")
    lines.append("(Reply *Yes* to book, or let me know what to change)")

    return "\n".join(lines)


def _handle_propose_multiple_bookings(customer_id: int, phone: str, bookings_list: list, gpt_reply: str) -> str:
    """Compute routes for multiple bookings, show combined preview, ask for confirmation."""
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    all_previews = []
    all_booking_data = []

    for i, bd in enumerate(bookings_list, 1):
        from_name = bd.get("from", "")
        to_name = bd.get("to", "")

        if not from_name or not to_name:
            return f"Trip #{i} is missing pickup or drop-off location. Could you please provide the complete details for all trips?"

        # Catch nonsensical same-location trips (e.g., "Kochi → Kochi")
        if from_name.strip().lower() == to_name.strip().lower():
            return f"Trip #{i} has the same pickup and drop location ({from_name}). Could you please clarify the correct pickup and destination?"

        # Pickup must be specific, not just a district name
        if _is_just_district(from_name):
            from_district = bd.get("from_district", from_name)
            return f"Trip #{i}: Could you share a specific pickup location in {from_district}? A landmark, hotel, bus stand, or area name would help the driver."

        # Check for missing date
        if not bd.get("travel_date"):
            return f"Trip #{i} ({from_name} → {to_name}) is missing the travel date. Could you please share when this trip should be?"

        # Past date check
        travel_date_val = bd.get("travel_date")
        if travel_date_val and travel_date_val < today_str:
            return f"Trip #{i} has a past date ({travel_date_val}). Please provide a valid future date. Today is {today_str}. 🙏"

        # Save customer name if provided
        cust_name = bd.get("customer_name")
        if cust_name:
            db.update_customer_name(phone, cust_name)

        route_data = _compute_route_data(bd)

        all_booking_data.append({
            "action_data": bd,
            "route_data": route_data,
        })

        # Build mini-preview for this trip
        trip_type = bd.get("trip_type", "one_way")
        report_time = bd.get("report_time")
        event_time = bd.get("event_time")
        travel_date = bd.get("travel_date")

        dur = route_data['duration_with_buffer_min']
        dur_hours = dur // 60
        dur_mins = dur % 60
        if dur_hours > 0 and dur_mins > 0:
            dur_display = f"~{dur_hours} hr {dur_mins} min"
        elif dur_hours > 0:
            dur_display = f"~{dur_hours} hr"
        else:
            dur_display = f"~{dur_mins} min"

        trip_label = {"round_trip": "Round Trip", "full_day": "Full Day", "one_way": "One Way"}.get(trip_type, "One Way")
        ghat_note = " ⛰️" if route_data.get("is_ghat") else ""

        bd_from_district = bd.get("from_district", "")
        bd_to_district = bd.get("to_district", "")
        from_display = f"{from_name}, {bd_from_district}" if bd_from_district and bd_from_district.lower() not in from_name.lower() else from_name
        to_display = f"{to_name}, {bd_to_district}" if bd_to_district and bd_to_district.lower() not in to_name.lower() else to_name

        preview_lines = [f"*Trip #{i}* ({trip_label})"]
        preview_lines.append(f"  📍 {from_display} → {to_display}")
        if travel_date:
            preview_lines.append(f"  📅 {travel_date}")
        if event_time:
            preview_lines.append(f"  🕐 Reach by: {event_time}")
            if route_data.get("suggested_report_time"):
                preview_lines.append(f"  🚗 Pickup at: {route_data['suggested_report_time']}")
        elif report_time:
            preview_lines.append(f"  🚗 Pickup at: {report_time}")
        preview_lines.append(f"  📏 {route_data['distance_km']} km | ⏱️ {dur_display}{ghat_note}")
        preview_lines.append(f"  💰 ₹{route_data['fare']}")

        all_previews.append("\n".join(preview_lines))

    # Store all bookings in session
    sessions[phone] = {
        "pending_booking": {
            "multiple": True,
            "bookings": all_booking_data,
        }
    }

    # Build combined preview
    total_fare = sum(b["route_data"]["fare"] for b in all_booking_data)
    lines = [
        f"Thanks for the details! Here are your {len(bookings_list)} trips:",
        "",
    ]
    lines.extend(all_previews)
    lines.append("")
    lines.append(f"💰 *Total Est. Fare:* ₹{total_fare}")
    lines.append("")
    lines.append("*Shall I confirm all bookings?* ✅")
    lines.append("(Reply *Yes* to book all, or let me know what to change)")

    return "\n\n".join([lines[0]] + ["\n".join(lines[1:])])


def _handle_create_booking(customer_id: int, action_data: dict, route_data: dict) -> str:
    """Actually create booking(s) after customer confirmation."""
    from_name = action_data.get("from", "")
    to_name = action_data.get("to", "")
    from_district = action_data.get("from_district", "")
    to_district = action_data.get("to_district", "")
    travel_time = action_data.get("travel_time")
    driving_notes = action_data.get("driving_notes")
    trip_type = action_data.get("trip_type", "one_way")
    booking_type = action_data.get("booking_type", "point_to_point")
    report_time = action_data.get("report_time")
    event_time = action_data.get("event_time")
    end_time = action_data.get("end_time")
    contact_name = action_data.get("contact_name")
    contact_phone = action_data.get("contact_phone")
    stops = action_data.get("stops")
    vehicle_info = action_data.get("vehicle_info")
    special_notes = action_data.get("special_notes")
    reminder_time = action_data.get("reminder_time")

    # Build display names with district
    from_display = f"{from_name}, {from_district}" if from_district and from_district.lower() not in from_name.lower() else from_name
    to_display = f"{to_name}, {to_district}" if to_district and to_district.lower() not in to_name.lower() else to_name

    # Use suggested report time if customer gave arrival time but no explicit report time
    if not report_time and route_data.get("suggested_report_time"):
        report_time = route_data["suggested_report_time"]

    est_distance = route_data["distance_km"]
    est_duration = route_data["duration_with_buffer_min"]
    est_fare = route_data["fare"]

    # Handle dates
    travel_dates = action_data.get("travel_dates")
    travel_date = action_data.get("travel_date")
    if travel_dates and isinstance(travel_dates, list) and len(travel_dates) > 0:
        dates = travel_dates
    elif travel_date:
        dates = [travel_date]
    else:
        dates = [None]

    driver = db.find_available_driver()
    if not driver:
        return "Sorry, all our drivers are currently busy. Could you please try again in about 10 minutes? 🙏"

    common = dict(
        customer_id=customer_id,
        driver_id=driver["id"],
        pickup_location=from_display,
        drop_location=to_display,
        distance_km=est_distance,
        est_duration_min=est_duration,
        travel_time=travel_time,
        driving_notes=driving_notes,
        trip_type=trip_type,
        booking_type=booking_type,
        report_time=report_time,
        event_time=event_time,
        end_time=end_time,
        contact_name=contact_name,
        contact_phone=contact_phone,
        stops=stops,
        vehicle_info=vehicle_info,
        special_notes=special_notes,
        reminder_time=reminder_time,
    )

    # Multi-date bookings
    if len(dates) > 1:
        booking_ids = []
        for d in dates:
            bid, _ = db.create_booking(travel_date=d, **common)
            booking_ids.append((bid, d))
        total_fare = est_fare * len(dates)
        return _format_multi_date_confirmation(
            booking_ids, from_display, to_display, driver, est_distance, est_duration,
            est_fare, total_fare, travel_time, report_time, event_time,
            trip_type, booking_type, contact_name, contact_phone,
            vehicle_info, stops, special_notes, driving_notes,
        )

    # Single date / immediate
    single_date = dates[0]
    booking_id, status = db.create_booking(travel_date=single_date, **common)
    return _format_single_confirmation(
        booking_id, status, from_display, to_display, driver, single_date,
        est_distance, est_duration, est_fare, travel_time, report_time,
        event_time, end_time, trip_type, booking_type, contact_name,
        contact_phone, vehicle_info, stops, special_notes, driving_notes,
    )


def _format_single_confirmation(booking_id, status, from_name, to_name, driver,
                                 travel_date, est_distance, est_duration, est_fare,
                                 travel_time, report_time, event_time, end_time,
                                 trip_type, booking_type, contact_name, contact_phone,
                                 vehicle_info, stops, special_notes, driving_notes):
    """Format a rich confirmation message for a single booking."""
    header = "📅 *Scheduled!*" if status == "scheduled" else "✅ *Confirmed!*"
    trip_label = {"round_trip": "🔄 Round Trip", "full_day": "📆 Full Day", "one_way": "➡️ One Way"}.get(trip_type, "")
    type_label = {"vehicle_pickup": "🚘 Vehicle Pickup", "hourly": "⏰ Hourly Hire", "full_day": "📆 Full Day Hire"}.get(booking_type, "")

    lines = [f"{header} (#{booking_id})"]
    if trip_label:
        lines.append(trip_label)
    if type_label and type_label != trip_label:
        lines.append(type_label)
    lines.append("")

    if booking_type == "vehicle_pickup" and vehicle_info:
        lines.append(f"🚘 *Vehicle:* {vehicle_info}")
        lines.append(f"📍 *Pickup from:* {from_name}")
        lines.append(f"📍 *Deliver to:* {to_name}")
    else:
        lines.append(f"📍 *Pickup:* {from_name}")
        lines.append(f"📍 *Drop:* {to_name}")

    if stops and isinstance(stops, list):
        lines.append(f"🛑 *Stops:* {' → '.join(stops)}")

    if travel_date:
        lines.append(f"📅 *Date:* {travel_date}")
    if report_time:
        lines.append(f"🕐 *Driver reports at:* {report_time}")
    if travel_time and travel_time != report_time:
        lines.append(f"⏰ *Pickup time:* {travel_time}")
    if event_time:
        lines.append(f"✈️ *Event/flight time:* {event_time}")
    if end_time:
        lines.append(f"🏁 *Until:* {end_time}")

    lines.append(f"📏 *Distance:* ~{est_distance} km")
    lines.append(f"⏱️ *Est. Duration:* ~{est_duration} min")
    lines.append(f"💰 *Est. Fare:* ₹{est_fare}")

    if contact_name:
        lines.append(f"👤 *Contact person:* {contact_name}")
    if contact_phone:
        lines.append(f"📞 *Contact phone:* {contact_phone}")
    if special_notes:
        lines.append(f"📝 *Notes:* {special_notes}")
    if driving_notes:
        lines.append(f"🚦 *Driving notes:* {driving_notes}")

    lines.append("\nA driver will be assigned shortly and will contact you before the trip. 🙌")
    return "\n".join(lines)


def _format_multi_date_confirmation(booking_ids, from_name, to_name, driver,
                                     est_distance, est_duration, per_trip_fare,
                                     total_fare, travel_time, report_time, event_time,
                                     trip_type, booking_type, contact_name, contact_phone,
                                     vehicle_info, stops, special_notes, driving_notes):
    """Format confirmation for multi-date bookings."""
    trip_label = {"round_trip": "🔄 Round Trip", "full_day": "📆 Full Day", "one_way": "➡️ One Way"}.get(trip_type, "")
    lines = [f"📅 *{len(booking_ids)} Rides Scheduled!*"]
    if trip_label:
        lines.append(trip_label)
    lines.append("")
    lines.append(f"📍 *Route:* {from_name} → {to_name}")
    if report_time:
        lines.append(f"🕐 *Driver reports at:* {report_time}")
    if travel_time:
        lines.append(f"⏰ *Pickup:* {travel_time}")
    lines.append(f"📏 *Distance:* ~{est_distance} km per trip")
    lines.append(f"💰 *Fare:* ₹{per_trip_fare} × {len(booking_ids)} = *₹{total_fare}*")
    lines.append("")
    lines.append("📋 *Dates:*")
    for bid, d in booking_ids:
        lines.append(f"  • #{bid} — 📅 {d}")
    if contact_name:
        lines.append(f"\n👤 *Contact:* {contact_name}")
    if special_notes:
        lines.append(f"📝 *Notes:* {special_notes}")
    if driving_notes:
        lines.append(f"🚦 *Driving notes:* {driving_notes}")
    lines.append("\nDrivers will be assigned and will contact you before each ride. 🙌")
    return "\n".join(lines)

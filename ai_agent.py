"""
AI Booking Agent — powered by GPT-4o mini.

The agent interprets WhatsApp messages and calls database helpers
to manage bookings. It maintains a simple state machine per customer
stored in memory (use Redis for production).
"""

import os
import json
from openai import OpenAI
import database as db

# Lazy-initialize the OpenAI client (created on first use, not at import time)
_client = None

def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client

# ── Per-customer session state (in-memory; use Redis in production) ──
sessions: dict = {}   # phone -> { "state": ..., "data": {...} }

RATE_PER_MIN = float(os.getenv("RATE_PER_MIN", "8.0"))  # ₹ per minute

SYSTEM_PROMPT = """You are a friendly cab booking assistant for "Palakkad Cabs" 🚕.
You help customers book rides between major locations in Palakkad, Kerala.

RULES:
1. Greet new customers warmly and ask their name.
2. For returning customers, greet them by name.
3. Ask for PICKUP location and DROP location (from the known locations list).
4. Confirm the booking details (route, estimated time, estimated fare).
5. If customer confirms, create the booking.
6. Be conversational, friendly, and use a mix of English. Keep messages short for WhatsApp.
7. If the customer asks about fare: it's ₹{rate}/min based on trip duration.
8. If no driver is available, apologise and ask them to try again shortly.
9. If customer wants to check past rides, show their recent bookings.
10. If the message is unclear, ask for clarification politely.

KNOWN LOCATIONS IN PALAKKAD:
{locations}

You MUST respond with a JSON object (and nothing else) in this format:
{{
  "reply": "Your WhatsApp reply message to the customer",
  "action": null or one of ["set_name", "create_booking", "check_bookings", "cancel_booking"],
  "action_data": {{}}  // relevant data for the action
}}

For "set_name" action_data: {{ "name": "Customer Name" }}
For "create_booking" action_data: {{ "from": "Location Name", "to": "Location Name" }}
For "check_bookings" action_data: {{}}
For "cancel_booking" action_data: {{ "booking_id": 123 }}
""".replace("{rate}", str(RATE_PER_MIN))


def _build_location_list() -> str:
    locs = db.get_locations()
    return ", ".join(loc["name"] for loc in locs)


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

    # 3. Build messages for OpenAI
    locations_str = _build_location_list()
    system = SYSTEM_PROMPT.replace("{locations}", locations_str)

    messages = [{"role": "system", "content": system}]

    # Add customer context
    customer_context = f"[Customer phone: {phone}, Name: {customer['name']}]"
    recent_bookings = db.get_customer_bookings(customer_id, limit=3)
    if recent_bookings:
        booking_summary = "\n".join(
            f"  - #{b['id']}: {b['from_name']} → {b['to_name']} | {b['status']} | ₹{b['fare'] or 'TBD'}"
            for b in recent_bookings
        )
        customer_context += f"\n[Recent bookings:\n{booking_summary}]"
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
            max_tokens=500,
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
        reply = _handle_create_booking(customer_id, action_data, reply)

    elif action == "check_bookings":
        bookings = db.get_customer_bookings(customer_id, limit=5)
        if bookings:
            lines = []
            for b in bookings:
                fare_str = f"₹{b['fare']}" if b["fare"] else "pending"
                lines.append(
                    f"🚗 #{b['id']}: {b['from_name']} → {b['to_name']} | {b['status']} | {fare_str}"
                )
            reply += "\n\n" + "\n".join(lines)
        else:
            reply += "\n\nYou don't have any bookings yet!"

    # 6. Log outgoing message
    db.log_conversation(customer_id, "out", reply)

    return reply


def _handle_create_booking(customer_id: int, action_data: dict, base_reply: str) -> str:
    """Look up locations, find driver, create booking."""
    from_name = action_data.get("from", "")
    to_name = action_data.get("to", "")

    from_locs = db.find_location(from_name)
    to_locs = db.find_location(to_name)

    if not from_locs:
        return f"Sorry, I couldn't find a location matching '{from_name}'. Could you check the name? 🤔"
    if not to_locs:
        return f"Sorry, I couldn't find a location matching '{to_name}'. Could you check the name? 🤔"

    from_loc = from_locs[0]
    to_loc = to_locs[0]

    if from_loc["id"] == to_loc["id"]:
        return "Pickup and drop locations can't be the same! 😅 Please choose different locations."

    # Get route info
    route = db.get_route(from_loc["id"], to_loc["id"])
    if not route:
        # Try reverse (some routes may only be defined one way)
        route = db.get_route(to_loc["id"], from_loc["id"])

    distance_km = route["distance_km"] if route else 10.0
    est_duration = route["est_duration_min"] if route else 20
    est_fare = round(est_duration * RATE_PER_MIN, 2)

    # Find available driver
    driver = db.find_available_driver(from_loc["id"])
    if not driver:
        return (
            "😔 Sorry, no drivers are available right now near "
            f"{from_loc['name']}. Please try again in a few minutes!"
        )

    # Create the booking
    booking_id = db.create_booking(
        customer_id=customer_id,
        driver_id=driver["id"],
        from_loc_id=from_loc["id"],
        to_loc_id=to_loc["id"],
        distance_km=distance_km,
        est_duration_min=est_duration,
    )

    reply = (
        f"✅ *Booking Confirmed!* (#{booking_id})\n\n"
        f"📍 *Pickup:* {from_loc['name']}\n"
        f"📍 *Drop:* {to_loc['name']}\n"
        f"🚗 *Driver:* {driver['name']} ({driver['vehicle_number']})\n"
        f"📏 *Distance:* {distance_km} km\n"
        f"⏱️ *Est. Duration:* {est_duration} min\n"
        f"💰 *Est. Fare:* ₹{est_fare}\n\n"
        f"Your driver will contact you shortly! 🙌"
    )
    return reply

"""
Fish Hub AI Agent — "Mohanan Chettan" persona.
Uses the shared SQLite DB for customer identity; fish-specific tables for inventory/orders.
"""

import os
import json
import sys
from datetime import date, datetime, timedelta
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as cabdb  # noqa: E402
from . import database as fdb


_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


DELIVERY_SLOTS = [
    {"code": "today_evening", "label": "Today Evening (5-7 PM)", "cutoff_hour": 13},
    {"code": "tomorrow_morning", "label": "Tomorrow Morning (7-9 AM)", "cutoff_hour": 23},
    {"code": "tomorrow_evening", "label": "Tomorrow Evening (5-7 PM)", "cutoff_hour": 23},
]


def available_slots_for_now():
    now = datetime.now()
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    out = []
    for s in DELIVERY_SLOTS:
        if s["code"] == "today_evening" and now.hour >= s["cutoff_hour"]:
            continue
        delivery_date = today if s["code"] == "today_evening" else tomorrow
        out.append({"code": s["code"], "label": s["label"], "delivery_date": delivery_date})
    return out


SYSTEM_PROMPT = """You are "Mohanan Chettan" (മോഹനൻ ചേട്ടൻ), the friendly, trusted fish agent for a Kerala coastal fish hub in Kochi.

YOUR PERSONA:
- Warm, respectful, family-style Malayali elder brother ("chettan" = elder brother in Malayalam).
- You source the freshest catch daily from the harbour at dawn and deliver to a closed circle of loyal customers.
- You know every fish — its taste, best cooking method, what's in season.
- Speak simple, clear English. Sprinkle Malayalam fish names naturally (neymeen, ayala, mathi, karimeen, chemmeen, konju).
- Describe fish specialities briefly and genuinely — not a sales pitch.
- Be honest: if a fish is limited or running out, say so. If not fresh today, recommend an alternative.

YOUR SERVICE:
- Daily morning stock is uploaded by the agency.
- Customers browse today's catch, ask about specialities, place orders.
- Confirm orders with price, quantity, delivery slot.
- Show past orders, cancel upcoming ones.

RULES:
- ONLY talk about fish, orders, delivery, cooking. If asked anything unrelated, politely redirect: "I only help with your fish orders, chetta. What can I get you today?"
- Do NOT invent fish. Only offer what's actually in today's inventory.
- Do NOT invent prices. Use exactly what's in inventory.
- If customer asks for more than available, tell them honestly and suggest alternatives.
- NEVER reveal you are an AI, a bot, or powered by OpenAI/GPT. You are Mohanan Chettan.
- If asked "are you a bot / AI / real person?", say: "I'm Mohanan chettan — running this fish hub."
- Always confirm before placing an order (quantity, fish, total, delivery slot).

DELIVERY SLOTS (ONLY valid options):
- today_evening    -> Today Evening 5-7 PM (only before 1 PM)
- tomorrow_morning -> Tomorrow Morning 7-9 AM
- tomorrow_evening -> Tomorrow Evening 5-7 PM

RESPONSE FORMAT (you MUST return a JSON object):
{
  "reply": "Your WhatsApp message (warm, short, natural)",
  "action": "none" | "set_name" | "show_inventory" | "place_order" | "check_orders" | "cancel_order" | "save_preferences",
  "action_data": { ... depends on action ... }
}

ACTIONS:
- set_name: {"name": "customer name"}
- show_inventory: {} (list today's catch in the reply)
- place_order: {"fish_name": "...", "quantity_kg": 2.0, "delivery_slot": "today_evening"}
- check_orders: {}
- cancel_order: {"order_id": 12}
- save_preferences: {"preferences": "free text like 'prefers karimeen, allergic to crab'"}

Keep replies short (2-4 lines). WhatsApp style. Warm but efficient.
"""


def build_context(phone):
    customer = cabdb.get_or_create_customer(phone)
    today_iso = date.today().isoformat()
    inventory = fdb.get_today_inventory(today_iso)
    orders = fdb.get_customer_orders(phone, limit=5)
    favourites = fdb.get_customer_favourite_fish(phone)
    slots = available_slots_for_now()
    prefs = fdb.get_preferences(phone)

    lines = [
        f"TODAY'S DATE: {today_iso}",
        f"CURRENT TIME: {datetime.now().strftime('%H:%M')}",
        "",
        "CUSTOMER INFO:",
        f"- Phone: {phone}",
        f"- Name: {customer.get('name') or '(not set)'}",
    ]
    if prefs:
        lines.append(f"- Fish preferences: {prefs}")
    lines.append("")

    if favourites:
        fav_str = ", ".join(f"{f['fish_name']} ({f['order_count']}x)" for f in favourites)
        lines.append(f"CUSTOMER'S FAVOURITES: {fav_str}")
        lines.append("")

    if orders:
        lines.append("RECENT ORDERS:")
        for o in orders[:3]:
            lines.append(f"- #{o['id']}: {o['quantity_kg']}kg {o['fish_name']} | "
                         f"{o['delivery_date']} {o['delivery_slot']} | {o['status']}")
        lines.append("")

    lines.append(f"TODAY'S FRESH CATCH ({len(inventory)} items):")
    if not inventory:
        lines.append("- NO inventory uploaded today yet. Politely tell customer the agency is sorting today's catch.")
    else:
        for item in inventory:
            remaining = float(item["available_kg"]) - float(item.get("reserved_kg") or 0)
            mal = f" ({item['malayalam_name']})" if item.get("malayalam_name") else ""
            spec = f" - {item['speciality']}" if item.get("speciality") else ""
            lines.append(f"- {item['fish_name']}{mal}: {remaining:.1f}kg left @ ₹{item['price_per_kg']:.0f}/kg{spec}")
            if item.get("notes"):
                lines.append(f"    NOTE: {item['notes']}")
    lines.append("")
    lines.append("AVAILABLE DELIVERY SLOTS RIGHT NOW:")
    for s in slots:
        lines.append(f"- {s['code']} -> {s['label']} (delivery date {s['delivery_date']})")
    return "\n".join(lines)


_conversations = {}


def process_message(phone, message):
    context = build_context(phone)
    hist = _conversations.setdefault(phone, [])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"LIVE CONTEXT:\n{context}"},
    ]
    messages.extend(hist)
    messages.append({"role": "user", "content": message})

    try:
        resp = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.6,
        )
        parsed = json.loads(resp.choices[0].message.content)
    except Exception as e:
        return f"Sorry, something's off on my side. Please try again. ({type(e).__name__})"

    reply = parsed.get("reply", "").strip()
    action = parsed.get("action", "none")
    action_data = parsed.get("action_data") or {}

    extra = _execute_action(phone, action, action_data)
    if extra:
        reply = (reply + "\n\n" + extra).strip() if reply else extra

    hist.append({"role": "user", "content": message})
    hist.append({"role": "assistant", "content": reply})
    if len(hist) > 20:
        _conversations[phone] = hist[-20:]

    return reply or "Sorry, couldn't process that. Could you try again?"


def _execute_action(phone, action, data):
    if not action or action == "none":
        return ""

    if action == "set_name":
        name = (data.get("name") or "").strip()
        if name:
            cabdb.update_customer_name(phone, name)
        return ""

    if action == "show_inventory":
        return ""

    if action == "save_preferences":
        prefs = (data.get("preferences") or "").strip()
        if prefs:
            fdb.save_preferences(phone, prefs)
        return ""

    if action == "check_orders":
        return ""

    if action == "cancel_order":
        oid = data.get("order_id")
        if oid is None:
            return ""
        ok = fdb.cancel_order(int(oid), phone)
        return f"(Order #{oid} cancelled.)" if ok else f"(Couldn't cancel order #{oid}.)"

    if action == "place_order":
        return _place(phone, data)

    return ""


def _place(phone, data):
    fish_name = (data.get("fish_name") or "").strip()
    qty = data.get("quantity_kg")
    slot_code = (data.get("delivery_slot") or "").strip()
    if not fish_name or not qty or not slot_code:
        return "(Order incomplete — missing fish, quantity, or slot.)"

    try:
        qty = float(qty)
    except (TypeError, ValueError):
        return "(Invalid quantity.)"

    slot = next((s for s in DELIVERY_SLOTS if s["code"] == slot_code), None)
    if not slot:
        return f"(Unknown delivery slot '{slot_code}'.)"

    today_iso = date.today().isoformat()
    tomorrow_iso = (date.today() + timedelta(days=1)).isoformat()
    delivery_date = today_iso if slot_code == "today_evening" else tomorrow_iso

    inv = fdb.get_today_inventory(today_iso)
    item = next((i for i in inv if i["fish_name"].lower() == fish_name.lower()), None)
    if not item:
        return f"(Sorry — {fish_name} not in today's catch.)"

    price = float(item["price_per_kg"])
    if not fdb.reserve_inventory(today_iso, item["fish_name"], qty):
        remaining = fdb.get_available_kg(today_iso, item["fish_name"])
        return f"(Sorry — only {remaining:.1f}kg of {item['fish_name']} left.)"

    cust = cabdb.get_or_create_customer(phone)
    order_id = fdb.create_order(
        customer_phone=phone,
        customer_name=cust.get("name") or "",
        fish_name=item["fish_name"],
        quantity_kg=qty,
        price_per_kg=price,
        delivery_date=delivery_date,
        delivery_slot=slot["label"],
    )
    total = qty * price
    return (f"Order #{order_id} confirmed: {qty}kg {item['fish_name']} = ₹{total:.0f}. "
            f"Delivery: {slot['label']} on {delivery_date}.")

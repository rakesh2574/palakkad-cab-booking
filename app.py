"""
Flask app — Twilio WhatsApp webhook for Kerala Cabs.

V2: Kerala-wide coverage, scheduled rides, driving preferences, smart rebooking.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Load .env before any imports that need env vars

from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client as TwilioClient

import database as db
import ai_agent

app = Flask(__name__)

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None


@app.route("/")
def home():
    return "🚕 Kerala Cabs WhatsApp Bot is running! (v2 — All Kerala)"


@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    """Twilio sends POST here when a WhatsApp message arrives."""
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")
    profile_name = request.form.get("ProfileName", "")

    phone = from_number.replace("whatsapp:", "").strip()

    print(f"📩 Message from {phone} ({profile_name}): {incoming_msg}")

    # ── PIN-based access control ──
    # Ensure customer record exists
    db.get_or_create_customer(phone, profile_name or None)

    if not db.is_customer_activated(phone):
        # Check if the message IS a PIN attempt
        result = db.try_activate_with_pin(phone, incoming_msg)

        if result == "activated":
            reply_text = (
                "✅ *Access Activated!* Welcome to Kerala Cabs! 🚕\n\n"
                "I'm Niveditha, your friendly cab booking assistant. "
                "I can help you book rides anywhere in Kerala!\n\n"
                "What's your name? 😊"
            )
        elif result == "already_active":
            reply_text = ai_agent.process_message(phone, incoming_msg)
        elif result == "pin_exhausted":
            reply_text = (
                "⚠️ This access code has already been used to its limit. "
                "Please contact the admin for a new code."
            )
        else:
            reply_text = (
                "🔒 *Kerala Cabs — Access Required*\n\n"
                "Welcome! This is an invite-only service.\n"
                "Please send your *access code* to get started.\n\n"
                "Don't have a code? Contact the admin to get one."
            )

        print(f"📤 Reply to {phone}: {reply_text}")
        resp = MessagingResponse()
        resp.message(reply_text)
        return str(resp), 200, {"Content-Type": "text/xml"}

    # ── Customer is activated — process normally ──
    reply_text = ai_agent.process_message(phone, incoming_msg)

    print(f"📤 Reply to {phone}: {reply_text}")

    resp = MessagingResponse()
    resp.message(reply_text)

    return str(resp), 200, {"Content-Type": "text/xml"}


@app.route("/send", methods=["POST"])
def send_proactive_message():
    """API endpoint to send a proactive WhatsApp message."""
    if not twilio_client:
        return {"error": "Twilio not configured"}, 500

    data = request.get_json()
    phone = data.get("phone", "")
    message = data.get("message", "")

    if not phone or not message:
        return {"error": "phone and message required"}, 400

    try:
        msg = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{phone}",
            body=message,
        )
        return {"sid": msg.sid, "status": "sent"}, 200
    except Exception as e:
        return {"error": str(e)}, 500


@app.route("/bookings/<int:booking_id>/complete", methods=["POST"])
def complete_booking_endpoint(booking_id):
    """Mark a booking as complete."""
    data = request.get_json()
    actual_duration = data.get("actual_duration_min")
    if not actual_duration:
        return {"error": "actual_duration_min required"}, 400

    fare = db.complete_booking(booking_id, actual_duration)
    return {"booking_id": booking_id, "fare": fare, "status": "completed"}, 200


# ── Admin API (protected by a simple key) ──
ADMIN_KEY = os.getenv("ADMIN_KEY", "palakkad2026")


def check_admin():
    key = request.args.get("key", "")
    return key == ADMIN_KEY


@app.route("/admin/dashboard")
def admin_dashboard():
    if not check_admin():
        return {"error": "Add ?key=YOUR_ADMIN_KEY to the URL"}, 401

    conn = db.get_connection()
    stats = {
        "customers": conn.execute("SELECT COUNT(*) as c FROM customers").fetchone()["c"],
        "drivers_total": conn.execute("SELECT COUNT(*) as c FROM drivers").fetchone()["c"],
        "drivers_available": conn.execute("SELECT COUNT(*) as c FROM drivers WHERE is_available = 1").fetchone()["c"],
        "bookings_total": conn.execute("SELECT COUNT(*) as c FROM bookings").fetchone()["c"],
        "bookings_completed": conn.execute("SELECT COUNT(*) as c FROM bookings WHERE status = 'completed'").fetchone()["c"],
        "bookings_confirmed": conn.execute("SELECT COUNT(*) as c FROM bookings WHERE status = 'confirmed'").fetchone()["c"],
        "bookings_scheduled": conn.execute("SELECT COUNT(*) as c FROM bookings WHERE status = 'scheduled'").fetchone()["c"],
        "total_revenue": conn.execute("SELECT COALESCE(SUM(fare), 0) as total FROM bookings WHERE status = 'completed'").fetchone()["total"],
        "messages_total": conn.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"],
        "customers_activated": conn.execute("SELECT COUNT(*) as c FROM customers WHERE is_activated = 1").fetchone()["c"],
        "pins_active": conn.execute("SELECT COUNT(*) as c FROM access_pins WHERE is_active = 1").fetchone()["c"],
    }
    conn.close()
    return jsonify(stats)


@app.route("/admin/customers")
def admin_customers():
    if not check_admin():
        return {"error": "Unauthorized"}, 401
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT id, phone, name, preferred_speed, driving_notes, is_activated, activated_at, created_at FROM customers ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/admin/bookings")
def admin_bookings():
    if not check_admin():
        return {"error": "Unauthorized"}, 401
    conn = db.get_connection()
    rows = conn.execute("""
        SELECT b.id, c.name as customer, c.phone,
               b.pickup_location as pickup, b.drop_location as dropoff,
               d.name as driver, b.status, b.distance_km, b.est_duration_min,
               b.actual_duration_min, b.fare,
               b.travel_date, b.travel_time, b.driving_notes,
               b.booked_at, b.completed_at
        FROM bookings b
        JOIN customers c ON b.customer_id = c.id
        LEFT JOIN drivers d ON b.driver_id = d.id
        ORDER BY b.id DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/admin/drivers")
def admin_drivers():
    if not check_admin():
        return {"error": "Unauthorized"}, 401
    conn = db.get_connection()
    rows = conn.execute("""
        SELECT id, name, phone, vehicle_number, vehicle_type,
               is_available, base_area
        FROM drivers ORDER BY id
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/admin/conversations")
def admin_conversations():
    if not check_admin():
        return {"error": "Unauthorized"}, 401
    phone = request.args.get("phone")
    conn = db.get_connection()
    if phone:
        rows = conn.execute("""
            SELECT cv.id, c.name, c.phone, cv.direction, cv.message, cv.created_at
            FROM conversations cv
            JOIN customers c ON cv.customer_id = c.id
            WHERE c.phone = ?
            ORDER BY cv.id DESC LIMIT 50
        """, (phone,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT cv.id, c.name, c.phone, cv.direction, cv.message, cv.created_at
            FROM conversations cv
            JOIN customers c ON cv.customer_id = c.id
            ORDER BY cv.id DESC LIMIT 100
        """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/admin/pins")
def admin_pins():
    """View all access PINs and their usage."""
    if not check_admin():
        return {"error": "Unauthorized"}, 401
    pins = db.list_access_pins()
    return jsonify(pins)


@app.route("/admin/pins/create", methods=["GET", "POST"])
def admin_create_pin():
    """
    Create a new access PIN.
    POST JSON: { "pin": "KERALA2026", "label": "Client ABC", "max_uses": 5 }
    Or via URL: /admin/pins/create?key=ADMIN_KEY&pin=KERALA2026&label=Client+ABC&max_uses=5
    """
    if not check_admin():
        return {"error": "Unauthorized"}, 401

    # Support both JSON body and URL params
    if request.is_json:
        data = request.get_json()
    else:
        data = {
            "pin": request.args.get("pin", ""),
            "label": request.args.get("label", ""),
            "max_uses": request.args.get("max_uses", "1"),
        }

    pin = data.get("pin", "").strip()
    label = data.get("label", "").strip() or None
    max_uses = int(data.get("max_uses", 1))

    if not pin:
        return {"error": "pin is required"}, 400

    success = db.create_access_pin(pin, label, max_uses)
    if success:
        return {"status": "created", "pin": pin.upper(), "label": label, "max_uses": max_uses}, 201
    else:
        return {"error": "PIN already exists"}, 409


@app.route("/admin/pins/<int:pin_id>/deactivate", methods=["GET", "POST"])
def admin_deactivate_pin(pin_id):
    """Deactivate a PIN so it can't be used anymore."""
    if not check_admin():
        return {"error": "Unauthorized"}, 401
    db.deactivate_pin(pin_id)
    return {"status": "deactivated", "pin_id": pin_id}


@app.route("/admin/activate", methods=["GET", "POST"])
def admin_activate_customer():
    """
    Manually activate a customer (bypass PIN).
    POST JSON: { "phone": "+919048736080" }
    Or via URL: /admin/activate?key=ADMIN_KEY&phone=+919048736080
    """
    if not check_admin():
        return {"error": "Unauthorized"}, 401

    if request.is_json:
        phone = request.get_json().get("phone", "")
    else:
        phone = request.args.get("phone", "")

    if not phone:
        return {"error": "phone is required"}, 400

    # Ensure customer exists
    db.get_or_create_customer(phone)
    conn = db.get_connection()
    conn.execute(
        "UPDATE customers SET is_activated = 1, activated_at = datetime('now') WHERE phone = ?",
        (phone,),
    )
    conn.commit()
    conn.close()
    return {"status": "activated", "phone": phone}


# ── Initialise DB and seed if empty ──
db.init_db()

conn = db.get_connection()
count = conn.execute("SELECT COUNT(*) as c FROM drivers").fetchone()["c"]
conn.close()
if count == 0:
    import seed_data
    seed_data.seed()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)

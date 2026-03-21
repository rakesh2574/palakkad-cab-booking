"""
Flask app — Twilio WhatsApp webhook for Palakkad Cabs.

Twilio sends incoming WhatsApp messages here as POST requests.
We process them through the AI agent and reply via Twilio.
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

# Twilio credentials (for sending proactive messages later if needed)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None


@app.route("/")
def home():
    return "🚕 Palakkad Cabs WhatsApp Bot is running!"


@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    """
    Twilio sends POST to this endpoint when a WhatsApp message arrives.

    Key form fields from Twilio:
      - From:  'whatsapp:+919876543210'
      - Body:  The message text
      - ProfileName: WhatsApp display name (optional)
    """
    incoming_msg = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")        # e.g. whatsapp:+919876543210
    profile_name = request.form.get("ProfileName", "")

    # Extract clean phone number
    phone = from_number.replace("whatsapp:", "").strip()

    print(f"📩 Message from {phone} ({profile_name}): {incoming_msg}")

    # Process through AI agent
    reply_text = ai_agent.process_message(phone, incoming_msg)

    print(f"📤 Reply to {phone}: {reply_text}")

    # Build Twilio TwiML response
    resp = MessagingResponse()
    resp.message(reply_text)

    return str(resp), 200, {"Content-Type": "text/xml"}


@app.route("/send", methods=["POST"])
def send_proactive_message():
    """
    API endpoint to send a proactive WhatsApp message (e.g., driver updates).
    POST JSON: { "phone": "+919876543210", "message": "Your driver is arriving!" }
    """
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
    """
    Mark a booking as complete. Driver or admin calls this.
    POST JSON: { "actual_duration_min": 25 }
    """
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
    """Quick overview of everything — open in browser."""
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
        "total_revenue": conn.execute("SELECT COALESCE(SUM(fare), 0) as total FROM bookings WHERE status = 'completed'").fetchone()["total"],
        "messages_total": conn.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"],
    }
    conn.close()
    return jsonify(stats)


@app.route("/admin/customers")
def admin_customers():
    if not check_admin():
        return {"error": "Unauthorized"}, 401
    conn = db.get_connection()
    rows = conn.execute("SELECT id, phone, name, created_at FROM customers ORDER BY id DESC").fetchall()
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
               b.actual_duration_min, b.fare, b.booked_at, b.completed_at
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
    """View recent conversations. Add ?phone=+919876543210 to filter by customer."""
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


# ── Initialise DB and seed if empty ──
db.init_db()

# Auto-seed drivers if table is empty (first deploy)
conn = db.get_connection()
count = conn.execute("SELECT COUNT(*) as c FROM drivers").fetchone()["c"]
conn.close()
if count == 0:
    import seed_data
    seed_data.seed()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)

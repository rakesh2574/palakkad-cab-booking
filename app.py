"""
Flask app — Twilio WhatsApp webhook for Palakkad Cabs.

Twilio sends incoming WhatsApp messages here as POST requests.
We process them through the AI agent and reply via Twilio.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Load .env before any imports that need env vars

from flask import Flask, request
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


# ── Initialise DB and seed if empty ──
db.init_db()

# Auto-seed if locations table is empty (first deploy)
conn = db.get_connection()
count = conn.execute("SELECT COUNT(*) as c FROM locations").fetchone()["c"]
conn.close()
if count == 0:
    import seed_data
    seed_data.seed()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)

# 🚕 Palakkad Cabs — WhatsApp AI Booking Agent

A WhatsApp-based cab booking system for Palakkad, Kerala. Customers chat with an AI agent (GPT-4o mini) on WhatsApp to book rides between major locations. Built with Flask, Twilio, and SQLite.

## Architecture

```
Customer (WhatsApp)
    ↓
Twilio WhatsApp API
    ↓
Flask Webhook (/webhook)
    ↓
AI Agent (GPT-4o mini)
    ↓
SQLite Database
```

## How It Works

1. Customer sends a WhatsApp message to your Twilio number
2. Twilio forwards it to your Flask server via webhook
3. The AI agent processes the message, understands intent, and takes action
4. Actions include: register name, book a cab, check past rides, cancel
5. Fare is calculated based on **trip duration** (₹8/min default)
6. All conversations are logged to the database

## Setup

### 1. Clone & Install

```bash
cd palakkad-cab-booking
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your actual keys
```

You need:
- **OpenAI API key** → https://platform.openai.com/api-keys
- **Twilio account** → https://www.twilio.com/console
  - Enable the WhatsApp Sandbox (for testing)
  - Note your Account SID and Auth Token

### 3. Seed the Database

```bash
python seed_data.py
```

This creates 20 locations across Palakkad, 80 routes, and 10 sample drivers.

### 4. Run the Server

```bash
python app.py
```

Server runs on `http://localhost:5000`.

### 5. Expose with ngrok (for development)

Twilio needs a public URL to send webhooks:

```bash
ngrok http 5000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`).

### 6. Configure Twilio Webhook

1. Go to [Twilio Console → Messaging → Try it Out → WhatsApp Sandbox](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
2. Set "When a message comes in" to: `https://your-ngrok-url.ngrok.io/webhook`
3. Method: POST
4. Save

### 7. Test It!

Send a WhatsApp message to your Twilio sandbox number. Try:

- "Hi" → Agent greets and asks your name
- "My name is Rakesh" → Agent saves your name
- "I need a cab from Palakkad Fort to Malampuzha Dam" → Books a ride!
- "Show my bookings" → Lists your recent trips

## Locations Covered

Palakkad Fort, Town Bus Stand, Olavakkode Railway Station, Junction Railway Station,
Kalmandapam, Chandranagar, Nurani, Kongad, Mannarkkad, Ottapalam, Shoranur Junction,
Chittur, Malampuzha Dam, Nemmara, Pattambi, Alathur, Kollengode, Kanjikode, Walayar, Pudussery

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check |
| `/webhook` | POST | Twilio WhatsApp webhook |
| `/send` | POST | Send proactive message |
| `/bookings/<id>/complete` | POST | Mark booking complete |

## Pricing Model

Default: **₹8 per minute** of actual trip duration. Configurable via `RATE_PER_MIN` in `.env`.

## Database Schema

- **customers** — phone, name (identified by WhatsApp number)
- **locations** — 20 major places in Palakkad with lat/lon
- **routes** — distance & estimated duration between location pairs
- **drivers** — name, phone, vehicle, availability, current location
- **bookings** — full trip lifecycle (pending → confirmed → in_progress → completed)
- **conversations** — complete WhatsApp message log per customer

## Production Notes

- Replace SQLite with PostgreSQL for concurrent access
- Use Redis for session state instead of in-memory dict
- Add Twilio request validation (signature checking)
- Deploy on Railway / Render / AWS with a proper domain
- Set up a Twilio Business WhatsApp number (not sandbox)

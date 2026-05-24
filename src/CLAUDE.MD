# CLAUDE.md — Arunachala GPT Master Reference
# WhatsApp AI Guide for Tiruvannamalai Devotees
# Read this ENTIRE file before writing a single line of code.

---

## 1. WHAT THIS PROJECT IS

Arunachala GPT is a WhatsApp bot that serves devotees visiting
Tiruvannamalai temple. It helps with crowd alerts, lodge booking,
Girivalam safety, temple knowledge, and more.

Devotees interact ONLY via WhatsApp. No app. No website.
Everything happens through WhatsApp messages.

---

## 2. TECH STACK

```
Language:    Python 3.11+
Framework:   FastAPI
Database:    Supabase (PostgreSQL)
AI:          Anthropic Claude API (claude-sonnet-4-5)
WhatsApp:    Twilio WhatsApp Business API
Hosting:     Render
Testing:     pytest + pytest-asyncio
HTTP Client: httpx (async)
DB Client:   supabase-py
```

Install all dependencies:
```bash
pip install fastapi uvicorn supabase anthropic httpx pytest pytest-asyncio python-dotenv pydantic
```

---

## 3. PROJECT STRUCTURE

```
arunachala-gpt/
├── CLAUDE.md                    ← You are reading this
├── .env                         ← Never commit this
├── .env.example                 ← Commit this (no values)
├── requirements.txt
├── main.py                      ← FastAPI app entry point
├── src/
│   ├── __init__.py
│   ├── config.py                ← All env vars loaded here
│   ├── database.py              ← Supabase client singleton
│   ├── whatsapp.py              ← 360dialog send message util
│   ├── claude_ai.py             ← Anthropic Claude API util
│   ├── language.py              ← Language detection + storage
│   ├── router.py                ← Main message router
│   └── features/
│       ├── __init__.py
│       ├── crowd_alert.py       ← Feature 1
│       ├── abhishekam.py        ← Feature 2A
│       ├── annadhanam.py        ← Feature 2B
│       ├── girivalam_guide.py   ← Feature 2C
│       ├── anti_middlemen.py    ← Feature 4
│       ├── sos.py               ← Feature 5
│       ├── lodge_booking.py     ← Feature 6
│       ├── ashram_calendar.py   ← Feature 7
│       ├── fair_price.py        ← Feature 8
│       ├── lingam_guide.py      ← Feature 9
│       ├── how_to_reach.py      ← Feature 11
│       ├── missing_person.py    ← Feature 12
│       ├── hill_climb.py        ← Feature 13
│       └── daily_devotional.py  ← Feature 14
├── features/                    ← MD files for each feature
│   ├── feature1_crowd_alert.md
│   └── ...
└── tests/
    ├── __init__.py
    ├── conftest.py              ← Shared test fixtures
    ├── test_feature1.py
    └── ...
```

---

## 4. ENVIRONMENT VARIABLES

Create `.env` file in root. Never commit it.

```bash
# .env

# Twilio WhatsApp API
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_WEBHOOK_SECRET=your_webhook_secret

# Anthropic Claude API
ANTHROPIC_API_KEY=your_anthropic_api_key
CLAUDE_MODEL=claude-sonnet-4-5

# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key

# App settings
ADMIN_PHONE=919XXXXXXXXX    # Your WhatsApp number
ENVIRONMENT=development      # development | production
```

Create `.env.example` with same keys but empty values.

---

## 5. CORE UTILITIES — READ BEFORE BUILDING ANY FEATURE

### 5.1 config.py
```python
# src/config.py
# src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_webhook_secret: str

    # Anthropic
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-5"

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # App
    admin_phone: str
    environment: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()
```

### 5.2 database.py
```python
# src/database.py
from supabase import create_client, Client
from src.config import settings

_client: Client | None = None

def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )
    return _client
```

### 5.3 whatsapp.py — HOW TO SEND MESSAGES
```python
# src/whatsapp.py
from twilio.rest import Client
from src.config import settings
import logging

logger = logging.getLogger(__name__)

def get_client() -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)

async def send_text(phone: str, message: str) -> dict:
    """Send plain text WhatsApp message via Twilio."""
    try:
        client = get_client()
        msg = client.messages.create(
            from_=settings.twilio_whatsapp_from,
            to=f"whatsapp:{phone}",
            body=message
        )
        return {"sid": msg.sid, "status": msg.status}
    except Exception as e:
        logger.error(f"Twilio send_text failed to {phone}: {e}")
        raise

async def send_buttons(phone: str, body: str, buttons: list[str]) -> dict:
    """
    Twilio does not support native WhatsApp buttons via API.
    Send as numbered text options instead.
    """
    numbered = "\n".join([f"{i+1}. {b}" for i, b in enumerate(buttons[:3])])
    full_message = f"{body}\n\n{numbered}"
    return await send_text(phone, full_message)

async def send_list(phone: str, body: str,
                    button_label: str, sections: list[dict]) -> dict:
    """
    Twilio does not support list messages.
    Send as numbered text options instead.
    """
    lines = [body, ""]
    for section in sections:
        if section.get("title"):
            lines.append(section["title"])
        for row in section.get("rows", []):
            lines.append(f"  • {row.get('title', '')}")
    return await send_text(phone, "\n".join(lines))

async def send_audio(phone: str, audio_url: str) -> dict:
    """Send audio file as WhatsApp media message via Twilio."""
    try:
        client = get_client()
        msg = client.messages.create(
            from_=settings.twilio_whatsapp_from,
            to=f"whatsapp:{phone}",
            media_url=[audio_url]
        )
        return {"sid": msg.sid, "status": msg.status}
    except Exception as e:
        logger.error(f"Twilio send_audio failed to {phone}: {e}")
        raise
```

### 5.4 claude_ai.py — HOW TO CALL CLAUDE
```python
# src/claude_ai.py
import anthropic
from src.config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

async def get_reply(
    system_prompt: str,
    user_message: str,
    conversation_history: list[dict] | None = None,
    max_tokens: int = 500
) -> str:
    """
    Call Claude API and get a reply.

    conversation_history format:
    [
        {"role": "user", "content": "previous message"},
        {"role": "assistant", "content": "previous reply"}
    ]
    """
    messages = conversation_history or []
    messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages
    )
    return response.content[0].text

# LANGUAGE SYSTEM PROMPT — use in every Claude call
LANGUAGE_RULE = """
CRITICAL LANGUAGE RULE:
Detect the language of the user's message and reply in EXACTLY that language.
- Tamil script or romanized Tamil (enna, eppo, koottam) → reply in Tamil
- Telugu script or romanized Telugu (ela undi, cheppandi) → reply in Telugu
- Kannada script or romanized Kannada (enu, bekku) → reply in Kannada
- Hindi → reply in Hindi
- English → reply in English
Keep responses warm, brief, and practical.
Devotees may be standing at a temple at 2am — keep it simple.
"""
```

### 5.5 language.py — LANGUAGE DETECTION AND STORAGE
```python
# src/language.py
from src.database import get_db

SUPPORTED_LANGUAGES = ["tamil", "telugu", "kannada", "hindi", "english"]

async def get_user_language(phone: str) -> str | None:
    """Get saved language preference for a user."""
    db = get_db()
    result = db.table("devotee_profile")\
        .select("language")\
        .eq("phone", phone)\
        .execute()
    if result.data:
        return result.data[0].get("language")
    return None

async def save_user_language(phone: str, language: str) -> None:
    """Save language preference for a user."""
    db = get_db()
    db.table("devotee_profile").upsert({
        "phone": phone,
        "language": language,
        "updated_at": "now()"
    }).execute()

def get_language_menu() -> str:
    """Return language selection message."""
    return (
        "Welcome to Arunachala GPT! 🙏\n\n"
        "Please select your language:\n"
        "1 — Tamil தமிழ்\n"
        "2 — Telugu తెలుగు\n"
        "3 — Kannada ಕನ್ನಡ\n"
        "4 — Hindi हिंदी\n"
        "5 — English\n\n"
        "Reply 1 / 2 / 3 / 4 / 5"
    )

LANGUAGE_MAP = {
    "1": "tamil", "2": "telugu",
    "3": "kannada", "4": "hindi", "5": "english"
}
```

---

## 6. HOW WHATSAPP WEBHOOK WORKS

360dialog sends a POST request to your webhook URL
whenever a user sends your bot a message.

```
User sends "Hi" on WhatsApp
        ↓
360dialog sends POST to: https://your-app.onrender.com/webhook
        ↓
Your FastAPI receives the request
        ↓
Extract: phone number + message text
        ↓
Route to correct feature handler
        ↓
Send reply via send_text() or send_buttons()
```

### main.py — Webhook Entry Point
```python
# main.py — Twilio webhook (no GET verification needed)
from fastapi import FastAPI, Request, Form
from twilio.request_validator import RequestValidator
from src.config import settings
from src.router import route_message

app = FastAPI(title="Arunachala GPT")

@app.post("/webhook")
async def receive_message(
    request: Request,
    From: str = Form(...),
    Body: str = Form(default=""),
    ButtonText: str = Form(default=""),
    ButtonPayload: str = Form(default="")
):
    """Receive WhatsApp messages from Twilio."""
    # Validate request is from Twilio
    validator = RequestValidator(settings.twilio_auth_token)
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    form_data = await request.form()
    params = dict(form_data)

    if settings.environment == "production":
        if not validator.validate(url, params, signature):
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    # Extract phone number (remove whatsapp: prefix)
    phone = From.replace("whatsapp:", "").replace("+", "")

    # Get message text — button text takes priority
    text = ButtonText or Body
    text = text.strip()

    if text:
        await route_message(phone=phone, text=text)

    # Twilio expects empty 200 response
    return ""

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Arunachala GPT"}

@app.post("/webhook")
async def receive_message(request: Request):
    """Receive WhatsApp messages from 360dialog."""
    body = await request.json()
    try:
        # Extract message from 360dialog payload
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "no_message"}

        message = messages[0]
        phone = message["from"]
        msg_type = message.get("type", "text")

        if msg_type == "text":
            text = message["text"]["body"].strip()
        elif msg_type == "interactive":
            # Button or list reply
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive["button_reply"]["title"]
            elif interactive.get("type") == "list_reply":
                text = interactive["list_reply"]["title"]
            else:
                text = ""
        else:
            text = ""

        if text:
            await route_message(phone=phone, text=text)

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Arunachala GPT"}
```

---

## 7. MESSAGE ROUTER — HOW FEATURES ARE TRIGGERED

```python
# src/router.py
from src.language import get_user_language, save_user_language, get_language_menu, LANGUAGE_MAP
from src.whatsapp import send_text
from src.database import get_db

async def route_message(phone: str, text: str) -> None:
    """
    Route incoming message to correct feature.
    Priority order:
    1. Admin commands (ADMIN prefix)
    2. Language selection (if no language saved yet)
    3. SOS/MISSING/FOUND (safety — highest priority)
    4. Feature-specific keywords
    5. General AI conversation
    """
    text_upper = text.upper().strip()

    # 1. ADMIN commands
    if text_upper.startswith("ADMIN") and phone == ADMIN_PHONE:
        from src.features.admin import handle_admin
        await handle_admin(phone, text)
        return

    # 2. Language selection
    language = await get_user_language(phone)
    if not language:
        if text in LANGUAGE_MAP:
            lang = LANGUAGE_MAP[text]
            await save_user_language(phone, lang)
            await send_text(phone, f"Language saved: {lang.title()} 🙏\n\nHow can I help you?")
        else:
            await send_text(phone, get_language_menu())
        return

    # 3. SAFETY — always highest priority
    if text_upper == "SOS":
        from src.features.sos import handle_sos
        await handle_sos(phone)
        return

    if text_upper.startswith("MISSING"):
        from src.features.missing_person import handle_missing
        await handle_missing(phone, text)
        return

    if text_upper.startswith("FOUND"):
        from src.features.missing_person import handle_found
        await handle_found(phone, text)
        return

    # 4. Feature keywords — check intent
    intent = detect_intent(text_upper)
    await dispatch_intent(phone, intent, text, language)


def detect_intent(text: str) -> str:
    """Detect user intent from message text."""
    crowd_words = ["CROWD", "KOOTTAM", "QUEUE", "WAIT", "TICKET", "DARSHAN"]
    sos_words = ["SOS", "HELP", "EMERGENCY", "MEDICAL"]
    lodge_words = ["LODGE", "ROOM", "STAY", "HOTEL", "BED"]
    lingam_words = ["LINGAM", "ASHTA", "INDRA", "AGNI", "YAMA", "NIRUTHI",
                    "VARUNA", "VAYU", "KUBERA", "ISANYA"]
    girivalam_words = ["GIRIVALAM", "CIRCUMAMBULATION", "PRADAKSHINA", "WALK"]
    hill_words = ["HILL", "CLIMB", "SKANDASHRAM", "VIRUPAKSHA", "CAVE"]
    reach_words = ["REACH", "COME", "TRAVEL", "BUS", "TRAIN", "CHENNAI",
                   "BANGALORE", "HYDERABAD"]
    price_words = ["PRICE", "RATE", "AUTO", "RUDRAKSHA", "FAIR", "COST"]
    calendar_words = ["ASHRAM", "SATSANG", "PROGRAM", "SCHEDULE", "TEACHER"]
    annadhanam_words = ["ANNADHANAM", "FOOD", "SPONSOR", "FEED"]
    abhishekam_words = ["ABHISHEKAM", "BOOKING", "BOOK"]
    missing_words = ["MISSING", "LOST", "REGISTER", "FAMILY"]

    for word in crowd_words:
        if word in text: return "crowd"
    for word in lingam_words:
        if word in text: return "lingam"
    for word in lodge_words:
        if word in text: return "lodge"
    for word in hill_words:
        if word in text: return "hill"
    for word in reach_words:
        if word in text: return "reach"
    for word in girivalam_words:
        if word in text: return "girivalam_guide"
    for word in price_words:
        if word in text: return "price"
    for word in calendar_words:
        if word in text: return "calendar"
    for word in annadhanam_words:
        if word in text: return "annadhanam"
    for word in abhishekam_words:
        if word in text: return "abhishekam"
    for word in missing_words:
        if word in text: return "missing"

    return "general"


async def dispatch_intent(phone: str, intent: str, text: str, language: str) -> None:
    """Dispatch to correct feature handler based on intent."""
    handlers = {
        "crowd":           "src.features.crowd_alert.handle",
        "lingam":          "src.features.lingam_guide.handle",
        "lodge":           "src.features.lodge_booking.handle",
        "hill":            "src.features.hill_climb.handle",
        "reach":           "src.features.how_to_reach.handle",
        "girivalam_guide": "src.features.girivalam_guide.handle",
        "price":           "src.features.fair_price.handle",
        "calendar":        "src.features.ashram_calendar.handle",
        "annadhanam":      "src.features.annadhanam.handle",
        "abhishekam":      "src.features.abhishekam.handle",
        "missing":         "src.features.missing_person.handle",
    }

    if intent in handlers:
        module_path, func_name = handlers[intent].rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        handler = getattr(module, func_name)
        await handler(phone=phone, text=text, language=language)
    else:
        # General AI conversation
        from src.features.general import handle_general
        await handle_general(phone=phone, text=text, language=language)
```

---

## 8. COMPLETE DATABASE SCHEMA

Run this SQL in Supabase SQL editor to create all tables.

```sql
-- ─── CORE TABLES ─────────────────────────────────────────────

CREATE TABLE devotee_profile (
    phone           VARCHAR(15) PRIMARY KEY,
    name            TEXT,
    language        VARCHAR(10),
    has_elderly     BOOLEAN DEFAULT FALSE,
    has_children    BOOLEAN DEFAULT FALSE,
    home_city       TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE conversation_state (
    phone           VARCHAR(15) PRIMARY KEY,
    current_feature TEXT,
    step            TEXT,
    data            JSONB DEFAULT '{}',
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ─── FEATURE 1: CROWD ALERT ──────────────────────────────────

CREATE TABLE crowd_status (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reported_at     TIMESTAMP DEFAULT NOW(),
    reported_by     TEXT,
    free_wait_min   INTEGER,
    rs50_wait_min   INTEGER,
    rs200_wait_min  INTEGER,
    notes           TEXT
);

CREATE TABLE temple_config (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      TIMESTAMP DEFAULT NOW()
);

INSERT INTO temple_config VALUES
('ticket_sale_start_time', '08:00', NOW()),
('rs50_ticket_price',      '50',    NOW()),
('rs200_ticket_price',     '200',   NOW()),
('rs50_sold_out',          'false', NOW()),
('rs200_sold_out',         'false', NOW()),
('temple_open_time',       '05:30', NOW()),
('temple_close_time',      '21:00', NOW()),
('volunteer_phone',        '',      NOW());

CREATE TABLE crowd_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    visit_date      DATE,
    hour_of_day     INTEGER,
    is_pournami     BOOLEAN,
    is_festival     BOOLEAN,
    festival_name   TEXT,
    free_wait_min   INTEGER,
    rs50_wait_min   INTEGER,
    rs200_wait_min  INTEGER
);

-- ─── FEATURE 2A: ABHISHEKAM ──────────────────────────────────

CREATE TABLE abhishekam_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone           VARCHAR(15),
    name            TEXT,
    registered_at   TIMESTAMP DEFAULT NOW(),
    notified_count  INTEGER DEFAULT 0,
    active          BOOLEAN DEFAULT TRUE
);

-- ─── FEATURE 2B: ANNADHANAM ──────────────────────────────────

CREATE TABLE annadhanam_bookings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_ref     TEXT UNIQUE,
    sponsor_phone   VARCHAR(15),
    sponsor_name    TEXT,
    occasion        TEXT,
    feeding_date    DATE,
    people_count    INTEGER,
    total_amount    INTEGER,
    platform_fee    INTEGER,
    status          TEXT DEFAULT 'pending',
    proof_sent      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ─── FEATURE 2C: GIRIVALAM GUIDE ────────────────────────────

CREATE TABLE guide_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT,
    phone           VARCHAR(15) UNIQUE,
    languages       TEXT[],
    experience_yrs  INTEGER,
    rating          DECIMAL DEFAULT 0,
    active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE guide_bookings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_ref     TEXT UNIQUE,
    devotee_phone   VARCHAR(15),
    guide_id        UUID REFERENCES guide_profiles(id),
    tour_type       TEXT,
    tour_date       DATE,
    group_size      INTEGER,
    has_elderly     BOOLEAN DEFAULT FALSE,
    total_amount    INTEGER,
    booking_fee     INTEGER DEFAULT 49,
    status          TEXT DEFAULT 'pending',
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ─── FEATURE 5: GIRIVALAM SOS ───────────────────────────────

CREATE TABLE sos_registrations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    walker_phone    VARCHAR(15) UNIQUE,
    walker_name     TEXT,
    family_phones   TEXT[],
    registered_at   TIMESTAMP DEFAULT NOW(),
    active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE sos_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    walker_phone    VARCHAR(15),
    triggered_at    TIMESTAMP DEFAULT NOW(),
    family_count    INTEGER,
    family_notified BOOLEAN DEFAULT FALSE,
    resolved        BOOLEAN DEFAULT FALSE
);

-- ─── FEATURE 6: LODGE BOOKING ───────────────────────────────

CREATE TABLE lodges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT,
    address         TEXT,
    phone           VARCHAR(15),
    walk_minutes    INTEGER,
    room_types      TEXT[],
    price_normal    INTEGER,
    price_pournami  INTEGER,
    facilities      TEXT[],
    payment_types   TEXT[],
    rating          DECIMAL DEFAULT 0,
    verified        BOOLEAN DEFAULT FALSE,
    listing_fee     INTEGER DEFAULT 700,
    photo_urls      TEXT[],
    active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE lodge_bookings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_ref     TEXT UNIQUE,
    devotee_phone   VARCHAR(15),
    devotee_name    TEXT,
    lodge_id        UUID REFERENCES lodges(id),
    checkin_date    DATE,
    checkin_time    TEXT,
    room_type       TEXT,
    room_rent       INTEGER,
    booking_fee     INTEGER DEFAULT 49,
    payment_method  TEXT,
    payment_verified BOOLEAN DEFAULT FALSE,
    lodge_confirmed BOOLEAN DEFAULT FALSE,
    status          TEXT DEFAULT 'pending',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE lodge_availability (
    lodge_id        UUID REFERENCES lodges(id),
    date            DATE,
    rooms_available INTEGER,
    last_updated    TIMESTAMP DEFAULT NOW(),
    is_full         BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (lodge_id, date)
);

-- ─── FEATURE 7: ASHRAM CALENDAR ─────────────────────────────

CREATE TABLE ashram_programs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ashram_name     TEXT,
    day_type        TEXT,
    time_of_day     TIME,
    program_name    TEXT,
    location        TEXT,
    open_to_all     BOOLEAN DEFAULT TRUE,
    active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE special_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_date      DATE,
    event_time      TIME,
    ashram_name     TEXT,
    event_name      TEXT,
    teacher_name    TEXT,
    description     TEXT,
    venue           TEXT,
    language        TEXT,
    entry           TEXT,
    active          BOOLEAN DEFAULT TRUE
);

CREATE TABLE calendar_subscribers (
    phone           VARCHAR(15) PRIMARY KEY,
    name            TEXT,
    location        TEXT,
    language        TEXT,
    trial_started   DATE,
    next_payment    DATE,
    active          BOOLEAN DEFAULT TRUE,
    is_trial        BOOLEAN DEFAULT TRUE
);

-- ─── FEATURE 9: LINGAM GUIDE ────────────────────────────────

CREATE TABLE lingam_guide (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lingam_number   INTEGER UNIQUE,
    name_english    TEXT,
    name_tamil      TEXT,
    name_telugu     TEXT,
    name_kannada    TEXT,
    name_hindi      TEXT,
    km_from_start   DECIMAL,
    direction       TEXT,
    installed_by    TEXT,
    navagraha       TEXT,
    significance_en TEXT,
    what_to_do_en   TEXT,
    offering_en     TEXT,
    chant           TEXT,
    best_time       TEXT,
    audio_url_ta    TEXT,
    audio_url_te    TEXT,
    audio_url_kn    TEXT,
    audio_url_hi    TEXT,
    audio_url_en    TEXT,
    next_km         DECIMAL
);

-- ─── FEATURE 12: MISSING PERSON ─────────────────────────────

CREATE TABLE family_groups (
    group_id        TEXT PRIMARY KEY,
    festival_date   DATE,
    registered_by   VARCHAR(15),
    meeting_point   TEXT,
    member_count    INTEGER,
    payment_done    BOOLEAN DEFAULT FALSE,
    active          BOOLEAN DEFAULT TRUE,
    registered_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE family_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id        TEXT REFERENCES family_groups(group_id),
    name            TEXT,
    phone           VARCHAR(15),
    age             INTEGER,
    is_child        BOOLEAN DEFAULT FALSE,
    is_elderly      BOOLEAN DEFAULT FALSE,
    is_emergency    BOOLEAN DEFAULT FALSE
);

CREATE TABLE missing_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id        TEXT,
    reported_by     VARCHAR(15),
    missing_person  TEXT,
    person_type     TEXT,
    triggered_at    TIMESTAMP DEFAULT NOW(),
    family_notified BOOLEAN DEFAULT FALSE,
    found           BOOLEAN DEFAULT FALSE,
    found_at        TIMESTAMP
);

CREATE TABLE meeting_points (
    code            TEXT PRIMARY KEY,
    name            TEXT,
    description     TEXT,
    area            TEXT,
    active          BOOLEAN DEFAULT TRUE
);

-- ─── FEATURE 13: HILL CLIMB ─────────────────────────────────

CREATE TABLE hill_spots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    spot_name       TEXT,
    distance_km     DECIMAL,
    time_up_min     INTEGER,
    difficulty      TEXT,
    ramana_history  TEXT,
    significance    TEXT,
    what_to_do      TEXT,
    open_time       TEXT,
    elderly_ok      BOOLEAN DEFAULT FALSE,
    notes           TEXT
);

-- ─── FEATURE 14: DAILY DEVOTIONAL ───────────────────────────

CREATE TABLE devotional_subscribers (
    phone           VARCHAR(15) PRIMARY KEY,
    name            TEXT,
    language        TEXT,
    location        TEXT,
    subscribed_at   TIMESTAMP DEFAULT NOW(),
    next_payment    DATE,
    active          BOOLEAN DEFAULT TRUE
);
```

---

## 9. CODING STANDARDS — ALL TEAM MEMBERS MUST FOLLOW

### Structure of every feature handler:
```python
# src/features/your_feature.py

"""
Feature X: [Feature Name]
Owner: [Team member name]
Status: [in-progress | complete | testing]
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons
from src.claude_ai import get_reply, LANGUAGE_RULE
import logging

logger = logging.getLogger(__name__)


async def handle(phone: str, text: str, language: str) -> None:
    """
    Main entry point for this feature.
    Called by router.py when intent matches.

    Args:
        phone: User's WhatsApp number with country code (e.g. 919XXXXXXXXX)
        text: The message user sent (already stripped)
        language: User's saved language preference
    """
    try:
        # Your feature logic here
        pass
    except Exception as e:
        logger.error(f"Feature X error for {phone}: {e}")
        await send_text(phone, "Something went wrong. Please try again.")
```

### Rules:
```
1. Every function must have a docstring
2. Every function must have type hints
3. Use logger — never use print() in production code
4. All database calls wrapped in try/except
5. Never hardcode phone numbers — use config.py
6. Feature files must not import from other feature files
   (only from src/database, src/whatsapp, src/claude_ai)
7. All monetary values stored as integers (paise or rupees — be consistent)
8. Use Rs. prefix for all amounts in messages
```

---

## 10. HOW TO RUN LOCALLY

```bash
# Clone and setup
git clone <repo-url>
cd arunachala-gpt
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copy env file and fill values
cp .env.example .env
# Edit .env with your actual keys

# Run the server
uvicorn main:app --reload --port 8000

# Test webhook locally using ngrok
ngrok http 8000
# Copy the https URL and set in 360dialog dashboard

# Run tests
pytest tests/ -v

# Run specific feature tests
pytest tests/test_feature1.py -v
```

---

## 11. DEPLOYMENT ON RENDER

```
1. Push code to GitHub
2. Create new Web Service on Render
3. Connect GitHub repo
4. Build command: pip install -r requirements.txt
5. Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
6. Add all environment variables from .env
7. Set 360dialog webhook URL to: https://your-app.onrender.com/webhook
```

---

## 12. FEATURE BUILD ORDER (Priority)

```
Sprint 1 — Core (Week 1-2):
  Feature 1:  Crowd Alert          ← Start here
  Feature 4:  Anti-Middlemen       ← Same day as Feature 1
  Feature 8:  Fair Price Guide     ← Same day
  Feature 11: How to Reach         ← Same day

Sprint 2 — Safety (Week 3):
  Feature 5:  Girivalam SOS
  Feature 9:  Lingam Guide

Sprint 3 — Booking (Week 4-5):
  Feature 2B: Annadhanam
  Feature 2C: Girivalam Guide
  Feature 6:  Lodge Booking

Sprint 4 — Subscriptions (Week 6-7):
  Feature 7:  Ashram Calendar
  Feature 2A: Abhishekam Guidance
  Feature 13: Hill Climb Guide

Sprint 5 — Karthigai (Before festival):
  Feature 12: Missing Person Alert
  Feature 14: Daily Devotional
```

---

## 13. ADMIN COMMANDS (your phone only)

```
ADMIN config rs50_sold_out true      → Update temple config
ADMIN config rs200_sold_out false    → Update temple config
ADMIN crowd F:180 T50:45 T200:15     → Manual crowd update
ADMIN broadcast Tamil <message>      → Send to all Tamil users
ADMIN stats                          → Get usage statistics
```

---

## 14. QUESTIONS? WHO TO ASK

```
Tech architecture issues  → Senior developer
Database design issues    → Senior developer
Feature logic questions   → Read the feature MD file first
WhatsApp API issues       → Check 360dialog docs
Claude API issues         → Check Anthropic docs
Deployment issues         → Check Render docs
```

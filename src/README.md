# Arunachala GPT
WhatsApp AI guide for Tiruvannamalai devotees.

## Setup
1. Clone this repo
2. Create virtual environment: `python -m venv venv`
3. Activate: `source venv/bin/activate`
4. Install packages: `pip install -r requirements.txt`
5. Copy env file: `cp .env.example .env`
6. Fill in your values in `.env`
7. Run: `uvicorn main:app --reload`

## Team Members
Read CLAUDE.md first before writing any code.
Then read your assigned feature MD file in /features/

pip install -r requirements.txt

# Copy env and fill your Supabase + Twilio keys
cp .env.example .env
# Edit .env with your actual values

# Run the server
uvicorn main:app --reload

# You should see:
# INFO: Uvicorn running on http://127.0.0.1:8000
# Open browser: http://localhost:8000
# Should show: {"message": "Arunachala GPT is running 🙏"}
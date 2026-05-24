from fastapi import FastAPI, Request, Form
from src.router import route_message
from src.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Arunachala GPT")


@app.post("/webhook")
async def receive_message(
    request: Request,
    From: str = Form(...),
    Body: str = Form(default=""),
    ButtonText: str = Form(default=""),
):
    """Receive WhatsApp messages from Twilio."""
    try:
        # Remove whatsapp: prefix and + sign
        phone = From.replace("whatsapp:", "").replace("+", "").strip()

        # Button text takes priority over body text
        text = (ButtonText or Body).strip()

        if phone and text:
            await route_message(phone=phone, text=text)

    except Exception as e:
        logger.error(f"Webhook error: {e}")

    # Twilio expects empty 200 response
    return ""


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Arunachala GPT"}


@app.get("/")
async def root():
    return {"message": "Arunachala GPT is running 🙏"}
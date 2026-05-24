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
            to=f"whatsapp:+{phone}",
            body=message
        )
        logger.info(f"Message sent to {phone}: {msg.sid}")
        return {"sid": msg.sid, "status": msg.status}
    except Exception as e:
        logger.error(f"send_text failed to {phone}: {e}")
        raise

async def send_buttons(phone: str, body: str, buttons: list[str]) -> dict:
    """Send message with numbered options (Twilio does not support native buttons)."""
    numbered = "\n".join([f"{i+1}. {b}" for i, b in enumerate(buttons[:3])])
    full_message = f"{body}\n\n{numbered}"
    return await send_text(phone, full_message)

async def send_list(phone: str, body: str,
                    button_label: str, sections: list[dict]) -> dict:
    """Send list as numbered text (Twilio limitation)."""
    lines = [body, ""]
    for section in sections:
        if section.get("title"):
            lines.append(section["title"])
        for row in section.get("rows", []):
            lines.append(f"  {row.get('title', '')}")
    return await send_text(phone, "\n".join(lines))

async def send_audio(phone: str, audio_url: str) -> dict:
    """Send audio file via Twilio WhatsApp."""
    try:
        client = get_client()
        msg = client.messages.create(
            from_=settings.twilio_whatsapp_from,
            to=f"whatsapp:+{phone}",
            media_url=[audio_url]
        )
        return {"sid": msg.sid, "status": msg.status}
    except Exception as e:
        logger.error(f"send_audio failed to {phone}: {e}")
        raise
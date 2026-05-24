from src.language import get_user_language, save_user_language
from src.language import get_language_menu, LANGUAGE_MAP
from src.whatsapp import send_text
from src.config import settings
import logging

logger = logging.getLogger(__name__)


async def route_message(phone: str, text: str) -> None:
    """Route incoming WhatsApp message to correct feature handler."""
    text_stripped = text.strip()
    text_upper = text_stripped.upper()

    # 1. Admin commands
    if text_upper.startswith("ADMIN") and phone == settings.admin_phone:
        from src.features.admin import handle_admin
        await handle_admin(phone, text_stripped)
        return

    # 2. Safety — always highest priority
    if text_upper == "SOS":
        from src.features.sos import handle_sos
        await handle_sos(phone)
        return

    if text_upper.startswith("MISSING"):
        from src.features.missing_person import handle_missing_alert
        await handle_missing_alert(phone, text_stripped)
        return

    if text_upper.startswith("FOUND"):
        from src.features.missing_person import handle_found
        await handle_found(phone, text_stripped)
        return

    # 3. Language selection — if no language saved
    language = await get_user_language(phone)
    if not language:
        if text_stripped in LANGUAGE_MAP:
            lang = LANGUAGE_MAP[text_stripped]
            await save_user_language(phone, lang)
            await send_text(phone,
                f"Language set to {lang.title()} 🙏\n\nHow can I help you today?"
            )
        else:
            await send_text(phone, get_language_menu())
        return

    # 4. Detect intent and dispatch
    intent = detect_intent(text_upper)
    await dispatch(phone, intent, text_stripped, language)


def detect_intent(text: str) -> str:
    """Detect user intent from message keywords."""
    if any(w in text for w in ["CROWD","KOOTTAM","QUEUE","WAIT","TICKET","DARSHAN"]):
        return "crowd"
    if any(w in text for w in ["LINGAM","INDRA","AGNI","YAMA","NIRUTHI",
                                 "VARUNA","VAYU","KUBERA","ISANYA","ASHTA"]):
        return "lingam"
    if any(w in text for w in ["LODGE","ROOM","STAY","HOTEL","BED","ACCOMMODATION"]):
        return "lodge"
    if any(w in text for w in ["CLIMB","HILL","CAVE","VIRUPAKSHA","SKANDASHRAM","SUMMIT"]):
        return "hill"
    if any(w in text for w in ["REACH","BUS","TRAIN","CHENNAI","BANGALORE",
                                 "HYDERABAD","COIMBATORE","MUMBAI","TRAVEL","COME"]):
        return "reach"
    if any(w in text for w in ["GIRIVALAM","CIRCUMAMBULATION","PRADAKSHINA","GUIDE"]):
        return "girivalam_guide"
    if any(w in text for w in ["PRICE","RATE","AUTO","RUDRAKSHA","VIBHUTI","FAIR","COST"]):
        return "price"
    if any(w in text for w in ["ASHRAM","SATSANG","PROGRAM","SCHEDULE","CALENDAR","TEACHER"]):
        return "calendar"
    if any(w in text for w in ["ANNADHANAM","FOOD","SPONSOR","FEED","ANNA"]):
        return "annadhanam"
    if any(w in text for w in ["ABHISHEKAM","ABHI","POOJA","PUJA"]):
        return "abhishekam"
    if any(w in text for w in ["MISSING","LOST","FAMILY","REGISTER","KARTHIGAI"]):
        return "missing"
    if any(w in text for w in ["DEVOTIONAL","DAILY","SUBSCRIBE","MORNING","MESSAGE"]):
        return "devotional"
    return "general"


async def dispatch(phone: str, intent: str, text: str, language: str) -> None:
    """Dispatch to correct feature handler."""
    import importlib

    handlers = {
        "crowd":           ("src.features.crowd_alert",     "handle"),
        "lingam":          ("src.features.lingam_guide",    "handle"),
        "lodge":           ("src.features.lodge_booking",   "handle"),
        "hill":            ("src.features.hill_climb",      "handle"),
        "reach":           ("src.features.how_to_reach",    "handle"),
        "girivalam_guide": ("src.features.girivalam_guide", "handle"),
        "price":           ("src.features.fair_price",      "handle"),
        "calendar":        ("src.features.ashram_calendar", "handle"),
        "annadhanam":      ("src.features.annadhanam",      "handle"),
        "abhishekam":      ("src.features.abhishekam",      "handle"),
        "missing":         ("src.features.missing_person",  "handle"),
        "devotional":      ("src.features.daily_devotional","handle"),
    }

    if intent in handlers:
        module_path, func_name = handlers[intent]
        try:
            module = importlib.import_module(module_path)
            handler = getattr(module, func_name)
            await handler(phone=phone, text=text, language=language)
        except ModuleNotFoundError:
            # Feature not built yet
            await send_text(phone, "This feature is coming soon. 🙏")
    else:
        await handle_general(phone, text, language)


async def handle_general(phone: str, text: str, language: str) -> None:
    """Handle general queries using Claude."""
    from src.claude_ai import get_reply, LANGUAGE_RULE
    reply = await get_reply(
        system_prompt=(
            "You are Arunachala GPT — a helpful guide for devotees "
            "visiting Tiruvannamalai temple.\n" + LANGUAGE_RULE
        ),
        user_message=text,
        max_tokens=300
    )
    await send_text(phone, reply)
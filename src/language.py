from src.database import get_db

LANGUAGE_MAP = {
    "1": "tamil", "2": "telugu",
    "3": "kannada", "4": "hindi", "5": "english"
}

async def get_user_language(phone: str) -> str | None:
    db = get_db()
    result = db.table("devotee_profile")\
        .select("language")\
        .eq("phone", phone)\
        .execute()
    if result.data:
        return result.data[0].get("language")
    return None

async def save_user_language(phone: str, language: str) -> None:
    db = get_db()
    db.table("devotee_profile").upsert({
        "phone": phone,
        "language": language,
        "updated_at": "now()"
    }).execute()

def get_language_menu() -> str:
    return (
        "Welcome to Arunachala GPT! 🙏\n\n"
        "Please select your language:\n"
        "1 — Tamil\n"
        "2 — Telugu\n"
        "3 — Kannada\n"
        "4 — Hindi\n"
        "5 — English\n\n"
        "Reply 1 / 2 / 3 / 4 / 5"
    )
import logging
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# LINGAM KEYWORD MAP
# All known spellings: native scripts + romanizations + misspellings
# ─────────────────────────────────────────────

LINGAM_KEYWORDS = {
    "indra": [
        # English / romanized
        "indra", "inthiran", "indhira", "indiran", "indra lingam",
        "indhiran", "inthira",
        # Tamil script
        "இந்திர", "இந்திர லிங்கம்",
        # Telugu script
        "ఇంద్ర", "ఇంద్ర లింగం",
        # Kannada script
        "ಇಂದ್ರ", "ಇಂದ್ರ ಲಿಂಗ",
        # Hindi script
        "इन्द्र", "इंद्र",
    ],
    "agni": [
        # English / romanized
        "agni", "akni", "agini", "agini lingam", "agni lingam",
        "agnee", "aagni",
        # Tamil script
        "அக்னி", "அக்னி லிங்கம்",
        # Telugu script
        "అగ్ని", "అగ్ని లింగం",
        # Kannada script
        "ಅಗ್ನಿ", "ಅಗ್ನಿ ಲಿಂಗ",
        # Hindi script
        "अग्नि",
    ],
    "yama": [
        # English / romanized
        "yama", "yaman", "yaman lingam", "yama lingam",
        "yamar", "yamam",
        # Tamil script
        "யம", "யம லிங்கம்",
        # Telugu script
        "యమ", "యమ లింగం",
        # Kannada script
        "ಯಮ", "ಯಮ ಲಿಂಗ",
        # Hindi script
        "यम",
    ],
    "niruthi": [
        # English / romanized
        "niruthi", "nirruti", "nirruthi", "nirudhi", "niruti",
        "nirrudi", "nirruti lingam", "niruthi lingam", "nirudi",
        "niruthu", "nirrughi",
        # Tamil script
        "நிருதி", "நிருதி லிங்கம்",
        # Telugu script
        "నిరుతి", "నిరుతి లింగం",
        # Kannada script
        "ನಿರುತಿ", "ನಿರುತಿ ಲಿಂಗ",
        # Hindi script
        "निरुति", "निरुति",
    ],
    "varuna": [
        # English / romanized
        "varuna", "varunan", "varuna lingam", "varunaa",
        "varun", "varunu",
        # Tamil script
        "வருண", "வருண லிங்கம்",
        # Telugu script
        "వరుణ", "వరుణ లింగం",
        # Kannada script
        "ವರುಣ", "ವರುಣ ಲಿಂಗ",
        # Hindi script
        "वरुण",
    ],
    "vayu": [
        # English / romanized
        "vayu", "vaayu", "vayu lingam", "vayuu", "vaio",
        "vayo", "vaayuu",
        # Tamil script
        "வாயு", "வாயு லிங்கம்",
        # Telugu script
        "వాయు", "వాయు లింగం",
        # Kannada script
        "ವಾಯು", "ವಾಯು ಲಿಂಗ",
        # Hindi script
        "वायु",
    ],
    "kubera": [
        # English / romanized
        "kubera", "kubra", "koobera", "koopera", "kubhera",
        "cubeera", "kubera lingam", "kuberan", "kobera",
        "kubhera lingam", "kuvera", "kuvera lingam",
        # Tamil script
        "குபேர", "குபேர லிங்கம்",
        # Telugu script
        "కుబేర", "కుబేర లింగం",
        # Kannada script
        "ಕುಬೇರ", "ಕುಬೇರ ಲಿಂಗ",
        # Hindi script
        "कुबेर",
    ],
    "isanya": [
        # English / romanized
        "isanya", "isana", "esanya", "ishaniya", "ishanya",
        "eesanya", "isanya lingam", "isana lingam", "ishan",
        "ishaanya", "esana", "isaanya",
        # Tamil script
        "ஈசான", "ஈசான லிங்கம்",
        # Telugu script
        "ఈశాన్య", "ఈశాన్య లింగం",
        # Kannada script
        "ಈಶಾನ್ಯ", "ಈಶಾನ್ಯ ಲಿಂಗ",
        # Hindi script
        "ईशान",
    ],
}

LINGAM_NUMBER_MAP = {
    "indra": 1, "agni": 2, "yama": 3, "niruthi": 4,
    "varuna": 5, "vayu": 6, "kubera": 7, "isanya": 8
}

LANGUAGE_AUDIO_MAP = {
    "tamil":   "audio_url_ta",
    "telugu":  "audio_url_te",
    "kannada": "audio_url_kn",
    "hindi":   "audio_url_hi",
    "english": "audio_url_en",
}

FUZZY_THRESHOLD = 82  # minimum match score (0-100)

LINGAM_SYSTEM_PROMPT = """
You are an expert spiritual guide for the 8 Ashta Lingams
on the Girivalam route around Arunachala hill, Tiruvannamalai.

LINGAM DATA:
{lingam_data}

CRITICAL LANGUAGE RULE:
Detect the language of the user message and reply in EXACTLY that language.
Tamil script or romanized Tamil -> reply in Tamil
Telugu -> reply in Telugu
Kannada -> reply in Kannada
Hindi -> reply in Hindi
English -> reply in English

Provide:
1. Location (km from start, direction)
2. Who installed it and why
3. Main blessing and significance
4. What to do when standing there
5. What to offer
6. What to chant
7. Which Navagraha it represents
8. Distance to next lingam

Keep response warm, brief (under 200 words), and practical.
Devotee may be standing at the lingam right now.
End with: distance to next lingam.
"""


# ─────────────────────────────────────────────
# STEP 1: DETECT LINGAM
# First: exact keyword match
# Second: fuzzy match for misspellings
# ─────────────────────────────────────────────

def detect_lingam(text: str) -> str | None:
    text_lower = text.lower().strip()

    # Pass 1 — exact substring match
    for lingam_key, keywords in LINGAM_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                logger.info(f"Exact match: '{keyword}' → {lingam_key}")
                return lingam_key

    # Pass 2 — fuzzy match on each word in user text
    words = text_lower.split()
    for word in words:
        if len(word) < 3:
            continue
        best_score = 0
        best_key = None
        for lingam_key, keywords in LINGAM_KEYWORDS.items():
            for keyword in keywords:
                score = fuzz.ratio(word, keyword.lower())
                if score > best_score:
                    best_score = score
                    best_key = lingam_key
        if best_score >= FUZZY_THRESHOLD:
            logger.info(f"Fuzzy match: '{word}' → {best_key} (score={best_score})")
            return best_key

    return None


# ─────────────────────────────────────────────
# STEP 2: FETCH FROM SUPABASE
# ─────────────────────────────────────────────

async def get_lingam_data(lingam_key: str) -> dict | None:
    from src.database import get_db
    lingam_num = LINGAM_NUMBER_MAP.get(lingam_key)
    if not lingam_num:
        return None
    db = get_db()
    result = (
        db.table("lingam_guide")
        .select("*")
        .eq("lingam_number", lingam_num)
        .execute()
    )
    return result.data[0] if result.data else None


def format_lingam_data(data: dict) -> str:
    return (
        f"Name: {data.get('name_english')}\n"
        f"KM from start: {data.get('km_from_start')}\n"
        f"Direction: {data.get('direction')}\n"
        f"Installed by: {data.get('installed_by')}\n"
        f"Navagraha: {data.get('navagraha')}\n"
        f"Significance: {data.get('significance_en')}\n"
        f"What to do: {data.get('what_to_do_en')}\n"
        f"Offering: {data.get('offering_en')}\n"
        f"Chant: {data.get('chant')}\n"
        f"Best time: {data.get('best_time')}\n"
        f"Next lingam distance: {data.get('next_km')} km ahead"
    )


def get_audio_url(lingam_data: dict, language: str) -> str | None:
    col = LANGUAGE_AUDIO_MAP.get(language, "audio_url_en")
    return lingam_data.get(col) or lingam_data.get("audio_url_en")


# ─────────────────────────────────────────────
# STEP 3: SEND LINGAM INFO (text via Claude + audio immediately)
# ─────────────────────────────────────────────

async def send_lingam_info(phone: str, lingam_key: str, text: str, language: str) -> None:
    from src.claude_ai import get_reply
    from src.whatsapp import send_text, send_audio
    lingam_data = await get_lingam_data(lingam_key)
    if not lingam_data:
        await send_text(phone, "Lingam data not found. Please try again. 🙏")
        return

    system = LINGAM_SYSTEM_PROMPT.format(lingam_data=format_lingam_data(lingam_data))
    reply = await get_reply(system_prompt=system, user_message=text, max_tokens=350)
    await send_text(phone, reply)

    audio_url = get_audio_url(lingam_data, language)
    if audio_url:
        await send_audio(phone, audio_url)
        logger.info(f"Audio sent to {phone}: {audio_url}")
    else:
        logger.info(f"No audio available for {lingam_key} in {language}")


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# Called by router.py → dispatch() → handle()
# ─────────────────────────────────────────────

async def handle(phone: str, text: str, language: str) -> None:
    from src.whatsapp import send_text
    text_clean = text.strip()

    lingam_key = detect_lingam(text_clean)

    if lingam_key:
        await send_lingam_info(phone, lingam_key, text_clean, language)
        return

    await send_text(
        phone,
        "Please ask about a specific lingam. Example:\n"
        "- 'Tell me about Kubera Lingam'\n"
        "- 'Yama lingam pathi sollu'\n\n"
        "The 8 Lingams on Girivalam route:\n"
        "1. Indra  2. Agni  3. Yama  4. Niruthi\n"
        "5. Varuna  6. Vayu  7. Kubera  8. Isanya \U0001f64f"
    )

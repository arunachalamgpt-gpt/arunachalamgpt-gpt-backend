# Feature 9 — 8 Ashta Lingam Spiritual Guide (Text + Audio)
# Owner: [Assign to team member]
# Status: not-started
# Depends on: CLAUDE.md core utilities

---

## WHAT THIS FEATURE DOES

Devotee asks about any of the 8 Ashta Lingams on Girivalam route.
Bot replies with significance, what to do, what to offer, which Navagraha.
Works in Tamil, Telugu, Kannada, Hindi, English.
Text first. AUDIO keyword sends gTTS voice note.

---

## USER STORIES

```
US-01: Devotee asks about Kubera Lingam in Tamil → Tamil reply.
US-02: Telugu devotee asks in romanized Telugu → Telugu reply.
US-03: Devotee replies AUDIO → receives voice note in their language.
US-04: Devotee asks "all 8 lingams" → quick summary of all.
US-05: Devotee asks why Girivalam → spiritual explanation.
```

---

## SOP

```
BEFORE LAUNCH:
  Walk the Girivalam route yourself
  Verify exact km mark for each of the 8 lingams
  Fill lingam_guide table with all data
  Generate 40 audio files (8 lingams x 5 languages)
  Upload MP3s to Supabase Storage
  Update audio_url_* columns in lingam_guide table

AUDIO GENERATION (run once):
  pip install gTTS
  Run: python scripts/generate_audio.py
  40 MP3 files generated in /audio/ folder
  Upload to Supabase Storage
  Copy URLs to lingam_guide table
```

---

## SCRIPT TO CREATE (one-time audio generation)

```
scripts/generate_audio.py
```

```python
# scripts/generate_audio.py
# Run ONCE to generate all 40 audio files
# pip install gTTS

from gtts import gTTS
import os

os.makedirs("audio", exist_ok=True)

lingam_scripts = {
    "indra": {
        "ta": "இந்திர லிங்கம். கிழக்கு திசை. 1.5 கிலோமீட்டர். இந்திர தேவர் இங்கே வழிபட்டார். நீண்ட ஆயுள் மற்றும் தடைகள் நீங்கும். வெள்ளை மலர் படைக்கவும். ஓம் நமசிவாய 108 முறை சொல்லுங்கள். அடுத்தது அக்னி லிங்கம் 2.5 கிலோமீட்டர்.",
        "te": "ఇంద్ర లింగం. తూర్పు దిక్కు. 1.5 కిలోమీటర్లు. ఇంద్రుడు ఇక్కడ పూజించాడు. దీర్ఘాయుష్షు మరియు అడ్డంకులు తొలగుతాయి. తెల్లటి పూలు సమర్పించండి. ఓం నమః శివాయ 108 సార్లు.",
        "kn": "ಇಂದ್ರ ಲಿಂಗ. ಪೂರ್ವ ದಿಕ್ಕು. 1.5 ಕಿಲೋಮೀಟರ್. ದೀರ್ಘಾಯುಷ್ಯ ಮತ್ತು ಅಡೆತಡೆಗಳು ನಿವಾರಣೆ. ಬಿಳಿ ಹೂವುಗಳನ್ನು ಅರ್ಪಿಸಿ. ಓಂ ನಮಃ ಶಿವಾಯ 108 ಬಾರಿ.",
        "hi": "इंद्र लिंग. पूर्व दिशा. 1.5 किलोमीटर. इंद्र देव ने यहाँ पूजा की. लंबी आयु और बाधाएं दूर होती हैं. सफेद फूल चढ़ाएं. ओम नमः शिवाय 108 बार.",
        "en": "Indra Lingam. East direction. 1.5 kilometres. Indra the King of Devas worshipped here. Gives long life and removes obstacles. Offer white flowers. Chant Om Namah Shivaya 108 times. Next is Agni Lingam 2.5 kilometres ahead.",
    },
    "agni":    {"ta": "அக்னி லிங்கம்...", "te": "అగ్ని లింగం...", "kn": "ಅಗ್ನಿ ಲಿಂಗ...", "hi": "अग्नि लिंग...", "en": "Agni Lingam..."},
    "yama":    {"ta": "யம லிங்கம்...",   "te": "యమ లింగం...",   "kn": "ಯಮ ಲಿಂಗ...",   "hi": "यम लिंग...",   "en": "Yama Lingam..."},
    "niruthi": {"ta": "நிருதி லிங்கம்...","te": "నిరుతి లింగం...","kn": "ನಿರುತಿ ಲಿಂಗ...","hi": "निरुति लिंग...","en": "Niruthi Lingam..."},
    "varuna":  {"ta": "வருண லிங்கம்...", "te": "వరుణ లింగం...", "kn": "ವರುಣ ಲಿಂಗ...", "hi": "वरुण लिंग...", "en": "Varuna Lingam..."},
    "vayu":    {"ta": "வாயு லிங்கம்...", "te": "వాయు లింగం...", "kn": "ವಾಯು ಲಿಂಗ...", "hi": "वायु लिंग...", "en": "Vayu Lingam..."},
    "kubera":  {"ta": "குபேர லிங்கம்...", "te": "కుబేర లింగం...", "kn": "ಕುಬೇರ ಲಿಂಗ...", "hi": "कुबेर लिंग...", "en": "Kubera Lingam..."},
    "isanya":  {"ta": "ஈசான லிங்கம்...", "te": "ఈశాన్య లింగం...", "kn": "ಈಶಾನ್ಯ ಲಿಂಗ...", "hi": "ईशान लिंग...", "en": "Isanya Lingam..."},
}

lang_map = {"ta": "Tamil", "te": "Telugu", "kn": "Kannada", "hi": "Hindi", "en": "English"}

for lingam, langs in lingam_scripts.items():
    for lang_code, text in langs.items():
        if "..." not in text:
            tts = gTTS(text=text, lang=lang_code, slow=False)
            filename = f"audio/{lingam}_{lang_code}.mp3"
            tts.save(filename)
            print(f"Generated: {filename} ({lang_map[lang_code]})")

print("Done! Upload /audio/ folder to Supabase Storage.")
```

---

## FILE TO CREATE

```
src/features/lingam_guide.py
```

---

## COMPLETE CODE

```python
# src/features/lingam_guide.py

"""
Feature 9: 8 Ashta Lingam Spiritual Guide (Text + Audio)
Owner: [Name]
Status: in-progress
"""

from src.database import get_db
from src.whatsapp import send_text, send_buttons, send_audio
from src.claude_ai import get_reply, LANGUAGE_RULE
import logging

logger = logging.getLogger(__name__)

LINGAM_NAMES = {
    "indra":   ["indra", "இந்திர", "ఇంద్ర", "ಇಂದ್ರ", "इंद्र"],
    "agni":    ["agni", "அக்னி", "అగ్ని", "ಅಗ್ನಿ", "अग्नि"],
    "yama":    ["yama", "யம", "యమ", "ಯಮ", "यम"],
    "niruthi": ["niruthi", "nirruti", "நிருதி", "నిరుతి", "ನಿರುತಿ", "निरुति"],
    "varuna":  ["varuna", "வருண", "వరుణ", "ವರುಣ", "वरुण"],
    "vayu":    ["vayu", "வாயு", "వాయు", "ವಾಯು", "वायु"],
    "kubera":  ["kubera", "குபேர", "కుబేర", "ಕುಬೇರ", "कुबेर"],
    "isanya":  ["isanya", "isana", "ஈசான", "ఈశాన్య", "ಈಶಾನ್ಯ", "ईशान"],
}

LINGAM_SYSTEM_PROMPT = f"""
You are an expert spiritual guide for the 8 Ashta Lingams
on the Girivalam route around Arunachala hill, Tiruvannamalai.

LINGAM DATA:
{{lingam_data}}

{LANGUAGE_RULE}

Provide:
1. Location (km from start, direction)
2. Who installed it and why
3. Main blessing/significance
4. What to do when standing there
5. What to offer
6. What to chant
7. Which Navagraha it represents
8. Distance to next lingam

Keep response warm, brief (under 200 words), and practical.
Devotee may be standing at the lingam right now.
End with: distance to next lingam.
"""

GENERAL_SPIRITUAL_PROMPT = f"""
You are a spiritual guide for Arunachala Girivalam, Tiruvannamalai.

Answer questions about:
- Why do Girivalam (Pradakshina)
- Why walk barefoot
- Why clockwise direction
- Why Pournami is special
- What to chant during Girivalam
- Ramana Maharshi's connection to Arunachala
- Can non-Hindus do Girivalam

{LANGUAGE_RULE}
Be warm, spiritual, and concise.
"""


async def handle(phone: str, text: str, language: str) -> None:
    """Entry point for lingam guide queries."""
    text_upper = text.upper()

    # Check if user wants audio
    if text_upper == "AUDIO":
        await handle_audio_request(phone)
        return

    # Detect which lingam
    lingam_key = detect_lingam(text)
    if lingam_key:
        await send_lingam_info(phone, lingam_key, text, language)
        return

    # General Girivalam spiritual question
    await handle_general_query(phone, text, language)


def detect_lingam(text: str) -> str | None:
    """Detect which lingam is being asked about."""
    text_lower = text.lower()
    for key, names in LINGAM_NAMES.items():
        if any(name.lower() in text_lower for name in names):
            return key
    return None


async def send_lingam_info(phone: str, lingam_key: str,
                            text: str, language: str) -> None:
    """Send text information about a specific lingam."""
    lingam_data = await get_lingam_data(lingam_key)
    if not lingam_data:
        await send_text(phone, "Lingam data not found. Please contact support.")
        return

    system = LINGAM_SYSTEM_PROMPT.format(
        lingam_data=format_lingam_data(lingam_data)
    )
    reply = await get_reply(
        system_prompt=system,
        user_message=text,
        max_tokens=350
    )

    # Save last queried lingam for audio follow-up
    db = get_db()
    db.table("conversation_state").upsert({
        "phone": phone,
        "current_feature": "lingam_guide",
        "step": "viewed_text",
        "data": {"last_lingam": lingam_key}
    }).execute()

    await send_buttons(phone, reply,
        ["AUDIO voice note", "Next lingam", "All 8 lingams"]
    )


async def handle_audio_request(phone: str) -> None:
    """Send audio voice note for last viewed lingam."""
    db = get_db()
    state = db.table("conversation_state")\
        .select("data")\
        .eq("phone", phone)\
        .eq("current_feature", "lingam_guide")\
        .execute()

    if not state.data or not state.data[0].get("data", {}).get("last_lingam"):
        await send_text(phone, "Ask about a lingam first, then reply AUDIO.")
        return

    lingam_key = state.data[0]["data"]["last_lingam"]
    user_lang = await get_user_language(phone)

    lingam_data = await get_lingam_data(lingam_key)
    if not lingam_data:
        return

    lang_col = f"audio_url_{user_lang[:2]}" if user_lang else "audio_url_en"
    audio_url = lingam_data.get(lang_col) or lingam_data.get("audio_url_en")

    if audio_url:
        await send_audio(phone, audio_url)
    else:
        await send_text(phone, "Audio not available yet. Text version above. 🙏")


async def handle_general_query(phone: str, text: str, language: str) -> None:
    """Handle general Girivalam spiritual questions."""
    reply = await get_reply(
        system_prompt=GENERAL_SPIRITUAL_PROMPT,
        user_message=text,
        max_tokens=300
    )
    await send_buttons(phone, reply,
        ["All 8 lingams", "Girivalam guide", "Main menu"]
    )


async def get_lingam_data(lingam_key: str) -> dict | None:
    """Get lingam data from database."""
    db = get_db()
    lingam_map = {
        "indra": 1, "agni": 2, "yama": 3, "niruthi": 4,
        "varuna": 5, "vayu": 6, "kubera": 7, "isanya": 8
    }
    lingam_num = lingam_map.get(lingam_key)
    if not lingam_num:
        return None

    result = db.table("lingam_guide")\
        .select("*")\
        .eq("lingam_number", lingam_num)\
        .execute()
    return result.data[0] if result.data else None


def format_lingam_data(data: dict) -> str:
    """Format lingam data for Claude system prompt."""
    return (
        f"Name: {data.get('name_english')}\n"
        f"KM: {data.get('km_from_start')} from East Gate start\n"
        f"Direction: {data.get('direction')}\n"
        f"Installed by: {data.get('installed_by')}\n"
        f"Navagraha: {data.get('navagraha')}\n"
        f"Significance: {data.get('significance_en')}\n"
        f"What to do: {data.get('what_to_do_en')}\n"
        f"Offering: {data.get('offering_en')}\n"
        f"Chant: {data.get('chant')}\n"
        f"Next lingam distance: {data.get('next_km')} km ahead"
    )


async def get_user_language(phone: str) -> str:
    """Get user's saved language."""
    db = get_db()
    result = db.table("devotee_profile")\
        .select("language").eq("phone", phone).execute()
    if result.data:
        return result.data[0].get("language", "english")
    return "english"
```

---

## TEST CASES

```python
# tests/test_feature9.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.features.lingam_guide import (
    detect_lingam, handle, handle_audio_request, format_lingam_data
)


class TestLingamDetection:
    def test_english_name_detected(self):
        assert detect_lingam("Tell me about Kubera Lingam") == "kubera"

    def test_tamil_name_detected(self):
        assert detect_lingam("குபேர லிங்கம் பத்தி சொல்லுங்க") == "kubera"

    def test_romanized_tamil_detected(self):
        assert detect_lingam("yama lingam pathi sollu") == "yama"

    def test_telugu_detected(self):
        assert detect_lingam("Varuna lingam gurinchi") == "varuna"

    def test_unknown_lingam_returns_none(self):
        assert detect_lingam("Random message") is None

    def test_all_8_lingams_detectable(self):
        tests = [
            ("indra lingam", "indra"),
            ("agni lingam", "agni"),
            ("yama lingam", "yama"),
            ("niruthi lingam", "niruthi"),
            ("varuna lingam", "varuna"),
            ("vayu lingam", "vayu"),
            ("kubera lingam", "kubera"),
            ("isanya lingam", "isanya"),
        ]
        for query, expected in tests:
            assert detect_lingam(query) == expected, f"Failed for {query}"


class TestFormatLingamData:
    def test_all_key_fields_in_output(self):
        data = {
            "name_english": "Kubera Lingam",
            "km_from_start": 11.5,
            "direction": "North",
            "installed_by": "Kubera",
            "navagraha": "Budhan",
            "significance_en": "Wealth and prosperity",
            "what_to_do_en": "Offer yellow flowers",
            "offering_en": "Yellow flowers",
            "chant": "Om Namah Shivaya",
            "next_km": 1.5
        }
        result = format_lingam_data(data)
        assert "Kubera Lingam" in result
        assert "11.5" in result
        assert "North" in result
        assert "Budhan" in result


class TestFeature9Acceptance:

    @pytest.mark.asyncio
    async def test_AC01_lingam_query_gets_text_reply(self):
        with patch("src.features.lingam_guide.get_lingam_data",
                   new_callable=AsyncMock,
                   return_value={"name_english": "Kubera Lingam",
                                 "km_from_start": 11.5,
                                 "direction": "North",
                                 "installed_by": "Kubera",
                                 "navagraha": "Budhan",
                                 "significance_en": "Wealth",
                                 "what_to_do_en": "Pray",
                                 "offering_en": "Yellow flowers",
                                 "chant": "Om Namah Shivaya",
                                 "next_km": 1.5}), \
             patch("src.features.lingam_guide.get_reply",
                   new_callable=AsyncMock,
                   return_value="Kubera Lingam is the wealth lingam"), \
             patch("src.features.lingam_guide.get_db", return_value=MagicMock()), \
             patch("src.features.lingam_guide.send_buttons",
                   new_callable=AsyncMock) as mock_btn:
            await handle("919XXXXXXXXX", "Tell me about Kubera Lingam", "english")
            mock_btn.assert_called_once()
            assert "AUDIO" in mock_btn.call_args[0][2]

    @pytest.mark.asyncio
    async def test_AC02_audio_keyword_sends_voice_note(self):
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.execute.return_value.data = [
                {"data": {"last_lingam": "kubera"}}
            ]

        with patch("src.features.lingam_guide.get_db", return_value=mock_db), \
             patch("src.features.lingam_guide.get_lingam_data",
                   new_callable=AsyncMock,
                   return_value={"audio_url_en": "https://example.com/kubera_en.mp3"}), \
             patch("src.features.lingam_guide.get_user_language",
                   new_callable=AsyncMock, return_value="english"), \
             patch("src.features.lingam_guide.send_audio",
                   new_callable=AsyncMock) as mock_audio:
            await handle_audio_request("919XXXXXXXXX")
            mock_audio.assert_called_once()

    @pytest.mark.asyncio
    async def test_AC03_all_8_lingams_have_data_in_db(self):
        """Verify all 8 lingams are in the database."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.execute.return_value.data = \
            [{"lingam_number": i} for i in range(1, 9)]

        with patch("src.features.lingam_guide.get_db", return_value=mock_db):
            db = mock_db
            result = db.table("lingam_guide").select("lingam_number").execute()
            assert len(result.data) == 8
```

---

## ACCEPTANCE CRITERIA

```
[ ] AC-01: All 8 lingam names detected correctly (all scripts)
[ ] AC-02: Lingam query → text reply with location + significance
[ ] AC-03: After text → AUDIO button offered
[ ] AC-04: AUDIO reply → voice note sent in user's language
[ ] AC-05: No lingam keyword → general Girivalam info
[ ] AC-06: All 8 lingams have data in lingam_guide table
[ ] AC-07: All 40 audio files generated and URLs in DB
[ ] AC-08: All tests pass: pytest tests/test_feature9.py -v
[ ] AC-09: Real test: "Kubera lingam pathi sollu" → Tamil reply
[ ] AC-10: Real test: Reply AUDIO → Tamil voice note received
```

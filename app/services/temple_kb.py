"""Grounded knowledge base for temple Q&A.

Each entry is a small, atomic fact with a stable `id`, a `text` statement
short enough to inline in a prompt, `keywords` used by the retriever, and a
`topic` for filtering / analytics. Facts are the source of truth for the QA
service — if a fact is wrong here, the bot will confidently say the wrong
thing. Keep them tight and verified.

Adding a new fact:
- Give it a unique `id` (short kebab-style).
- Include search terms in `keywords` — plural forms, common misspellings,
  romanized variants. The retriever tokenizes on ASCII letter runs, so put
  in only lowercase alpha tokens.
- Add at least one eval question in `qa_eval.EVAL_SET` that requires this
  fact — that's how we know the retriever can find it.
"""

from typing import TypedDict


class KBEntry(TypedDict):
    id: str
    text: str
    keywords: list[str]
    topic: str


KB: list[KBEntry] = [
    {
        "id": "annamalaiyar_deity",
        "text": (
            "The primary deity is Lord Shiva, worshipped here as Annamalaiyar "
            "(also called Arunachaleswarar). The temple represents the "
            "fire element (Agni) among the Pancha Bhoota Stalas."
        ),
        "keywords": [
            "deity", "god", "shiva", "annamalaiyar", "arunachaleswarar",
            "fire", "agni", "pancha", "bhoota", "stala",
            "main", "primary",
        ],
        "topic": "deity",
    },
    {
        "id": "unnamulai_goddess",
        "text": (
            "The consort goddess is Unnamulai Amman (also Apita Kuchambal), "
            "a form of Parvati."
        ),
        "keywords": [
            "goddess", "consort", "unnamulai", "amman", "parvati", "apita",
            "kuchambal", "devi", "amba",
        ],
        "topic": "deity",
    },
    {
        "id": "arunachala_hill",
        "text": (
            "The sacred Arunachala hill is itself considered a manifestation "
            "of Shiva. It is central to the temple's identity and to the "
            "Girivalam pilgrimage."
        ),
        "keywords": [
            "hill", "mountain", "arunachala", "manifestation", "sacred",
        ],
        "topic": "geography",
    },
    {
        "id": "gopurams",
        "text": (
            "The temple has four gopurams: the Raja Gopuram on the east "
            "(11 storeys, roughly 66 m tall), plus north, west, and south "
            "gopurams."
        ),
        "keywords": [
            "gopuram", "gopurams", "tower", "raja", "east", "north", "west",
            "south", "gate", "storey", "storeys", "tall", "height",
        ],
        "topic": "architecture",
    },
    {
        "id": "karthigai_deepam",
        "text": (
            "Karthigai Deepam is the temple's largest festival, held in "
            "November or December. A great flame is lit atop Arunachala hill "
            "and is visible for many kilometres."
        ),
        "keywords": [
            "karthigai", "deepam", "festival", "flame", "lamp", "november",
            "december", "biggest", "largest", "diya",
        ],
        "topic": "festival",
    },
    {
        "id": "girivalam_pournami",
        "text": (
            "Pournami Girivalam is the 14 km barefoot circumambulation of "
            "Arunachala hill, undertaken by devotees on every full-moon day."
        ),
        "keywords": [
            "girivalam", "pournami", "full", "moon", "circumambulation",
            "walk", "walking", "barefoot", "14", "km", "pradakshina",
        ],
        "topic": "festival",
    },
    {
        "id": "history_chola",
        "text": (
            "The temple's core structure dates to the Chola period around "
            "the 9th century. It was expanded later by the Vijayanagara and "
            "Hoysala dynasties."
        ),
        "keywords": [
            "history", "old", "age", "ancient", "chola", "vijayanagara",
            "hoysala", "century", "dynasty", "built",
        ],
        "topic": "history",
    },
    {
        "id": "location",
        "text": (
            "The temple is in Tiruvannamalai town in Tamil Nadu — about "
            "185 km from Chennai and 210 km from Bengaluru."
        ),
        "keywords": [
            "location", "where", "tiruvannamalai", "chennai", "bengaluru",
            "bangalore", "distance", "km", "far", "reach", "tamil", "nadu",
        ],
        "topic": "location",
    },
    {
        "id": "opening_time",
        "text": (
            "The temple opens at 5:30 AM every day. The main pujas are held "
            "early morning and evening."
        ),
        "keywords": [
            "open", "opens", "opening", "time", "timing", "hours", "morning",
            "puja", "closes", "closing",
        ],
        "topic": "practical",
    },
    {
        "id": "bus_stand",
        "text": (
            "The Tiruvannamalai bus stand is about 2 km from the east gate; "
            "auto-rickshaws and share-autos are readily available."
        ),
        "keywords": [
            "bus", "stand", "auto", "rickshaw", "transport", "arrive",
            "reach", "walk", "distance",
        ],
        "topic": "practical",
    },
    {
        "id": "ramana_maharshi",
        "text": (
            "The saint Ramana Maharshi lived on Arunachala hill for decades. "
            "The Sri Ramanasramam ashram is a short distance from the temple."
        ),
        "keywords": [
            "ramana", "maharshi", "saint", "guru", "ashram", "ramanasramam",
            "sri",
        ],
        "topic": "saints",
    },
    {
        "id": "seshadri_swamigal",
        "text": (
            "Seshadri Swamigal is another revered saint associated with "
            "Tiruvannamalai; his samadhi shrine is close to the temple."
        ),
        "keywords": [
            "seshadri", "swamigal", "saint", "samadhi", "shrine",
        ],
        "topic": "saints",
    },
]


def all_ids() -> list[str]:
    """Return all KB fact IDs — useful for tests and analytics."""
    return [entry["id"] for entry in KB]


def get(fact_id: str) -> KBEntry:
    """Look up a fact by id. Raises KeyError if missing so callers fail loudly."""
    for entry in KB:
        if entry["id"] == fact_id:
            return entry
    raise KeyError(fact_id)

"""Lodge pricing logic.

`price_for_date` picks the right rate for a given check-in date by consulting
the curated lunar-calendar table in `app.services.lunar_calendar`. The
priority is: Karthigai Deepam → Pournami → normal. Karthigai falls back to
the normal price when the lodge hasn't set a Karthigai rate.
"""

from datetime import date

from app.models.lodge import Lodge
from app.services import lunar_calendar


def price_for_date(lodge: Lodge, checkin_date: date) -> int:
    if lunar_calendar.is_karthigai_deepam(checkin_date) and lodge.price_karthigai:
        return lodge.price_karthigai
    if lunar_calendar.is_pournami(checkin_date):
        return lodge.price_pournami
    return lodge.price_normal

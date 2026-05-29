"""Lodge pricing logic.

`price_for_date` chooses the right rate (normal vs Pournami vs Karthigai) for a
given check-in date. Pournami/Karthigai day-of-month sets are placeholders until
a lunar-calendar lookup is wired in.
"""

from datetime import date

from app.models.lodge import Lodge

POURNAMI_DAYS_OF_MONTH: set[int] = set()
KARTHIGAI_DAYS_OF_MONTH: set[int] = set()


def price_for_date(lodge: Lodge, checkin_date: date) -> int:
    day = checkin_date.day
    if day in KARTHIGAI_DAYS_OF_MONTH and lodge.price_karthigai:
        return lodge.price_karthigai
    if day in POURNAMI_DAYS_OF_MONTH:
        return lodge.price_pournami
    return lodge.price_normal

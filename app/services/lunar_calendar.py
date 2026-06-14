"""Lunar-calendar helpers for ArunachalamGPT.

The full-moon (Pournami) and Karthigai Deepam festival dates drift ~10 days
per Gregorian year because they track the Tamil lunar calendar. A static
day-of-month check (like the placeholder we used to have in
`services/pricing.py`) cannot work; this module ships a hand-curated table
keyed by Gregorian year instead.

**How to extend each November for the following year:**

1. Look up the full-moon dates **in IST** from a panchang source:
   - https://www.drikpanchang.com/panchang/day-panchang.html
   - https://www.timeanddate.com/moon/phases/timezone/india
   - Cross-check at least two sources.
2. Add a new entry to `POURNAMI_DATES[year]`.
3. Look up Karthigai Deepam (Krittika nakshatra in Karthigai month) for the
   year and add it to `KARTHIGAI_DEEPAM_DATES[year]`.
4. `tests/test_services_lunar_calendar.py` has parametrised checks for a
   handful of known dates — add one for the new year.

All comparisons treat the date in IST. If a moon transit happens just past
midnight IST, the "Pournami day" is the calendar date of the morning that
follows the transit, per panchang convention.
"""

from datetime import date

# Hand-curated full-moon (Pournami) dates by Gregorian year, IST.
# Cross-checked against drikpanchang.com and timeanddate.com.
POURNAMI_DATES: dict[int, frozenset[date]] = {
    2026: frozenset(
        {
            date(2026, 1, 3),
            date(2026, 2, 2),
            date(2026, 3, 3),
            date(2026, 4, 2),
            date(2026, 5, 1),
            date(2026, 5, 31),
            date(2026, 6, 29),
            date(2026, 7, 29),
            date(2026, 8, 28),
            date(2026, 9, 26),
            date(2026, 10, 26),
            date(2026, 11, 25),
            date(2026, 12, 24),
        }
    ),
    2027: frozenset(
        {
            date(2027, 1, 23),
            date(2027, 2, 21),
            date(2027, 3, 23),
            date(2027, 4, 21),
            date(2027, 5, 21),
            date(2027, 6, 19),
            date(2027, 7, 19),
            date(2027, 8, 18),
            date(2027, 9, 16),
            date(2027, 10, 15),
            date(2027, 11, 14),
            date(2027, 12, 14),
        }
    ),
}

# Karthigai Deepam (Krittika nakshatra in Karthigai month) — one per year.
KARTHIGAI_DEEPAM_DATES: dict[int, date] = {
    2026: date(2026, 12, 2),
    2027: date(2027, 11, 21),
}


def is_pournami(d: date) -> bool:
    """Return True if `d` is a full-moon Pournami per the curated table.

    Returns False for any year not in `POURNAMI_DATES` — callers should
    treat that as "unknown, assume normal day" rather than as a Pournami.
    """
    return d in POURNAMI_DATES.get(d.year, frozenset())


def is_karthigai_deepam(d: date) -> bool:
    """Return True if `d` is the Karthigai Deepam festival day."""
    return KARTHIGAI_DEEPAM_DATES.get(d.year) == d


def supported_years() -> list[int]:
    """Years for which lunar data is loaded — used by /system diagnostics."""
    return sorted(set(POURNAMI_DATES) | set(KARTHIGAI_DEEPAM_DATES))


def pournami_dates_in_year(year: int) -> list[date]:
    """Return the sorted list of Pournami dates for `year`, or [] if unknown."""
    return sorted(POURNAMI_DATES.get(year, frozenset()))

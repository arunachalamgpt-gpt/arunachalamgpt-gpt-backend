"""Tests for the hand-curated lunar-calendar table.

Includes parametrised checks for every curated date so a typo in the table
(or an accidental year-by-year overwrite) fails immediately. Add a case for
each new year you append to `POURNAMI_DATES` / `KARTHIGAI_DEEPAM_DATES`.
"""

from datetime import date, timedelta

import pytest

from app.services import lunar_calendar


# ---------- known Pournami dates ----------


@pytest.mark.parametrize(
    "d",
    [
        date(2026, 1, 3),
        date(2026, 5, 1),
        date(2026, 5, 31),  # second Pournami in May 2026
        date(2026, 12, 24),
        date(2027, 1, 23),
        date(2027, 6, 19),
        date(2027, 12, 14),
    ],
)
def test_is_pournami_true_for_curated_dates(d):
    assert lunar_calendar.is_pournami(d) is True


def test_is_pournami_false_for_neighbouring_day():
    # 2026-05-01 IS Pournami; one day off should not match.
    assert lunar_calendar.is_pournami(date(2026, 4, 30)) is False
    assert lunar_calendar.is_pournami(date(2026, 5, 2)) is False


def test_is_pournami_false_for_year_not_in_table():
    # We don't ship data for 2030 — return False, never crash.
    assert lunar_calendar.is_pournami(date(2030, 5, 1)) is False


# ---------- Karthigai Deepam ----------


@pytest.mark.parametrize(
    "d",
    [
        date(2026, 12, 2),
        date(2027, 11, 21),
    ],
)
def test_is_karthigai_deepam_true_for_curated(d):
    assert lunar_calendar.is_karthigai_deepam(d) is True


def test_is_karthigai_deepam_false_for_neighbours():
    assert lunar_calendar.is_karthigai_deepam(date(2026, 12, 1)) is False
    assert lunar_calendar.is_karthigai_deepam(date(2026, 12, 3)) is False


def test_is_karthigai_deepam_false_for_unknown_year():
    assert lunar_calendar.is_karthigai_deepam(date(2030, 11, 1)) is False


# ---------- introspection helpers ----------


def test_supported_years_sorted_and_unique():
    years = lunar_calendar.supported_years()
    assert years == sorted(set(years))
    assert 2026 in years
    assert 2027 in years


def test_pournami_dates_in_year_returns_sorted_list():
    dates = lunar_calendar.pournami_dates_in_year(2026)
    assert dates == sorted(dates)
    # ~12-13 full moons per year; allow either.
    assert 12 <= len(dates) <= 13


def test_pournami_dates_in_year_empty_for_unknown():
    assert lunar_calendar.pournami_dates_in_year(2030) == []


# ---------- table integrity ----------


def test_every_pournami_date_is_actually_in_its_keyed_year():
    """Guards against typos like adding date(2027, 5, 1) under POURNAMI_DATES[2026]."""
    for year, dates in lunar_calendar.POURNAMI_DATES.items():
        for d in dates:
            assert d.year == year, f"{d} should not be keyed under {year}"


def test_pournami_dates_have_sensible_spacing():
    """Full moons should be ~29-30 days apart. Catches duplicates and obvious typos."""
    for year, dates in lunar_calendar.POURNAMI_DATES.items():
        ordered = sorted(dates)
        for prev, curr in zip(ordered, ordered[1:]):
            gap = (curr - prev).days
            assert 27 <= gap <= 32, (
                f"Unusual {gap}-day gap in {year}: {prev} → {curr}"
            )

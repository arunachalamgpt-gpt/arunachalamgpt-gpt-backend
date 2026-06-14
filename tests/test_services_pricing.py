from datetime import date
from types import SimpleNamespace

from app.services import pricing


def _lodge(price_normal=500, price_pournami=800, price_karthigai=1500):
    return SimpleNamespace(
        price_normal=price_normal,
        price_pournami=price_pournami,
        price_karthigai=price_karthigai,
    )


def test_default_uses_normal_price():
    # 2026-06-07 is neither Pournami nor Karthigai per the table
    assert pricing.price_for_date(_lodge(), date(2026, 6, 7)) == 500


def test_pournami_day_uses_pournami_price():
    # 2026-05-01 is a curated Pournami date
    assert pricing.price_for_date(_lodge(), date(2026, 5, 1)) == 800


def test_karthigai_day_uses_karthigai_price():
    # 2026-12-02 is the curated Karthigai Deepam date for 2026
    assert pricing.price_for_date(_lodge(), date(2026, 12, 2)) == 1500


def test_karthigai_without_price_falls_back_to_normal():
    lodge = _lodge(price_karthigai=None)
    assert pricing.price_for_date(lodge, date(2026, 12, 2)) == 500


def test_unknown_year_treated_as_normal():
    # 2029 isn't in the table — should never accidentally pick a holiday rate
    assert pricing.price_for_date(_lodge(), date(2029, 5, 1)) == 500

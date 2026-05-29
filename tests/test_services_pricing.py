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
    assert pricing.price_for_date(_lodge(), date(2026, 6, 7)) == 500


def test_pournami_day_uses_pournami_price(monkeypatch):
    monkeypatch.setattr(pricing, "POURNAMI_DAYS_OF_MONTH", {15})
    assert pricing.price_for_date(_lodge(), date(2026, 6, 15)) == 800


def test_karthigai_day_uses_karthigai_price(monkeypatch):
    monkeypatch.setattr(pricing, "KARTHIGAI_DAYS_OF_MONTH", {28})
    assert pricing.price_for_date(_lodge(), date(2026, 6, 28)) == 1500


def test_karthigai_without_price_falls_back_to_normal(monkeypatch):
    monkeypatch.setattr(pricing, "KARTHIGAI_DAYS_OF_MONTH", {28})
    lodge = _lodge(price_karthigai=None)
    assert pricing.price_for_date(lodge, date(2026, 6, 28)) == 500

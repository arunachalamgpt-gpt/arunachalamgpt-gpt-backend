from datetime import date

from app.services import planning


def test_recommend_elderly_early_rs200():
    r = planning.recommend(
        visit_date=date.today(), has_elderly=True, has_children=False
    )
    assert "Rs.200" in r.recommended_line
    assert "4:30" in r.recommended_arrival
    assert any("medical" in item.lower() for item in r.packing_checklist)


def test_recommend_children_includes_snacks():
    r = planning.recommend(
        visit_date=date.today(), has_elderly=False, has_children=True
    )
    assert any("snack" in item.lower() for item in r.packing_checklist)


def test_recommend_no_special_needs_mid_morning_rs50():
    r = planning.recommend(
        visit_date=date.today(), has_elderly=False, has_children=False
    )
    assert "Rs.50" in r.recommended_line
    assert "8:00 AM" in r.recommended_arrival


def test_recommend_pournami_warns_and_recommends_early():
    r = planning.recommend(
        visit_date=date.today(),
        has_elderly=False,
        has_children=False,
        is_pournami=True,
    )
    assert "Pournami" in r.rationale
    assert "4:30" in r.recommended_arrival  # Pournami treated as heavy day


def test_recommend_festival_warns_and_recommends_early():
    r = planning.recommend(
        visit_date=date.today(),
        has_elderly=False,
        has_children=False,
        is_festival=True,
    )
    assert "Karthigai Deepam" in r.rationale
    assert "4:30" in r.recommended_arrival


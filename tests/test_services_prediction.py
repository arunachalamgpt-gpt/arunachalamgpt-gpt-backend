from datetime import date

from app.schemas.crowd import CrowdHistoryIn
from app.services import prediction


def test_predict_empty_returns_none_means(db_session):
    p = prediction.predict(
        db_session, visit_date=date.today(), hour_of_day=7, is_pournami=False
    )
    assert p.sample_size == 0
    assert p.free_wait_min is None
    assert p.rs50_wait_min is None
    assert p.rs200_wait_min is None


def test_predict_averages_rows(db_session):
    for free in [60, 120, 180]:
        prediction.record_history(
            db_session,
            CrowdHistoryIn(
                visit_date=date.today(),
                hour_of_day=8,
                is_pournami=True,
                is_festival=False,
                free_wait_min=free,
                rs50_wait_min=20,
                rs200_wait_min=5,
            ),
        )
    db_session.commit()
    p = prediction.predict(
        db_session, visit_date=date.today(), hour_of_day=8, is_pournami=True
    )
    assert p.sample_size == 3
    assert p.free_wait_min == 120
    assert p.rs50_wait_min == 20


def test_predict_ignores_null_values(db_session):
    prediction.record_history(
        db_session,
        CrowdHistoryIn(
            visit_date=date.today(),
            hour_of_day=9,
            free_wait_min=None,
            rs50_wait_min=30,
            rs200_wait_min=10,
        ),
    )
    db_session.commit()
    p = prediction.predict(db_session, visit_date=date.today(), hour_of_day=9)
    assert p.free_wait_min is None
    assert p.rs50_wait_min == 30

from app.services import temple_config


def test_ensure_defaults_seeds_known_keys(db_session):
    inserted = temple_config.ensure_defaults(db_session)
    assert inserted == len(temple_config.DEFAULTS)
    # second call is a no-op
    assert temple_config.ensure_defaults(db_session) == 0


def test_upsert_inserts_then_updates(db_session):
    row = temple_config.upsert(db_session, "x", "1", description="d")
    assert row.value == "1"
    row2 = temple_config.upsert(db_session, "x", "2", updated_by="9876543210")
    assert row2.value == "2"
    assert row2.description == "d"  # preserved
    assert row2.updated_by == "9876543210"


def test_list_all_orders_by_key(db_session):
    temple_config.upsert(db_session, "b", "1")
    temple_config.upsert(db_session, "a", "1")
    keys = [r.key for r in temple_config.list_all(db_session)]
    assert keys == sorted(keys)


def test_is_truthy_handles_none_and_variants():
    assert temple_config.is_truthy(None) is False
    assert temple_config.is_truthy("") is False
    assert temple_config.is_truthy("true") is True
    assert temple_config.is_truthy("YES") is True
    assert temple_config.is_truthy("nope") is False


def test_model_default_updated_at(db_session):
    """Construct a row without `updated_at` to exercise the model's default_factory."""
    from app.models.temple_config import TempleConfig

    row = TempleConfig(key="k_default", value="v")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.updated_at is not None


def test_upsert_updates_existing_row_value(db_session):
    """Confirm the else-branch of `upsert` runs (row.value reassigned)."""
    temple_config.upsert(db_session, "y", "first", description="orig")
    db_session.commit()
    row = temple_config.upsert(db_session, "y", "second")
    db_session.commit()
    assert row.value == "second"
    assert row.description == "orig"  # preserved when not passed


def test_upsert_updates_description_on_existing(db_session):
    temple_config.upsert(db_session, "z", "1", description="first")
    db_session.commit()
    row = temple_config.upsert(db_session, "z", "2", description="updated")
    db_session.commit()
    assert row.description == "updated"

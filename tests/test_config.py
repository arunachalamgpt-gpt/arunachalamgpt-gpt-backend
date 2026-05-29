import importlib
import os

import pytest


def test_config_loads_with_db_url():
    import app.config as cfg
    assert cfg.DB_CONNECTION_STRING == "sqlite:///:memory:"
    assert cfg.DB_POOL_SIZE >= 1
    assert cfg.APP_PORT >= 1
    assert isinstance(cfg.CORS_ORIGINS, list)


def test_config_raises_when_db_url_missing(monkeypatch):
    monkeypatch.setenv("DB_CONNECTION_STRING", "")
    monkeypatch.setattr("app.config.load_dotenv", lambda *a, **kw: False)
    import app.config as cfg

    try:
        with pytest.raises(RuntimeError, match="DB_CONNECTION_STRING"):
            importlib.reload(cfg)
    finally:
        monkeypatch.setenv("DB_CONNECTION_STRING", "sqlite:///:memory:")
        monkeypatch.undo()
        importlib.reload(cfg)


def test_config_parses_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example, ")
    import app.config as cfg
    importlib.reload(cfg)
    try:
        assert cfg.CORS_ORIGINS == ["https://a.example", "https://b.example"]
    finally:
        monkeypatch.setenv("CORS_ORIGINS", "*")
        importlib.reload(cfg)

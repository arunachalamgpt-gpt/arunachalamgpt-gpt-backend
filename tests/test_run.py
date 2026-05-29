import runpy

import pytest


def test_run_module_invokes_uvicorn(monkeypatch):
    called = {}

    def fake_run(target, host, port, reload):
        called["target"] = target
        called["host"] = host
        called["port"] = port
        called["reload"] = reload

    import uvicorn
    monkeypatch.setattr(uvicorn, "run", fake_run)
    runpy.run_path("run.py", run_name="__main__")
    assert called["target"] == "app.main:app"

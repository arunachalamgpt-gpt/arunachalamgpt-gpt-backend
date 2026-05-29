import logging

from app.logging_config import setup_logging


def test_setup_logging_idempotent():
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    setup_logging("DEBUG")
    handler_count = len(root.handlers)
    setup_logging("DEBUG")
    assert len(root.handlers) == handler_count


def test_setup_logging_sets_request_id_format():
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    setup_logging("INFO")
    fmt = root.handlers[0].formatter._fmt  # type: ignore[union-attr]
    assert "request_id" in fmt

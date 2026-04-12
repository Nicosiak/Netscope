"""Pytest hooks — close global SQLite worker so connections are not left open."""

from __future__ import annotations

import pytest


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    try:
        from core import storage as storage_mod

        storage_mod.storage.close()
    except Exception:
        pass

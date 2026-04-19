"""Pytest hooks — close global SQLite worker so connections are not left open."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Keep Hypothesis example DB under `.cache/hypothesis` (see `scripts/clean_caches.sh`)."""
    from hypothesis import settings
    from hypothesis.database import DirectoryBasedExampleDatabase

    root = Path(config.rootpath)
    hyp = root / ".cache" / "hypothesis"
    hyp.mkdir(parents=True, exist_ok=True)
    settings.register_profile(
        "default",
        database=DirectoryBasedExampleDatabase(str(hyp)),
    )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    try:
        from core import storage as storage_mod

        storage_mod.storage.close()
    except Exception:
        pass

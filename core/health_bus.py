"""Collector health event bus — pub/sub for data and error events."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

Callback = Callable[[str, Any], None]


class HealthBus:
    """
    Collectors or app code call emit_data() or emit_error().
    Subscribers receive callbacks on the calling thread — schedule onto Tk via queue_fn.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: Dict[str, List[Callback]] = {}
        self._last_status: Dict[str, str] = {}
        self._last_error: Dict[str, str] = {}

    def subscribe(self, source: str, callback: Callback) -> None:
        """callback(status, payload) where status is 'ok' or 'error'."""
        with self._lock:
            self._subs.setdefault(source, []).append(callback)

    def emit_data(self, source: str, data: Any) -> None:
        with self._lock:
            self._last_status[source] = "ok"
            self._last_error.pop(source, None)
            cbs = list(self._subs.get(source, []))
        for cb in cbs:
            try:
                cb("ok", data)
            except Exception:
                pass

    def emit_error(self, source: str, message: str) -> None:
        with self._lock:
            self._last_status[source] = "error"
            self._last_error[source] = message
            cbs = list(self._subs.get(source, []))
        for cb in cbs:
            try:
                cb("error", message)
            except Exception:
                pass

    def last_status(self, source: str) -> Optional[str]:
        return self._last_status.get(source)

    def last_error(self, source: str) -> Optional[str]:
        return self._last_error.get(source)


bus = HealthBus()

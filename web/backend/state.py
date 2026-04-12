"""Thread-safe shared state for the web backend.

All mutable state lives here so every module imports from one place
and races are impossible to introduce accidentally.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from typing import Deque, List, Optional, Tuple


class PingState:
    """Holds the live ping RTT, rolling history, and current target host.

    All reads and writes are protected by a single lock so concurrent
    WebSocket handlers and the background ping worker never race.
    """

    def __init__(self, maxlen: int = 80, default_target: str = "8.8.8.8") -> None:
        self._lock = threading.Lock()
        self._rtt: Optional[float] = None
        self._history: Deque[Optional[float]] = deque(maxlen=maxlen)
        self._target: str = default_target

    # ── writes ──────────────────────────────────────────────────

    def record(self, rtt: Optional[float]) -> None:
        with self._lock:
            self._rtt = rtt
            self._history.append(rtt)

    def set_target(self, host: str) -> None:
        with self._lock:
            self._target = host
            self._history.clear()
            self._rtt = None

    # ── reads ───────────────────────────────────────────────────

    def snapshot(self) -> Tuple[Optional[float], List[Optional[float]], str]:
        """Return (current_rtt, history_copy, target) atomically."""
        with self._lock:
            return self._rtt, list(self._history), self._target

    def get_target(self) -> str:
        with self._lock:
            return self._target


class RssiState:
    """Rolling RSSI history for stability / averaging metrics.

    Window is kept at ``maxlen`` slots; each slot is either an ``int``
    dBm value or ``None`` (disconnected / unavailable).
    """

    def __init__(self, maxlen: int = 20) -> None:
        self._lock = threading.Lock()
        self._history: Deque[Optional[int]] = deque(maxlen=maxlen)

    def record(self, rssi: Optional[int]) -> None:
        with self._lock:
            self._history.append(rssi)

    def stats(self) -> Tuple[Optional[float], Optional[float]]:
        """Return (avg10, stddev_all) over the current history window.

        avg10   — mean of the last 10 non-null samples (2.5 s at 250 ms tick).
        stddev  — population std-dev of all non-null samples in the window.
                  Returns None if fewer than 2 samples are available.
        """
        with self._lock:
            vals = [v for v in self._history if isinstance(v, int)]

        if not vals:
            return None, None

        avg10: Optional[float] = round(sum(vals[-10:]) / len(vals[-10:]), 1) if vals[-10:] else None

        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            variance = sum((v - mean) ** 2 for v in vals) / len(vals)
            stddev: Optional[float] = round(math.sqrt(variance), 1)
        else:
            stddev = None

        return avg10, stddev


# ── Module-level singletons ───────────────────────────────────────

ping = PingState()
rssi = RssiState()

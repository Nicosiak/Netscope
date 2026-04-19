"""Continuous ping using icmplib (unprivileged on macOS)."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Sequence

from icmplib import ping

from collectors.ping_stats import stats_from_rtt_history
from core.sanitize import normalize_diagnostic_host


class PingSampler:
    """
    Background ICMP pings; reports RTT and rolling stats.
    Uses queue_fn to schedule UI updates on the Tk main thread.
    """

    def __init__(
        self,
        target: str = "8.8.8.8",
        interval_s: float = 1.0,
        history_max: int = 60,
        queue_fn: Optional[Callable[[Callable[[], None]], None]] = None,
    ) -> None:
        self.target = target
        self.interval_s = interval_s
        self.history_max = history_max
        self.queue_fn = queue_fn or (lambda f: f())
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._history: Deque[Optional[float]] = deque(maxlen=history_max)
        self.on_sample: Optional[Callable[[Dict], None]] = None

    def set_target(self, target: str) -> None:
        n = normalize_diagnostic_host(target.strip())
        if n:
            self.target = n

    def _emit(self, payload: Dict) -> None:
        cb = self.on_sample
        if cb:
            cb(payload)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                rtt: Optional[float] = None
                lost = False
                try:
                    res = ping(self.target, count=1, timeout=1.5, privileged=False)
                    if res.packets_received > 0 and res.avg_rtt is not None:
                        rtt = float(res.avg_rtt)
                    else:
                        lost = True
                except Exception:
                    lost = True

                self._history.append(None if lost else rtt)

                hist_list = list(self._history)
                stats = stats_from_rtt_history(hist_list)
                payload = {
                    "target": self.target,
                    "rtt_ms": rtt,
                    "lost": lost,
                    "history_ms": hist_list,
                    **stats,
                    "ts": time.time(),
                }

                try:
                    self.queue_fn(lambda p=payload: self._emit(p))
                except Exception:
                    pass
            except Exception:
                pass

            self._stop.wait(self.interval_s)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval_s + 2)

    def reset_history(self) -> None:
        self._history.clear()

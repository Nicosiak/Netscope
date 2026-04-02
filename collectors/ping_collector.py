"""Continuous ping using icmplib (unprivileged on macOS)."""

from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Optional

from icmplib import ping


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
        self.target = target.strip() or self.target

    def _emit(self, payload: Dict) -> None:
        if self.on_sample:
            self.on_sample(payload)

    def _loop(self) -> None:
        while not self._stop.is_set():
            rtt: Optional[float] = None
            lost = False
            try:
                # Unprivileged ICMP works on recent macOS without root
                res = ping(self.target, count=1, timeout=1.5, privileged=False)
                if res.packets_received > 0 and res.avg_rtt is not None:
                    rtt = float(res.avg_rtt)
                else:
                    lost = True
            except Exception:
                lost = True

            self._history.append(None if lost else rtt)

            valid = [x for x in self._history if x is not None]
            total = len(self._history)
            received = len(valid)
            loss_pct = 100.0 * (total - received) / total if total else 0.0

            jitter: Optional[float] = None
            if len(valid) >= 2:
                try:
                    jitter = float(statistics.pstdev(valid))
                except statistics.StatisticsError:
                    jitter = None

            payload = {
                "target": self.target,
                "rtt_ms": rtt,
                "lost": lost,
                "history_ms": list(self._history),
                "min_ms": min(valid) if valid else None,
                "max_ms": max(valid) if valid else None,
                "avg_ms": (sum(valid) / len(valid)) if valid else None,
                "jitter_ms": jitter,
                "loss_pct": loss_pct,
                "ts": time.time(),
            }

            try:
                self.queue_fn(lambda p=payload: self._emit(p))
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

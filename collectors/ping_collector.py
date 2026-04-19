"""Continuous ping using icmplib (unprivileged on macOS)."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Sequence

from icmplib import ping

from core.host_sanitize import normalize_diagnostic_host


def stats_from_rtt_history(history: Sequence[Optional[float]]) -> Dict[str, Optional[float]]:
    """Professional-grade RTT statistics from a rolling history of RTT samples and None (loss).

    Mirrors web/backend/ping_stats.py exactly — keep both in sync.
    """
    from typing import List
    valid: List[float] = [x for x in history if x is not None]
    total = len(history)
    received = len(valid)
    loss_pct = 100.0 * (total - received) / total if total else 0.0

    if not valid:
        return {
            "min_ms": None, "avg_ms": None, "p50_ms": None,
            "p95_ms": None, "max_ms": None,
            "jitter_ms": None, "loss_pct": loss_pct,
        }

    sv = sorted(valid)
    n  = len(sv)
    p50 = sv[n // 2] if n % 2 else (sv[n // 2 - 1] + sv[n // 2]) / 2.0
    p95 = sv[min(math.ceil(0.95 * n) - 1, n - 1)]

    diffs: List[float] = []
    prev: Optional[float] = None
    for v in history:
        if v is not None:
            if prev is not None:
                diffs.append(abs(v - prev))
            prev = v
        else:
            prev = None

    jitter: Optional[float] = round(sum(diffs) / len(diffs), 3) if diffs else None

    return {
        "min_ms":    round(min(valid), 3),
        "avg_ms":    round(sum(valid) / n, 3),
        "p50_ms":    round(p50, 3),
        "p95_ms":    round(p95, 3),
        "max_ms":    round(max(valid), 3),
        "jitter_ms": jitter,
        "loss_pct":  loss_pct,
    }


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

"""Continuous ping using icmplib (unprivileged on macOS)."""

from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Sequence

from icmplib import ping

from core.health_bus import bus
from core.host_sanitize import normalize_diagnostic_host


def stats_from_rtt_history(history: Sequence[Optional[float]]) -> Dict[str, Optional[float]]:
    """
    Rolling min/max/avg RTT, jitter (population stdev), and loss % from a history
    of successful RTT samples (float) and failed samples (None).
    """
    valid = [x for x in history if x is not None]
    total = len(history)
    received = len(valid)
    loss_pct = 100.0 * (total - received) / total if total else 0.0
    jitter: Optional[float] = None
    if len(valid) >= 2:
        try:
            jitter = float(statistics.pstdev(valid))
        except statistics.StatisticsError:
            jitter = None
    return {
        "min_ms": min(valid) if valid else None,
        "max_ms": max(valid) if valid else None,
        "avg_ms": (sum(valid) / len(valid)) if valid else None,
        "jitter_ms": jitter,
        "loss_pct": loss_pct,
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
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"

                def err_cb(m: str = msg) -> None:
                    bus.emit_error("ping", m)

                try:
                    self.queue_fn(err_cb)
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

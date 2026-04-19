"""Pure RTT statistics — no icmplib dependency.

Single source of truth imported by both ``collectors.ping_collector``
and ``web.backend.ping_stats``.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence


def stats_from_rtt_history(history: Sequence[Optional[float]]) -> Dict[str, Optional[float]]:
    """Professional-grade RTT statistics from a rolling history of RTT samples and None (loss).

    Jitter: mean absolute deviation of *consecutive* RTT pairs, resetting across
    packet-loss events.  This matches RFC 3393 / mtr / Wireshark semantics — not
    population stddev, which measures overall spread rather than inter-arrival variation.

    p50 / p95: percentiles computed over the valid sample window.  p50 is the
    spike-resistant "typical" latency; p95 shows how bad the worst 5% is without
    being skewed by a single outlier the way max is.
    """
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

"""RTT history statistics for the web backend (no icmplib import).

Duplicated from ``collectors/ping_collector.py`` so importing
``payload`` does not require icmplib at module load time.
"""

from __future__ import annotations

import statistics
from typing import Dict, Optional, Sequence


def stats_from_rtt_history(history: Sequence[Optional[float]]) -> Dict[str, Optional[float]]:
    """Min/max/avg RTT, jitter (population stdev), and loss % from RTT + None samples."""
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

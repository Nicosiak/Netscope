"""RTT history statistics for the web backend.

Re-exports from ``collectors.ping_stats`` — single source of truth,
no icmplib import at payload module load time.
"""

from collectors.ping_stats import stats_from_rtt_history as stats_from_rtt_history

__all__ = ["stats_from_rtt_history"]

"""Background ICMP ping worker.

Runs a single daemon thread that pings the current target at ~1 Hz and
writes results into the shared PingState.  The worker starts on server
startup and stops cleanly on shutdown.

Only one thread is ever running at a time; ``ensure_running()`` is
protected by a lock so concurrent callers are safe.
"""

from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
import threading
from typing import Any, Optional

from web.backend.state import ping as ping_state

log = logging.getLogger(__name__)

_start_lock = threading.Lock()
_stop_event = threading.Event()
_thread: Optional[threading.Thread] = None

_RTT_RE = re.compile(r"time[=<]([\d.]+)\s*ms", re.IGNORECASE)


def _ping_via_system(target: str) -> Optional[float]:
    """One ICMP probe using the OS ``ping`` binary (works without icmplib)."""
    ping_bin = shutil.which("ping")
    if not ping_bin:
        return None
    if platform.system() == "Darwin":
        args = [ping_bin, "-c", "1", "-W", "2000", target]  # -W = wait ms on macOS
    else:
        args = [ping_bin, "-c", "1", "-W", "2", target]  # -W = wait seconds on Linux
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=3,
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        m = _RTT_RE.search(text)
        if m:
            return float(m.group(1))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        log.debug("System ping failed for %s", target, exc_info=True)
    return None


def _do_ping(target: str, icmp_fn: Any) -> Optional[float]:
    """Single ping attempt; returns RTT ms or None."""
    rtt: Optional[float] = None
    if icmp_fn is not None:
        try:
            res = icmp_fn(target, count=1, timeout=1.5, privileged=False)
            if res.packets_received > 0 and res.avg_rtt is not None:
                rtt = float(res.avg_rtt)
        except Exception:
            log.debug("icmplib ping error for %s", target, exc_info=True)
    if rtt is None:
        rtt = _ping_via_system(target)
    return rtt


def _loop() -> None:
    icmp_ping: Any = None
    try:
        from icmplib import ping as icmp_ping
    except ImportError:
        log.warning("icmplib not installed — using system ping for Tools ICMP")

    log.info("Ping worker started (target=%s)", ping_state.get_target())

    warmed_target: Optional[str] = None  # last target that got a warmup ping

    while not _stop_event.is_set():
        if ping_state.is_paused():
            _stop_event.wait(1.0)
            continue

        target = ping_state.get_target()

        # Warmup on target change — primes DNS + ARP cache; result discarded
        if target != warmed_target:
            warmed_target = target
            from web.backend.payload import reset_baseline
            reset_baseline()
            log.debug("Warmup ping → %s", target)
            _do_ping(target, icmp_ping)
            _stop_event.wait(1.0)
            continue

        rtt = _do_ping(target, icmp_ping)
        ping_state.record(rtt)
        _stop_event.wait(1.0)

    log.info("Ping worker stopped")


def ensure_running() -> None:
    """Start the ping worker if it is not already alive."""
    global _thread
    with _start_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_loop, daemon=True, name="ping-worker")
        _thread.start()


def stop() -> None:
    """Signal the worker to stop and wait for it to finish."""
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=3.0)

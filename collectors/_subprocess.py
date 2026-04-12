"""Shared subprocess helpers — list args only, always with timeouts."""

from __future__ import annotations

import subprocess
from typing import List


def run_text(args: List[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Run *args* with capture_output; never uses ``shell=True``."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def merged_output(proc: subprocess.CompletedProcess[str]) -> str:
    """Combine stdout and stderr (dig/network tools often split across both)."""
    return (proc.stdout or "") + (proc.stderr or "")


def run_merged_safe(args: List[str], *, timeout: float) -> str:
    """Like :func:`run_text` then :func:`merged_output`, or a short error string."""
    try:
        return merged_output(run_text(args, timeout=timeout))
    except Exception as e:
        return f"(error running {' '.join(args)}: {e})"

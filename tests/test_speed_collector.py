"""Unit tests for networkQuality summarization."""

from __future__ import annotations

from collectors import speed_collector as sc


def test_summarize_not_ok_returns_raw() -> None:
    assert sc.summarize({"ok": False, "raw": "missing tool"}) == "missing tool"


def test_summarize_no_json_returns_raw_fallback() -> None:
    assert sc.summarize({"ok": True}) == "No data."


def test_summarize_formats_throughput_and_latency() -> None:
    data = {
        "ok": True,
        "json": {
            "dl_throughput": 50_000_000,
            "ul_throughput": 10_000_000,
            "responsiveness": 500,
            "base_rtt": 12,
        },
    }
    out = sc.summarize(data)
    assert "Download (Mbps): 50.0" in out
    assert "Upload (Mbps): 10.0" in out
    assert "Responsiveness (RPM): 500" in out
    assert "Idle latency (ms): 12" in out

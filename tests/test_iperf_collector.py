"""Unit tests for iperf3 JSON summarization."""

from __future__ import annotations

from unittest.mock import patch

from collectors.iperf_collector import run_iperf3, summarize_result


def test_run_iperf3_rejects_invalid_host() -> None:
    with patch("collectors.iperf_collector.iperf3_available", return_value=True):
        out = run_iperf3("evil;rm")
    assert out["ok"] is False
    assert "Invalid" in (out.get("raw") or "")


def test_summarize_empty_result() -> None:
    s = summarize_result({"ok": False})
    assert s["mbps"] is None
    assert s["bits_per_second"] is None


def test_summarize_tcp_receive_bits() -> None:
    data = {
        "ok": True,
        "json": {
            "end": {
                "sum_received": {"bits_per_second": 100_000_000, "seconds": 10},
                "sum_sent": {"retransmits": 2, "bits_per_second": 0},
            },
        },
    }
    s = summarize_result(data)
    assert s["mbps"] == 100.0
    assert s["bits_per_second"] == 100_000_000
    assert s["retransmits"] == 2
    assert s["duration_s"] == 10


def test_summarize_udp_metrics() -> None:
    data = {
        "ok": True,
        "json": {
            "end": {
                "sum": {
                    "jitter_ms": 0.5,
                    "lost_percent": 1.2,
                    "bits_per_second": 50_000_000,
                },
            },
        },
    }
    s = summarize_result(data)
    assert s["jitter_ms"] == 0.5
    assert s["lost_percent"] == 1.2
    assert s["mbps"] == 50.0

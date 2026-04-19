"""Unit tests for networkQuality summarization and metrics extraction."""

from __future__ import annotations

from typing import Any, List

import pytest

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


def test_summarize_includes_interface_when_present() -> None:
    data = {
        "ok": True,
        "json": {
            "interface_name": "en0",
            "dl_throughput": 1_000_000,
        },
    }
    out = sc.summarize(data)
    assert out.startswith("Interface: en0")


def test_extract_metrics_ok() -> None:
    data = {
        "ok": True,
        "json": {
            "dl_throughput": 48_000_000,
            "ul_throughput": 12_000_000,
            "responsiveness": 600,
            "base_rtt": 15.5,
            "ul_responsiveness": 400,
            "interface_name": "en0",
            "start_date": "2026-01-01T12:00:00Z",
            "end_date": "2026-01-01T12:01:00Z",
        },
    }
    m = sc.extract_metrics(data)
    assert m["dl_mbps"] == pytest.approx(48.0)
    assert m["ul_mbps"] == pytest.approx(12.0)
    assert m["responsiveness_rpm"] == pytest.approx(600.0)
    assert m["base_rtt_ms"] == pytest.approx(15.5)
    assert m["ul_responsiveness_rpm"] == pytest.approx(400.0)
    assert m["interface_name"] == "en0"
    assert m["start_date"] == "2026-01-01T12:00:00Z"
    assert m["end_date"] == "2026-01-01T12:01:00Z"


def test_extract_metrics_upload_responsiveness_alias() -> None:
    data = {
        "ok": True,
        "json": {"upload_responsiveness": 111, "interface": "bridge0"},
    }
    m = sc.extract_metrics(data)
    assert m["ul_responsiveness_rpm"] == pytest.approx(111.0)
    assert m["interface_name"] == "bridge0"


def test_extract_metrics_not_ok() -> None:
    m = sc.extract_metrics({"ok": False, "json": None})
    assert m["dl_mbps"] is None
    assert m["interface_name"] is None


def test_extract_metrics_string_throughput_ignored() -> None:
    m = sc.extract_metrics({"ok": True, "json": {"dl_throughput": "fast", "ul_throughput": None}})
    assert m["dl_mbps"] is None
    assert m["ul_mbps"] is None


def test_extract_metrics_empty_interface_is_none() -> None:
    m = sc.extract_metrics({"ok": True, "json": {"interface_name": "   "}})
    assert m["interface_name"] is None


def test_extract_metrics_json_not_dict_returns_all_none() -> None:
    m = sc.extract_metrics({"ok": True, "json": "not a dict"})
    assert all(v is None for v in m.values())


def test_extract_metrics_missing_ok_returns_all_none() -> None:
    m = sc.extract_metrics({"json": {"dl_throughput": 100_000_000}})
    assert m["dl_mbps"] is None


def test_clamp_max_runtime_boundaries() -> None:
    from collectors.speed_collector import _clamp_max_runtime
    assert _clamp_max_runtime(5) == 20
    assert _clamp_max_runtime(200) == 90
    assert _clamp_max_runtime(20) == 20
    assert _clamp_max_runtime(90) == 90
    assert _clamp_max_runtime(45) == 45


def test_run_network_quality_appends_M_and_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Any] = []

    def fake_which(_: str) -> str:
        return "/usr/bin/networkQuality"

    def fake_run_text(args: List[str], *, timeout: float) -> Any:
        calls.append({"args": list(args), "timeout": timeout})

        class P:
            stdout = "{}"

        return P()

    monkeypatch.setattr(sc.shutil, "which", fake_which)
    monkeypatch.setattr(sc, "run_text", fake_run_text)

    sc.run_network_quality(max_runtime_sec=None)
    assert calls[-1]["args"] == ["networkQuality", "-c"]
    assert calls[-1]["timeout"] == 120.0

    sc.run_network_quality(max_runtime_sec=45)
    assert calls[-1]["args"] == ["networkQuality", "-c", "-M", "45"]

    sc.run_network_quality(max_runtime_sec=5)
    assert calls[-1]["args"] == ["networkQuality", "-c", "-M", "20"]

    sc.run_network_quality(max_runtime_sec=200)
    assert calls[-1]["args"] == ["networkQuality", "-c", "-M", "90"]

"""Tests for small collector utilities: wifi sort, traceroute parsing, location helper."""

from __future__ import annotations

from collectors.location_helper import request_when_in_use
from collectors.traceroute_collector import nonblank_traceroute_lines
from collectors.wifi_collector import sort_networks_by_rssi

# ── WiFi sort ─────────────────────────────────────────────────────────

def test_sort_networks_by_rssi_strongest_first() -> None:
    nets = [
        {"ssid": "weak", "rssi_dbm": -80},
        {"ssid": "strong", "rssi_dbm": -40},
        {"ssid": "mid", "rssi_dbm": -60},
    ]
    ordered = sort_networks_by_rssi(nets)
    assert [n["ssid"] for n in ordered] == ["strong", "mid", "weak"]


def test_sort_networks_missing_rssi_sorts_last() -> None:
    nets = [{"ssid": "unknown"}, {"ssid": "a", "rssi_dbm": -70}]
    ordered = sort_networks_by_rssi(nets)
    assert ordered[0]["ssid"] == "a"
    assert ordered[1]["ssid"] == "unknown"


def test_sort_networks_empty_list() -> None:
    assert sort_networks_by_rssi([]) == []


# ── Traceroute parsing ────────────────────────────────────────────────

def test_nonblank_lines_skips_empty_and_whitespace_only() -> None:
    raw = "line one\n\n  \nline two\t\n"
    assert nonblank_traceroute_lines(raw) == ["line one", "line two"]


def test_nonblank_lines_strips_trailing_whitespace() -> None:
    assert nonblank_traceroute_lines("hop 1   \nhop 2") == ["hop 1", "hop 2"]


def test_nonblank_lines_empty_input() -> None:
    assert nonblank_traceroute_lines("") == []
    assert nonblank_traceroute_lines("   \n\n") == []


# ── Location helper ───────────────────────────────────────────────────

def test_request_when_in_use_no_raise() -> None:
    request_when_in_use()

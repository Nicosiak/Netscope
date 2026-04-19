"""Tests for small collector utilities: wifi sort, traceroute parsing."""

from __future__ import annotations

import pytest

from collectors import traceroute_collector as traceroute_mod
from collectors.traceroute_collector import (
    _PROBE_COUNT,
    _traceroute_meta,
    enrich_hops_network,
    enrich_hops_row_delta,
    nonblank_traceroute_lines,
    parse_cymru_txt,
    parse_traceroute_header,
    parse_traceroute_hop_line,
    parse_traceroute_hops,
)
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


def test_parse_hop_line_numeric_ip() -> None:
    row = parse_traceroute_hop_line(" 1  192.168.1.1  4.567 ms")
    assert row["ttl"] == 1
    assert row["host"] == "192.168.1.1"
    assert row["ip"] == "192.168.1.1"
    assert row["hostname"] is None
    assert row["rtt_ms"] == 4.567
    assert row["probe_reply_count"] == 1
    assert row["line"] == "1  192.168.1.1  4.567 ms"


def test_parse_hop_line_name_in_parens() -> None:
    row = parse_traceroute_hop_line(" 7  rtr.example.com (72.68.121.1)  10.5 ms")
    assert row["ttl"] == 7
    assert row["ip"] == "72.68.121.1"
    assert row["hostname"] == "rtr.example.com"
    assert row["rtt_ms"] == 10.5
    assert row["probe_reply_count"] == 1


def test_parse_hop_line_multiple_probes_uses_first_ms() -> None:
    row = parse_traceroute_hop_line(" 2  10.0.0.1  12.0 ms  11.0 ms  13.0 ms")
    assert row["ttl"] == 2
    assert row["host"] == "10.0.0.1"
    assert row["rtt_ms"] == 12.0
    assert row["probe_reply_count"] == 3


def test_parse_hop_line_stars_no_rtt() -> None:
    row = parse_traceroute_hop_line(" 3  * * *")
    assert row["ttl"] == 3
    assert row["host"] == "* * *"
    assert row["ip"] is None
    assert row["hostname"] is None
    assert row["rtt_ms"] is None
    assert row["probe_reply_count"] == 0


def test_parse_hop_line_lt_one_ms() -> None:
    row = parse_traceroute_hop_line(" 1  192.168.1.1  <1 ms")
    assert row["rtt_ms"] == 1.0
    assert row["probe_reply_count"] == 1
    assert row["host"] == "192.168.1.1"


def test_parse_hop_line_skips_header() -> None:
    assert parse_traceroute_hop_line("traceroute to 8.8.8.8 (8.8.8.8), 64 hops max") is None


def test_parse_traceroute_hops_full_sample() -> None:
    lines = [
        "traceroute to 8.8.8.8 (8.8.8.8), 64 hops max, 40 byte packets",
        " 1  192.168.1.1  2.000 ms",
        " 2  * * *",
        " 3  8.8.8.8  10.500 ms",
    ]
    hops = parse_traceroute_hops(lines)
    assert len(hops) == 3
    assert hops[0]["rtt_ms"] == 2.0
    assert hops[0]["probe_reply_count"] == 1
    assert hops[1]["rtt_ms"] is None
    assert hops[1]["probe_reply_count"] == 0
    assert hops[2]["host"] == "8.8.8.8"
    assert hops[2]["probe_reply_count"] == 1


def test_traceroute_meta_probe_loss_matches_probe_counts() -> None:
    lines = [
        "traceroute to 8.8.8.8 (8.8.8.8), 64 hops max, 40 byte packets",
        " 1  192.168.1.1  2.000 ms",
        " 2  * * *",
        " 3  8.8.8.8  10.500 ms",
    ]
    raw = "\n".join(lines)
    hops = enrich_hops_row_delta(parse_traceroute_hops(lines))
    meta = _traceroute_meta("8.8.8.8", raw, hops, 0.0)
    assert meta["probes_sent"] == 3 * _PROBE_COUNT
    assert meta["probes_replied"] == 2
    # 9 probes, 7 no-reply -> round(100 * 7/9, 1) == 77.8
    assert meta["packet_loss_pct"] == pytest.approx(round(700.0 / 9.0, 1))
    assert meta["probe_count_per_hop"] == _PROBE_COUNT


def test_parse_traceroute_header_line() -> None:
    line = "traceroute to 8.8.8.8 (8.8.8.8), 64 hops max, 52 byte packets"
    h = parse_traceroute_header(line)
    assert h is not None
    assert h["query"] == "8.8.8.8"
    assert h["resolved"] == "8.8.8.8"
    assert h["max_hops_cli"] == "64"
    assert h["packet_bytes"] == "52"


def test_enrich_hops_row_delta_consecutive() -> None:
    hops = [
        {"ttl": 1, "host": "a", "rtt_ms": 5.0},
        {"ttl": 2, "host": "*", "rtt_ms": None},
        {"ttl": 3, "host": "b", "rtt_ms": 15.0},
    ]
    e = enrich_hops_row_delta(hops)
    assert e[0]["delta_row_ms"] is None
    assert e[1]["delta_row_ms"] is None
    assert e[2]["delta_row_ms"] is None


def test_enrich_hops_row_delta_two_replies() -> None:
    hops = [
        {"ttl": 1, "rtt_ms": 5.0},
        {"ttl": 2, "rtt_ms": 12.0},
    ]
    e = enrich_hops_row_delta(hops)
    assert e[0]["delta_row_ms"] is None
    assert e[1]["delta_row_ms"] == 7.0


def test_parse_cymru_txt() -> None:
    asn, org = parse_cymru_txt('"7922 | 73.0.0.0/8 | US | arin |"')
    assert asn == "AS7922"
    assert "73.0.0.0" in org or org == "73.0.0.0/8"


def test_enrich_hops_network_segment_lan_and_dest_cloud(monkeypatch) -> None:
    monkeypatch.setattr(traceroute_mod, "_cymru_txt_for_ipv4", lambda ip: "")
    monkeypatch.setattr(traceroute_mod, "_dig_ptr", lambda ip, timeout=1.8: "")
    hops = [
        {"ttl": 1, "ip": "192.168.1.1", "rtt_ms": 2.0, "hostname": None},
        {"ttl": 2, "ip": "9.9.9.9", "rtt_ms": 20.0, "hostname": None},
    ]
    enrich_hops_network(hops, "9.9.9.9", budget_s=0.5)
    assert hops[0]["segment"] == "lan"
    assert hops[1]["segment"] == "cloud"


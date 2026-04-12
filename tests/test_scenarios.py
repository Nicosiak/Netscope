"""
Scenario matrix — cross-checks analysis, sanitization, alerts, and ping stats.

Pure Python (no GUI, no live CoreWLAN). Use this to compare “internal” results
across synthetic payloads and catch drift between modules.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

import pytest

from analysis.recommendations import recommend_from_connection, recommend_from_scan
from analysis.thresholds import SignalQuality, classify_rssi
from collectors.ping_collector import stats_from_rtt_history
from core.alerts import DEFAULT_RULES, AlertEngine, AlertLevel, AlertRule
from core.sanitize import (
    PING_STALE_S,
    WIFI_STALE_S,
    sanitize_ping,
    sanitize_wifi,
)


def _alert_level(
    engine: AlertEngine,
    rssi: Optional[float] = None,
    ping_ms: Optional[float] = None,
    loss_pct: Optional[float] = None,
) -> AlertLevel:
    return engine.evaluate(rssi=rssi, ping_ms=ping_ms, loss_pct=loss_pct).level


class TestAlertEngineScenarios:
    """Single-metric and combined-metric scenarios; worst level wins."""

    @pytest.fixture
    def engine(self) -> AlertEngine:
        return AlertEngine(rules=list(DEFAULT_RULES))

    @pytest.mark.parametrize(
        "rssi,expected",
        [
            (-50, AlertLevel.OK),
            (-71, AlertLevel.WARNING),
            (-75, AlertLevel.WARNING),
            (-81, AlertLevel.CRITICAL),
            (-100, AlertLevel.CRITICAL),
        ],
    )
    def test_rssi_only(self, engine: AlertEngine, rssi: int, expected: AlertLevel) -> None:
        assert _alert_level(engine, rssi=float(rssi)) == expected

    @pytest.mark.parametrize(
        "ping_ms,expected",
        [
            (10.0, AlertLevel.OK),
            (79.0, AlertLevel.OK),
            (81.0, AlertLevel.WARNING),
            (151.0, AlertLevel.CRITICAL),
        ],
    )
    def test_ping_only(self, engine: AlertEngine, ping_ms: float, expected: AlertLevel) -> None:
        assert _alert_level(engine, ping_ms=ping_ms) == expected

    @pytest.mark.parametrize(
        "loss,expected",
        [
            (0.0, AlertLevel.OK),
            (1.1, AlertLevel.WARNING),
            (5.1, AlertLevel.CRITICAL),
        ],
    )
    def test_loss_only(self, engine: AlertEngine, loss: float, expected: AlertLevel) -> None:
        assert _alert_level(engine, loss_pct=loss) == expected

    def test_worst_metric_wins(self, engine: AlertEngine) -> None:
        # RSSI OK, ping critical -> CRITICAL
        assert _alert_level(engine, rssi=-50.0, ping_ms=200.0, loss_pct=0.0) == AlertLevel.CRITICAL
        # All trigger -> CRITICAL
        assert _alert_level(engine, rssi=-90.0, ping_ms=200.0, loss_pct=10.0) == AlertLevel.CRITICAL

    def test_none_metrics_never_fire(self, engine: AlertEngine) -> None:
        assert _alert_level(engine, rssi=None, ping_ms=None, loss_pct=None) == AlertLevel.OK

    def test_custom_rules_order(self) -> None:
        rules: List[AlertRule] = [
            AlertRule("ping_ms", ">", 10.0, AlertLevel.WARNING, "w"),
            AlertRule("ping_ms", ">", 100.0, AlertLevel.CRITICAL, "c"),
        ]
        eng = AlertEngine(rules=rules)
        st = eng.evaluate(ping_ms=150.0)
        assert st.level == AlertLevel.CRITICAL
        assert "c" in st.messages


class TestSanitizeWifiScenarios:
    def test_stale_flag_uses_ts_age(self) -> None:
        now = time.time()
        fresh = sanitize_wifi({"rssi_dbm": -65, "ssid": "X"}, ts=now - 1.0)
        assert fresh["_stale"] is False
        old = sanitize_wifi({"rssi_dbm": -65, "ssid": "X"}, ts=now - (WIFI_STALE_S + 1.0))
        assert old["_stale"] is True

    def test_invalid_rssi_becomes_none(self) -> None:
        c = sanitize_wifi({"rssi_dbm": -200, "ssid": "A"}, ts=time.time())
        assert c["rssi_dbm"] is None
        assert c["_valid"] is True  # ssid present

    def test_error_preserved(self) -> None:
        c = sanitize_wifi({"error": "No Wi-Fi interface"}, ts=time.time())
        assert c.get("error") == "No Wi-Fi interface"


class TestSanitizePingScenarios:
    def test_stale_when_ts_old(self) -> None:
        now = time.time()
        p = sanitize_ping({"rtt_ms": 12.0, "ts": now - (PING_STALE_S + 0.5)})
        assert p["_stale"] is True

    def test_loss_clamped(self) -> None:
        p = sanitize_ping({"loss_pct": 999.0, "ts": time.time()})
        assert p["loss_pct"] == 100.0
        p2 = sanitize_ping({"loss_pct": -5.0, "ts": time.time()})
        assert p2["loss_pct"] == 0.0

    def test_history_sanitized(self) -> None:
        p = sanitize_ping({"history_ms": [10.0, None, 99999.0], "ts": time.time()})
        assert p["history_ms"][0] == 10.0
        assert p["history_ms"][1] is None
        assert p["history_ms"][2] is None  # out of range


class TestRecommendationsVsThresholds:
    """Recommendations should align with classify_rssi buckets for obvious cases."""

    @pytest.mark.parametrize(
        "rssi,expected_quality",
        [
            (-45, SignalQuality.EXCELLENT),
            (-68, SignalQuality.GOOD),
            (-72, SignalQuality.FAIR),
            (-82, SignalQuality.POOR),
        ],
    )
    def test_connection_tips_match_bucket(self, rssi: int, expected_quality: SignalQuality) -> None:
        assert classify_rssi(rssi) == expected_quality
        tips = recommend_from_connection(
            {"rssi_dbm": rssi, "ssid": "Net", "noise_dbm": -92, "tx_rate_mbps": 200.0}
        )
        text = " ".join(tips).lower()
        if expected_quality == SignalQuality.POOR:
            assert "weak" in text or "move closer" in text
        elif expected_quality in (SignalQuality.EXCELLENT, SignalQuality.GOOD):
            assert "healthy" in text or "usable" in text or "marginal" in text


class TestScanRecommendationScenarios:
    def test_crowded_channel_threshold(self) -> None:
        rows = [{"channel": 11, "band": "2.4 GHz", "ssid": f"n{i}"} for i in range(4)]
        tips = recommend_from_scan(rows, my_channel=11)
        assert any("busy" in t.lower() for t in tips)

    def test_no_tips_without_channel(self) -> None:
        assert recommend_from_scan([{"channel": 6}], my_channel=None) == []


class TestPingStatsScenarios:
    @pytest.mark.parametrize(
        "hist,expected_loss",
        [
            ([10.0, 20.0, 30.0], 0.0),
            ([10.0, None, None], pytest.approx(100.0 * 2.0 / 3.0)),
        ],
    )
    def test_loss_percent(self, hist: List[Optional[float]], expected_loss: Any) -> None:
        s = stats_from_rtt_history(hist)
        assert s["loss_pct"] == expected_loss


def test_default_rules_cover_all_metrics() -> None:
    metrics = {r.metric for r in DEFAULT_RULES}
    assert metrics == {"rssi", "ping_ms", "loss_pct"}

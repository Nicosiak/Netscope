"""Alert engine — evaluates metrics against thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

# Hex color constants (inlined from former ui/theme.py — no Tk dependency)
_COLOR_ALERT_OK       = "#22c55e"
_COLOR_ALERT_WARNING  = "#f59e0b"
_COLOR_ALERT_CRITICAL = "#ef4444"


class AlertLevel(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertState:
    level: AlertLevel = AlertLevel.OK
    messages: List[str] = field(default_factory=list)

    @property
    def color_hex(self) -> str:
        return {
            AlertLevel.OK: _COLOR_ALERT_OK,
            AlertLevel.WARNING: _COLOR_ALERT_WARNING,
            AlertLevel.CRITICAL: _COLOR_ALERT_CRITICAL,
        }[self.level]


@dataclass
class AlertRule:
    metric: str
    op: str
    threshold: float
    level: AlertLevel
    message: str

    def evaluate(self, value: Optional[float]) -> bool:
        if value is None:
            return False
        if self.op == "<":
            return value < self.threshold
        if self.op == ">":
            return value > self.threshold
        return False


DEFAULT_RULES: List[AlertRule] = [
    AlertRule(
        "rssi",
        "<",
        -80,
        AlertLevel.CRITICAL,
        "Very weak RSSI (below about −80 dBm) — coverage or placement issue",
    ),
    AlertRule(
        "rssi",
        "<",
        -70,
        AlertLevel.WARNING,
        "RSSI below about −70 dBm — below a common UniFi/Ekahau-style stable target",
    ),
    AlertRule("ping_ms", ">", 150, AlertLevel.CRITICAL, "Very high latency — possible ISP issue"),
    AlertRule("ping_ms", ">", 80, AlertLevel.WARNING, "Elevated latency"),
    AlertRule("loss_pct", ">", 5, AlertLevel.CRITICAL, "High packet loss — unstable connection"),
    AlertRule("loss_pct", ">", 1, AlertLevel.WARNING, "Packet loss detected"),
]


class AlertEngine:
    def __init__(self, rules: Optional[List[AlertRule]] = None) -> None:
        self.rules = rules if rules is not None else list(DEFAULT_RULES)
        self._callbacks: List[Callable[[AlertState], None]] = []

    def subscribe(self, cb: Callable[[AlertState], None]) -> None:
        self._callbacks.append(cb)

    def evaluate(
        self,
        rssi: Optional[float] = None,
        ping_ms: Optional[float] = None,
        loss_pct: Optional[float] = None,
    ) -> AlertState:
        values = {"rssi": rssi, "ping_ms": ping_ms, "loss_pct": loss_pct}
        state = AlertState()
        worst = AlertLevel.OK

        for rule in self.rules:
            val = values.get(rule.metric)
            if rule.evaluate(val):
                state.messages.append(rule.message)
                if rule.level == AlertLevel.CRITICAL:
                    worst = AlertLevel.CRITICAL
                elif rule.level == AlertLevel.WARNING and worst == AlertLevel.OK:
                    worst = AlertLevel.WARNING

        state.level = worst
        for cb in self._callbacks:
            try:
                cb(state)
            except Exception:
                pass
        return state


alert_engine = AlertEngine()

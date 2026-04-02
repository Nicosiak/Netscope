"""Main application window — WiFiman-inspired dark theme."""

from __future__ import annotations

from typing import Any, Callable, Dict

import customtkinter as ctk

from collectors.location_helper import request_when_in_use
from collectors.ping_collector import PingSampler
from collectors.wifi_collector import WiFiPoller
from ui import theme
from ui.tabs.diagnostics_tab import DiagnosticsTab
from ui.tabs.ping_tab import PingTab
from ui.tabs.wifi_tab import WiFiTab


class NetScopeApp:
    _sb_cache: Dict[str, str] = {}

    def __init__(self) -> None:
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        request_when_in_use()

        self.root = ctk.CTk()
        self.root.title("NetScope")
        self.root.geometry("1160x880")
        self.root.minsize(900, 640)
        self.root.configure(fg_color=theme.BG_PRIMARY)

        self._build_status_bar()

        self.tabview = ctk.CTkTabview(
            self.root,
            anchor="w",
            fg_color=theme.BG_PRIMARY,
            segmented_button_fg_color=theme.BG_CARD,
            segmented_button_selected_color=theme.ACCENT_DIM,
            segmented_button_selected_hover_color=theme.ACCENT,
            segmented_button_unselected_color=theme.BG_CARD,
            segmented_button_unselected_hover_color=theme.BG_CARD_HOVER,
            text_color=theme.FG_PRIMARY,
        )
        self.tabview.pack(fill="both", expand=True, padx=0, pady=0)

        wifi_frame = self.tabview.add("  Signal  ")
        ping_frame = self.tabview.add("  Ping  ")
        diag_frame = self.tabview.add("  Diagnostics  ")

        queue_fn: Callable[[Callable[[], None]], None] = lambda f: self.root.after(0, f)

        self.wifi_tab = WiFiTab(wifi_frame)
        self.ping_tab = PingTab(ping_frame)
        self.diag_tab = DiagnosticsTab(diag_frame)
        self.diag_tab.set_queue_fn(queue_fn)

        self.wifi_poller = WiFiPoller(interval_s=2.0, queue_fn=queue_fn)
        self.wifi_poller.on_data = self._on_wifi_data
        self.wifi_poller.start()

        self.ping_sampler = PingSampler(target="8.8.8.8", interval_s=1.0, history_max=60, queue_fn=queue_fn)
        self.ping_sampler.on_sample = self._on_ping_sample

        def on_target(host: str) -> None:
            self.ping_sampler.stop()
            self.ping_sampler.set_target(host)
            self.ping_sampler.reset_history()
            self.ping_sampler.start()

        self.ping_tab.bind_target_change(on_target)
        self.ping_sampler.start()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self.root, height=32, corner_radius=0, fg_color=theme.BG_CARD, border_width=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=16, expand=True)

        self._sb_ssid = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=11), text_color=theme.FG_SECONDARY)
        self._sb_ssid.pack(side="left", padx=(0, 20))
        self._sb_rssi = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=11), text_color=theme.FG_SECONDARY)
        self._sb_rssi.pack(side="left", padx=(0, 20))
        self._sb_ch = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=11), text_color=theme.FG_SECONDARY)
        self._sb_ch.pack(side="left", padx=(0, 20))
        self._sb_ping = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=11), text_color=theme.FG_SECONDARY)
        self._sb_ping.pack(side="left", padx=(0, 20))
        self._sb_loss = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=11), text_color=theme.FG_SECONDARY)
        self._sb_loss.pack(side="right")

    def _sb_set(self, lbl: ctk.CTkLabel, key: str, text: str, text_color: str) -> None:
        """Only reconfigure a status bar label if its value actually changed."""
        cache_key = f"{key}_{text}_{text_color}"
        if self._sb_cache.get(key) == cache_key:
            return
        self._sb_cache[key] = cache_key
        lbl.configure(text=text, text_color=text_color)

    def _on_wifi_data(self, data: Dict[str, Any]) -> None:
        self.wifi_tab.on_wifi_data(data)
        conn = data.get("connection") or {}
        ssid = conn.get("ssid") or "—"
        rssi = conn.get("rssi_dbm")
        ch = conn.get("channel")
        band = conn.get("band") or ""

        self._sb_set(self._sb_ssid, "ssid", ssid, theme.FG_SECONDARY)
        if rssi is not None:
            from analysis.thresholds import classify_rssi, rssi_color_hex
            q = classify_rssi(rssi)
            self._sb_set(self._sb_rssi, "rssi", f"{rssi} dBm", rssi_color_hex(q))
        else:
            self._sb_set(self._sb_rssi, "rssi", "— dBm", theme.FG_MUTED)
        self._sb_set(self._sb_ch, "ch", f"Ch {ch or '—'} {band}", theme.FG_SECONDARY)

    def _on_ping_sample(self, payload: Dict[str, Any]) -> None:
        self.ping_tab.on_ping_sample(payload)
        rtt = payload.get("rtt_ms")
        lp = payload.get("loss_pct")
        if rtt is not None:
            from analysis.thresholds import classify_ping_ms
            _, col = classify_ping_ms(rtt)
            self._sb_set(self._sb_ping, "ping", f"{rtt:.0f} ms", col)
        else:
            self._sb_set(self._sb_ping, "ping", "timeout", theme.COLOR_POOR)
        if isinstance(lp, (int, float)) and lp > 0.5:
            self._sb_set(self._sb_loss, "loss", f"Loss {lp:.1f}%", theme.COLOR_POOR)
        else:
            self._sb_set(self._sb_loss, "loss", "Loss 0%", theme.FG_MUTED)

    def _on_close(self) -> None:
        try:
            self.wifi_poller.stop()
        except Exception:
            pass
        try:
            self.ping_sampler.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

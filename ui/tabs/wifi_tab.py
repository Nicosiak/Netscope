"""WiFi tab — grouped sections with clear visual hierarchy."""

from __future__ import annotations

import csv
import time
from collections import Counter, deque
from tkinter import filedialog
from typing import Any, Deque, Dict, List, Optional, Tuple

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from analysis import recommendations, thresholds
from ui import theme

_CARD = dict(fg_color=theme.BG_CARD, corner_radius=10, border_width=1, border_color=theme.BORDER)
_PAD = 16


def _section_label(parent: Any, text: str) -> None:
    """Dim uppercase section header with a divider line above it."""
    ctk.CTkFrame(parent, fg_color=theme.DIVIDER, height=1).pack(fill="x", padx=_PAD, pady=(14, 0))
    ctk.CTkLabel(parent, text=text.upper(), font=ctk.CTkFont(size=10, weight="bold"),
                 text_color=theme.FG_MUTED).pack(anchor="w", padx=_PAD + 4, pady=(6, 4))


class WiFiTab:
    def __init__(self, master: Any) -> None:
        self.master = master
        self._rssi_history: Deque[Tuple[float, Optional[int]]] = deque(maxlen=120)
        self._net_widgets: List[ctk.CTkFrame] = []
        self._last_nets: List[Dict[str, Any]] = []
        self._prev_ch_key: str = ""

        outer = ctk.CTkScrollableFrame(master, fg_color=theme.BG_PRIMARY)
        outer.pack(fill="both", expand=True)
        self._outer = outer

        # ── Section 1: Connection Overview ────────────────────────────
        _section_label(outer, "Connection")

        self._build_phy_bar(outer)

        mid = ctk.CTkFrame(outer, fg_color="transparent")
        mid.pack(fill="x", padx=_PAD, pady=(6, 0))
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=2)
        self._build_rssi_chart(mid)
        self._build_ap_card(mid)

        # ── Section 2: WiFi Quality ──────────────────────────────────
        _section_label(outer, "WiFi Quality")

        self._build_speed_factors(outer)
        self._build_tips(outer)

        # ── Section 3: Spectrum ──────────────────────────────────────
        _section_label(outer, "Spectrum")

        self._build_channel_chart(outer)

        # ── Section 4: Nearby Networks ───────────────────────────────
        _section_label(outer, "Scan Results")

        self._build_network_table(outer)

        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.pack(fill="x", padx=_PAD, pady=(2, 16))
        ctk.CTkButton(btn_row, text="Export CSV", width=100, height=26, command=self._export_csv,
                       font=ctk.CTkFont(size=10), fg_color=theme.BG_CARD, hover_color=theme.BG_CARD_HOVER,
                       border_width=1, border_color=theme.BORDER, text_color=theme.FG_MUTED
                       ).pack(side="right")

    # ── PHY summary bar ──────────────────────────────────────────────

    def _build_phy_bar(self, parent: Any) -> None:
        bar = ctk.CTkFrame(parent, **_CARD)
        bar.pack(fill="x", padx=_PAD, pady=(0, 4))

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=10)
        for col in range(5):
            inner.columnconfigure(col, weight=1)

        self._phy_labels: Dict[str, ctk.CTkLabel] = {}
        for i, (key, label) in enumerate([("signal", "Signal"), ("phy", "PHY Mode"), ("band", "Band"), ("ch_width", "Width"), ("rate", "PHY Speed")]):
            ctk.CTkLabel(inner, text=label, font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED).grid(row=0, column=i, padx=6, sticky="w")
            val = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=14, weight="bold"), text_color=theme.FG_PRIMARY)
            val.grid(row=1, column=i, padx=6, sticky="w")
            self._phy_labels[key] = val

    # ── RSSI chart ───────────────────────────────────────────────────

    def _build_rssi_chart(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, **_CARD)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        ctk.CTkLabel(card, text="Signal Strength", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=theme.FG_SECONDARY).pack(anchor="w", padx=12, pady=(8, 0))

        self._fig = Figure(figsize=(5, 2.0), dpi=100)
        self._ax = self._fig.add_subplot(111)
        self._line, = self._ax.plot([], [], color=theme.CHART_LINE, linewidth=2, solid_capstyle="round")
        self._ax.set_ylim(-95, -15)
        self._ax.set_xlim(60, 0)
        self._ax.set_ylabel("dBm", fontsize=9)
        theme.style_figure(self._fig)

        self._canvas = FigureCanvasTkAgg(self._fig, master=card)
        self._canvas.get_tk_widget().configure(bg=theme.CHART_BG, highlightthickness=0)
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _refresh_chart(self) -> None:
        now = time.time()
        pts = [(t, r) for (t, r) in self._rssi_history if t >= now - 60 and r is not None]
        pts.sort(key=lambda x: x[0])
        if pts:
            self._line.set_data([now - t for t, _ in pts], [r for _, r in pts])
        else:
            self._line.set_data([], [])
        self._ax.set_xlim(60, 0)
        self._ax.set_ylim(-95, -15)
        self._canvas.draw_idle()

    # ── Connected AP card ────────────────────────────────────────────

    def _build_ap_card(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, **_CARD)
        card.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=12)

        ctk.CTkLabel(inner, text="Connected AP", font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED).pack(anchor="w")
        self._ap_ssid = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=15, weight="bold"), text_color=theme.FG_PRIMARY)
        self._ap_ssid.pack(anchor="w", pady=(2, 0))
        self._ap_bssid = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED)
        self._ap_bssid.pack(anchor="w", pady=(1, 8))

        self._ap_rssi = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=26, weight="bold"), text_color=theme.COLOR_POOR)
        self._ap_rssi.pack(anchor="w")
        self._ap_quality = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=11, weight="bold"), text_color=theme.FG_MUTED)
        self._ap_quality.pack(anchor="w", pady=(1, 0))

        ctk.CTkFrame(inner, fg_color=theme.DIVIDER, height=1).pack(fill="x", pady=(8, 6))

        detail = ctk.CTkFrame(inner, fg_color="transparent")
        detail.pack(fill="x")
        self._ap_snr = ctk.CTkLabel(detail, text="SNR —", font=ctk.CTkFont(size=10), text_color=theme.FG_SECONDARY)
        self._ap_snr.pack(anchor="w")
        self._ap_sec = ctk.CTkLabel(detail, text="Security —", font=ctk.CTkFont(size=10), text_color=theme.FG_SECONDARY)
        self._ap_sec.pack(anchor="w", pady=(1, 0))

    # ── WiFi Speed Factors ───────────────────────────────────────────

    def _build_speed_factors(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, **_CARD)
        card.pack(fill="x", padx=_PAD, pady=(0, 4))

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(12, 8))
        ctk.CTkLabel(hdr, text="Speed Factors", font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")
        self._sf_overall = ctk.CTkLabel(hdr, text="—", font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.FG_MUTED)
        self._sf_overall.pack(side="right")

        self._sf_labels: Dict[str, Dict[str, ctk.CTkLabel]] = {}
        for idx, (key, title) in enumerate([("spectrum", "Spectrum"), ("radio", "Radio Potential"), ("channel_health", "Channel Health")]):
            if idx > 0:
                ctk.CTkFrame(card, fg_color=theme.DIVIDER, height=1).pack(fill="x", padx=20)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=(6, 1))
            ctk.CTkLabel(row, text=title, font=ctk.CTkFont(size=12), text_color=theme.FG_PRIMARY).pack(side="left")
            status = ctk.CTkLabel(row, text="—", font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.FG_MUTED)
            status.pack(side="right")
            detail_row = ctk.CTkFrame(card, fg_color="transparent")
            detail_row.pack(fill="x", padx=20, pady=(0, 6))
            detail = ctk.CTkLabel(detail_row, text="—", font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED)
            detail.pack(anchor="w")
            self._sf_labels[key] = {"status": status, "detail": detail}

        ctk.CTkFrame(card, fg_color="transparent", height=4).pack()

    def _update_speed_factors(self, conn: Dict[str, Any], nets: List[Dict[str, Any]]) -> None:
        band = conn.get("band") or ""
        ch_width = conn.get("channel_width") or ""
        phy = conn.get("phy_mode") or ""
        rssi = conn.get("rssi_dbm")
        ch = conn.get("channel")

        if "5" in band or "6" in band:
            ss, sc = ("Excellent", theme.COLOR_EXCELLENT) if any(w in ch_width for w in ("80", "160", "320")) else ("Good", theme.COLOR_GOOD)
        elif "2.4" in band:
            ss, sc = "Fair", theme.COLOR_FAIR
        else:
            ss, sc = "—", theme.FG_MUTED
        self._sf_labels["spectrum"]["status"].configure(text=ss, text_color=sc)
        self._sf_labels["spectrum"]["detail"].configure(text=f"Band {band}   Width {ch_width}" if ch_width else f"Band {band or '—'}")

        if "ax" in phy or "be" in phy:
            rs, rc = ("Excellent", theme.COLOR_EXCELLENT) if isinstance(rssi, int) and rssi >= -67 else (("Fair", theme.COLOR_FAIR) if isinstance(rssi, int) and rssi < -75 else ("Good", theme.COLOR_GOOD))
        elif "ac" in phy:
            rs, rc = "Good", theme.COLOR_GOOD
        else:
            rs, rc = "Fair", theme.COLOR_FAIR
        if isinstance(rssi, int) and rssi < -80:
            rs, rc = "Poor", theme.COLOR_POOR
        self._sf_labels["radio"]["status"].configure(text=rs, text_color=rc)
        self._sf_labels["radio"]["detail"].configure(text=f"Standard {phy or '—'}   Signal {rssi or '—'} dBm")

        same_ch = sum(1 for n in nets if n.get("channel") == ch) if ch else 0
        cs, cc = ("Excellent", theme.COLOR_EXCELLENT) if same_ch <= 2 else (("Good", theme.COLOR_GOOD) if same_ch <= 5 else (("Fair", theme.COLOR_FAIR) if same_ch <= 8 else ("Poor", theme.COLOR_POOR)))
        self._sf_labels["channel_health"]["status"].configure(text=cs, text_color=cc)
        self._sf_labels["channel_health"]["detail"].configure(text=f"Channel {ch or '—'}   ({same_ch} APs)")

        scores = {"Excellent": 3, "Good": 2, "Fair": 1, "Poor": 0, "—": 1}
        avg = (scores.get(ss, 1) + scores.get(rs, 1) + scores.get(cs, 1)) / 3
        ov, oc = ("Excellent", theme.COLOR_EXCELLENT) if avg >= 2.5 else (("Good", theme.COLOR_GOOD) if avg >= 1.5 else (("Fair", theme.COLOR_FAIR) if avg >= 0.5 else ("Poor", theme.COLOR_POOR)))
        self._sf_overall.configure(text=ov, text_color=oc)

    # ── Recommendations ──────────────────────────────────────────────

    def _build_tips(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, **_CARD)
        card.pack(fill="x", padx=_PAD, pady=(0, 4))
        ctk.CTkLabel(card, text="Recommendations", font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.FG_PRIMARY).pack(anchor="w", padx=20, pady=(10, 0))
        self.txt_tips = ctk.CTkTextbox(card, height=50, fg_color="transparent", text_color=theme.FG_SECONDARY,
                                        font=ctk.CTkFont(size=11), wrap="word", activate_scrollbars=False)
        self.txt_tips.pack(fill="x", padx=20, pady=(4, 10))

    # ── Channel congestion (cached — only redraws when data changes) ─

    def _build_channel_chart(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, **_CARD)
        card.pack(fill="x", padx=_PAD, pady=(0, 4))

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(10, 4))
        ctk.CTkLabel(hdr, text="Channel Congestion", font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")
        self._ch_summary = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED)
        self._ch_summary.pack(side="right")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 10))
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=2)

        # 2.4 GHz panel
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(left, text="2.4 GHz", font=ctk.CTkFont(size=10, weight="bold"), text_color=theme.FG_SECONDARY).pack(anchor="w")
        self._ch_24_container = ctk.CTkFrame(left, fg_color="transparent")
        self._ch_24_container.pack(fill="x", pady=(4, 0))

        # 5 GHz panel
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(right, text="5 GHz", font=ctk.CTkFont(size=10, weight="bold"), text_color=theme.FG_SECONDARY).pack(anchor="w")
        self._ch_5_container = ctk.CTkFrame(right, fg_color="transparent")
        self._ch_5_container.pack(fill="x", pady=(4, 0))

        self._ch_24_bars: List[ctk.CTkFrame] = []
        self._ch_5_bars: List[ctk.CTkFrame] = []

    def _refresh_channel_chart(self, networks: List[Dict[str, Any]], my_channel: Optional[int]) -> None:
        ch_24: Counter[int] = Counter()
        ch_5: Counter[int] = Counter()
        for net in networks:
            c = net.get("channel")
            b = net.get("band") or ""
            if c is None:
                continue
            if b.startswith("2.4") or (1 <= c <= 14):
                ch_24[c] += 1
            elif b.startswith("5") or (32 <= c <= 177):
                ch_5[c] += 1

        cache_key = f"{sorted(ch_24.items())}|{sorted(ch_5.items())}|{my_channel}"
        if cache_key == self._prev_ch_key:
            return
        self._prev_ch_key = cache_key

        total_aps = sum(ch_24.values()) + sum(ch_5.values())
        self._ch_summary.configure(text=f"{total_aps} APs scanned")

        self._render_channel_bars(self._ch_24_container, self._ch_24_bars, ch_24, my_channel)
        self._render_channel_bars(self._ch_5_container, self._ch_5_bars, ch_5, my_channel)

    def _render_channel_bars(self, container: ctk.CTkFrame, bar_list: List[ctk.CTkFrame],
                              data: Counter[int], my_channel: Optional[int]) -> None:
        for w in bar_list:
            w.destroy()
        bar_list.clear()

        if not data:
            lbl = ctk.CTkFrame(container, fg_color="transparent")
            lbl.pack(fill="x")
            ctk.CTkLabel(lbl, text="No APs", font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED).pack(anchor="w")
            bar_list.append(lbl)
            return

        max_count = max(data.values()) if data else 1
        for ch in sorted(data.keys()):
            count = data[ch]
            is_mine = ch == my_channel
            color = theme.COLOR_EXCELLENT if is_mine else theme.ACCENT

            row = ctk.CTkFrame(container, fg_color="transparent", height=20)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            ctk.CTkLabel(row, text=str(ch), width=30, anchor="e", font=ctk.CTkFont(size=10),
                         text_color=theme.FG_PRIMARY if is_mine else theme.FG_SECONDARY).pack(side="left")

            bar_bg = ctk.CTkFrame(row, fg_color=theme.BG_CARD_HOVER, corner_radius=3, height=12)
            bar_bg.pack(side="left", fill="x", expand=True, padx=(6, 4))
            bar_bg.pack_propagate(False)

            frac = max(0.04, count / max_count)
            fill = ctk.CTkFrame(bar_bg, fg_color=color, corner_radius=3)
            fill.place(relx=0, rely=0.5, anchor="w", relwidth=frac, relheight=0.85)

            ctk.CTkLabel(row, text=str(count), width=20, anchor="w", font=ctk.CTkFont(size=10),
                         text_color=color).pack(side="left")

            bar_list.append(row)

    # ── Nearby networks ──────────────────────────────────────────────

    def _build_network_table(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, **_CARD)
        card.pack(fill="x", padx=_PAD, pady=(0, 4))

        hdr_row = ctk.CTkFrame(card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=20, pady=(10, 6))
        ctk.CTkLabel(hdr_row, text="Nearby Networks", font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")
        self._net_count_lbl = ctk.CTkLabel(hdr_row, text="", font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED)
        self._net_count_lbl.pack(side="right")

        col_hdr = ctk.CTkFrame(card, fg_color="transparent")
        col_hdr.pack(fill="x", padx=20)
        for i, (text, w) in enumerate([("Network", 200), ("Signal", 70), ("Ch", 50), ("Band", 70), ("Security", 120)]):
            ctk.CTkLabel(col_hdr, text=text, width=w, anchor="w", font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED).grid(row=0, column=i, padx=4)

        ctk.CTkFrame(card, fg_color=theme.DIVIDER, height=1).pack(fill="x", padx=20, pady=(4, 0))

        self._net_container = ctk.CTkFrame(card, fg_color="transparent")
        self._net_container.pack(fill="x", padx=20, pady=(4, 12))

    def _render_networks(self, networks: List[Dict[str, Any]]) -> None:
        for w in self._net_widgets:
            w.destroy()
        self._net_widgets.clear()

        visible = [n for n in networks if n.get("ssid")]
        hidden_count = len(networks) - len(visible)
        self._net_count_lbl.configure(text=f"{len(visible)} visible" + (f" · {hidden_count} hidden" if hidden_count else ""))

        for idx, row in enumerate(visible[:20]):
            q = thresholds.classify_rssi(row.get("rssi_dbm"))
            color = thresholds.rssi_color_hex(q)

            bg = "transparent" if idx % 2 == 0 else theme.BG_CARD_HOVER
            fr = ctk.CTkFrame(self._net_container, fg_color=bg, corner_radius=4, height=28)
            fr.pack(fill="x", pady=1)
            fr.pack_propagate(False)

            rssi_val = row.get("rssi_dbm")
            vals = [
                (str(row.get("ssid") or "")[:28], 200, theme.FG_PRIMARY),
                (f"{rssi_val} dBm" if rssi_val is not None else "—", 70, color),
                (str(row.get("channel") or "—"), 50, theme.FG_SECONDARY),
                (str(row.get("band") or "—"), 70, theme.FG_SECONDARY),
                (str(row.get("security") or "—")[:18], 120, theme.FG_MUTED),
            ]
            for i, (txt, w, col) in enumerate(vals):
                ctk.CTkLabel(fr, text=txt, width=w, anchor="w", font=ctk.CTkFont(size=11), text_color=col).grid(row=0, column=i, padx=4)
            self._net_widgets.append(fr)

    # ── Export ───────────────────────────────────────────────────────

    def _export_csv(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["SSID", "BSSID", "RSSI (dBm)", "Channel", "Band", "Security"])
            for row in self._last_nets:
                w.writerow([row.get("ssid", ""), row.get("bssid", ""), row.get("rssi_dbm", ""),
                            row.get("channel", ""), row.get("band", ""), row.get("security", "")])

    # ── Data callback ────────────────────────────────────────────────

    def on_wifi_data(self, data: Dict[str, Any]) -> None:
        conn = data.get("connection") or {}
        nets: List[Dict[str, Any]] = data.get("networks") or []
        self._last_nets = nets

        rssi = conn.get("rssi_dbm")
        q = thresholds.classify_rssi(rssi)
        rc = thresholds.rssi_color_hex(q)

        self._phy_labels["signal"].configure(text=f"{rssi} dBm" if rssi is not None else "—", text_color=rc)
        self._phy_labels["phy"].configure(text=conn.get("phy_mode") or "—")
        band = conn.get("band") or "—"
        ch_w = conn.get("channel_width") or ""
        self._phy_labels["band"].configure(text=f"{band}" + (f" ({ch_w})" if ch_w else ""))
        self._phy_labels["ch_width"].configure(text=ch_w or "—")
        rate = conn.get("tx_rate_mbps")
        self._phy_labels["rate"].configure(
            text=f"↓{rate:.0f} Mbps" if isinstance(rate, (int, float)) else "—",
            text_color=theme.COLOR_DOWNLOAD if isinstance(rate, (int, float)) else theme.FG_PRIMARY,
        )

        ssid = conn.get("ssid") or "—"
        self._ap_ssid.configure(text=ssid)
        self._ap_bssid.configure(text=conn.get("bssid") or "—")
        self._ap_rssi.configure(text=f"{rssi} dBm" if rssi is not None else "—", text_color=rc)
        self._ap_quality.configure(text=q.value, text_color=rc)

        noise = conn.get("noise_dbm")
        if isinstance(rssi, int) and isinstance(noise, int):
            self._ap_snr.configure(text=f"SNR {rssi - noise} dB")
        else:
            self._ap_snr.configure(text="SNR —")
        self._ap_sec.configure(text=conn.get("security") or "—")

        now = data.get("ts") or time.time()
        self._rssi_history.append((now, rssi if isinstance(rssi, int) else None))
        self._refresh_chart()

        ch = conn.get("channel")
        self._update_speed_factors(conn, nets)
        self._refresh_channel_chart(nets, ch if isinstance(ch, int) else None)

        tips = recommendations.recommend_from_connection(conn) + recommendations.recommend_from_scan(nets, ch if isinstance(ch, int) else None)
        self.txt_tips.configure(state="normal")
        self.txt_tips.delete("1.0", "end")
        self.txt_tips.insert("1.0", "\n".join(f"• {t}" for t in tips))
        self.txt_tips.configure(state="disabled")

        self._render_networks(nets)

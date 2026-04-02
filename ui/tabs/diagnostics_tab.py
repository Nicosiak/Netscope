"""Diagnostics: DNS comparison, speed test, traceroute, interface info."""

from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from collectors import (
    dns_collector,
    interface_collector,
    iperf_collector,
    speed_collector,
    traceroute_collector,
)
from ui import theme


class DiagnosticsTab:
    def __init__(self, master: Any) -> None:
        self.master = master
        self._queue: Optional[Callable[[Callable[[], None]], None]] = None

        outer = ctk.CTkScrollableFrame(master, fg_color=theme.BG_PRIMARY)
        outer.pack(fill="both", expand=True)

        self._build_dns_card(outer)
        self._build_speed_card(outer)
        self._build_iperf_card(outer)
        self._build_trace_card(outer)
        self._build_iface_card(outer)

        self._load_interfaces()

    def set_queue_fn(self, queue_fn: Callable[[Callable[[], None]], None]) -> None:
        self._queue = queue_fn

    def _safe_ui(self, fn: Callable[[], None]) -> None:
        if self._queue:
            self._queue(fn)
        else:
            fn()

    # ── DNS with comparison chart ────────────────────────────────────

    def _build_dns_card(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color=theme.BG_CARD, border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", padx=16, pady=(16, 4))

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(hdr, text="DNS Lookup Comparison", font=ctk.CTkFont(size=13, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")
        self.btn_dns = ctk.CTkButton(hdr, text="Run Test", width=90, command=self._run_dns, font=ctk.CTkFont(size=11),
                                      fg_color=theme.ACCENT_DIM, hover_color=theme.ACCENT)
        self.btn_dns.pack(side="right")

        self._dns_fig = Figure(figsize=(5, 1.6), dpi=100)
        self._dns_ax = self._dns_fig.add_subplot(111)
        self._dns_ax.set_xlabel("Query time (ms)", fontsize=9)
        theme.style_figure(self._dns_fig)
        self._dns_canvas = FigureCanvasTkAgg(self._dns_fig, master=card)
        self._dns_canvas.get_tk_widget().configure(bg=theme.CHART_BG)
        self._dns_canvas.get_tk_widget().pack(fill="x", padx=16, pady=(0, 4))

        self.txt_dns = ctk.CTkTextbox(card, height=100, fg_color="transparent", text_color=theme.FG_SECONDARY, font=ctk.CTkFont(family="Menlo", size=11), wrap="word")
        self.txt_dns.pack(fill="x", padx=16, pady=(0, 12))
        self.txt_dns.insert("1.0", "Press 'Run Test' to compare DNS servers…")
        self.txt_dns.configure(state="disabled")

    def _run_dns(self) -> None:
        self.btn_dns.configure(state="disabled", text="Running…")
        self._set_textbox(self.txt_dns, "Querying 4 DNS servers…")

        def work() -> None:
            results = dns_collector.compare_servers("google.com")

            def apply() -> None:
                self._dns_ax.clear()
                labels = []
                times = []
                colors = []
                for r in results:
                    lbl = r.get("label", "?")
                    qt = r.get("query_time_ms")
                    labels.append(lbl)
                    times.append(qt if qt is not None else 0)
                    if qt is not None and qt == min(t for t in [x.get("query_time_ms") for x in results] if t is not None):
                        colors.append(theme.COLOR_EXCELLENT)
                    else:
                        colors.append(theme.ACCENT)

                y_pos = range(len(labels))
                self._dns_ax.barh(y_pos, times, color=colors, height=0.5)
                self._dns_ax.set_yticks(list(y_pos))
                self._dns_ax.set_yticklabels(labels)
                self._dns_ax.set_xlabel("Query time (ms)", fontsize=9)
                for i, t in enumerate(times):
                    if t > 0:
                        self._dns_ax.text(t + 1, i, f"{t} ms", va="center", fontsize=9, color=theme.CHART_FG)

                self._dns_ax.set_facecolor(theme.CHART_BG)
                self._dns_ax.tick_params(colors=theme.CHART_FG, labelsize=9)
                self._dns_ax.xaxis.label.set_color(theme.CHART_FG)
                for spine in self._dns_ax.spines.values():
                    spine.set_color(theme.CHART_GRID)
                self._dns_fig.tight_layout(pad=1.0)
                self._dns_canvas.draw_idle()

                lines = []
                for r in results:
                    qt = r.get("query_time_ms")
                    srv = r.get("server") or r.get("server_queried") or "—"
                    lines.append(f"{r.get('label', '?'):24s}  {qt if qt is not None else '—':>4} ms  (server: {srv})")
                self._set_textbox(self.txt_dns, "\n".join(lines))
                self.btn_dns.configure(state="normal", text="Run Test")

            self._safe_ui(apply)

        threading.Thread(target=work, daemon=True).start()

    # ── Speed ────────────────────────────────────────────────────────

    def _build_speed_card(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color=theme.BG_CARD, border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", padx=16, pady=4)

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(hdr, text="Speed Test", font=ctk.CTkFont(size=13, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")
        self.btn_speed = ctk.CTkButton(hdr, text="Run Test", width=90, command=self._run_speed, font=ctk.CTkFont(size=11),
                                        fg_color=theme.ACCENT_DIM, hover_color=theme.ACCENT)
        self.btn_speed.pack(side="right")
        if not speed_collector.network_quality_available():
            self.btn_speed.configure(state="disabled", text="Unavailable")

        self.speed_cards_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.speed_cards_frame.pack(fill="x", padx=16, pady=(0, 4))
        self._speed_labels: dict[str, ctk.CTkLabel] = {}
        for i, (key, label) in enumerate([("dl", "Download"), ("ul", "Upload"), ("rpm", "RPM"), ("latency", "Latency")]):
            self.speed_cards_frame.columnconfigure(i, weight=1)
            cell = ctk.CTkFrame(self.speed_cards_frame, corner_radius=8, fg_color=theme.BG_CARD_HOVER)
            cell.grid(row=0, column=i, padx=3, pady=4, sticky="nsew")
            ctk.CTkLabel(cell, text=label, font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED).pack(padx=6, pady=(6, 0))
            v = ctk.CTkLabel(cell, text="—", font=ctk.CTkFont(size=15, weight="bold"), text_color=theme.FG_PRIMARY)
            v.pack(padx=6, pady=(0, 6))
            self._speed_labels[key] = v

        self.txt_speed = ctk.CTkTextbox(card, height=80, fg_color="transparent", text_color=theme.FG_SECONDARY, font=ctk.CTkFont(family="Menlo", size=11), wrap="word")
        self.txt_speed.pack(fill="x", padx=16, pady=(0, 12))
        self.txt_speed.insert("1.0", "Press 'Run Test' to measure speed (uses networkQuality)…")
        self.txt_speed.configure(state="disabled")

    def _run_speed(self) -> None:
        self.btn_speed.configure(state="disabled", text="Running…")
        self._set_textbox(self.txt_speed, "Running networkQuality — this may take 15-30 s…")
        for lbl in self._speed_labels.values():
            lbl.configure(text="…")

        def work() -> None:
            data = speed_collector.run_network_quality()
            summary = speed_collector.summarize(data)
            j = data.get("json") or {}

            def apply() -> None:
                dl = j.get("dl_throughput")
                ul = j.get("ul_throughput")
                self._speed_labels["dl"].configure(text=f"{dl / 1e6:.1f} Mbps" if isinstance(dl, (int, float)) else "—")
                self._speed_labels["ul"].configure(text=f"{ul / 1e6:.1f} Mbps" if isinstance(ul, (int, float)) else "—")
                self._speed_labels["rpm"].configure(text=str(j.get("responsiveness", "—")))
                base = j.get("base_rtt")
                self._speed_labels["latency"].configure(text=f"{base} ms" if base is not None else "—")

                full = summary
                if isinstance(data.get("json"), dict):
                    full += "\n\n" + json.dumps(data["json"], indent=2)
                self._set_textbox(self.txt_speed, full)
                self.btn_speed.configure(state="normal", text="Run Test")

            self._safe_ui(apply)

        threading.Thread(target=work, daemon=True).start()

    # ── iperf3 LAN throughput ───────────────────────────────────────

    def _build_iperf_card(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color=theme.BG_CARD, border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", padx=16, pady=4)

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(hdr, text="LAN Throughput (iperf3)", font=ctk.CTkFont(size=13, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")

        ctrl = ctk.CTkFrame(card, fg_color="transparent")
        ctrl.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(ctrl, text="Server:", font=ctk.CTkFont(size=11), text_color=theme.FG_MUTED).pack(side="left")
        self.iperf_host = ctk.CTkEntry(ctrl, width=180, placeholder_text="gateway IP or iperf3 server", font=ctk.CTkFont(size=12))
        self.iperf_host.pack(side="left", padx=4)

        ctk.CTkButton(ctrl, text="Use Gateway", width=100, font=ctk.CTkFont(size=11), command=self._iperf_use_gateway).pack(side="left", padx=4)

        self.btn_iperf_dl = ctk.CTkButton(ctrl, text="Download", width=90, command=lambda: self._run_iperf(reverse=True), font=ctk.CTkFont(size=12))
        self.btn_iperf_dl.pack(side="left", padx=4)
        self.btn_iperf_ul = ctk.CTkButton(ctrl, text="Upload", width=90, command=lambda: self._run_iperf(reverse=False), font=ctk.CTkFont(size=12))
        self.btn_iperf_ul.pack(side="left", padx=4)

        if not iperf_collector.iperf3_available():
            self.btn_iperf_dl.configure(state="disabled")
            self.btn_iperf_ul.configure(state="disabled")

        self.iperf_cards_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.iperf_cards_frame.pack(fill="x", padx=16, pady=(0, 4))
        self._iperf_labels: dict[str, ctk.CTkLabel] = {}
        for i, (key, label) in enumerate([("throughput", "Throughput"), ("retransmits", "Retransmits"), ("duration", "Duration")]):
            self.iperf_cards_frame.columnconfigure(i, weight=1)
            cell = ctk.CTkFrame(self.iperf_cards_frame, corner_radius=8, fg_color=theme.BG_CARD_HOVER)
            cell.grid(row=0, column=i, padx=3, pady=4, sticky="nsew")
            ctk.CTkLabel(cell, text=label, font=ctk.CTkFont(size=10), text_color=theme.FG_MUTED).pack(padx=6, pady=(6, 0))
            v = ctk.CTkLabel(cell, text="—", font=ctk.CTkFont(size=15, weight="bold"), text_color=theme.FG_PRIMARY)
            v.pack(padx=6, pady=(0, 6))
            self._iperf_labels[key] = v

        self.txt_iperf = ctk.CTkTextbox(card, height=80, fg_color="transparent", text_color=theme.FG_SECONDARY, font=ctk.CTkFont(family="Menlo", size=11), wrap="word")
        self.txt_iperf.pack(fill="x", padx=16, pady=(0, 12))
        if iperf_collector.iperf3_available():
            self.txt_iperf.insert("1.0", "Enter a server IP running iperf3 -s, or use your gateway.\nRequires iperf3 server on the other end.")
        else:
            self.txt_iperf.insert("1.0", "iperf3 not found. Install with: brew install iperf3")
        self.txt_iperf.configure(state="disabled")

    def _iperf_use_gateway(self) -> None:
        snap = interface_collector.snapshot()
        gw = snap.get("default_gateway")
        if gw:
            self.iperf_host.delete(0, "end")
            self.iperf_host.insert(0, gw)

    def _run_iperf(self, reverse: bool = False) -> None:
        server = (self.iperf_host.get() or "").strip()
        if not server:
            self._set_textbox(self.txt_iperf, "Enter a server IP first.")
            return

        direction = "Download" if reverse else "Upload"
        self.btn_iperf_dl.configure(state="disabled")
        self.btn_iperf_ul.configure(state="disabled")
        self._set_textbox(self.txt_iperf, f"Running iperf3 {direction.lower()} test to {server}…")
        for lbl in self._iperf_labels.values():
            lbl.configure(text="…")

        def work() -> None:
            data = iperf_collector.run_iperf3(server, duration=10, reverse=reverse)
            summary = iperf_collector.summarize_result(data)

            def apply() -> None:
                mbps = summary.get("mbps")
                self._iperf_labels["throughput"].configure(
                    text=f"{mbps:.1f} Mbps" if mbps is not None else "—"
                )
                retrans = summary.get("retransmits")
                self._iperf_labels["retransmits"].configure(
                    text=str(retrans) if retrans is not None else "—"
                )
                dur = summary.get("duration_s")
                self._iperf_labels["duration"].configure(
                    text=f"{dur:.1f} s" if dur is not None else "—"
                )

                if data.get("ok"):
                    self._set_textbox(self.txt_iperf, f"{direction}: {mbps:.1f} Mbps" if mbps else data.get("raw", ""))
                else:
                    self._set_textbox(self.txt_iperf, data.get("raw") or "Test failed.")

                self.btn_iperf_dl.configure(state="normal")
                self.btn_iperf_ul.configure(state="normal")

            self._safe_ui(apply)

        threading.Thread(target=work, daemon=True).start()

    # ── Traceroute ───────────────────────────────────────────────────

    def _build_trace_card(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color=theme.BG_CARD, border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", padx=16, pady=4)

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(hdr, text="Traceroute", font=ctk.CTkFont(size=13, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")
        self.trace_host = ctk.CTkEntry(hdr, width=150, placeholder_text="8.8.8.8", font=ctk.CTkFont(size=12),
                                        fg_color=theme.BG_INPUT, border_color=theme.BORDER, text_color=theme.FG_PRIMARY)
        self.trace_host.insert(0, "8.8.8.8")
        self.trace_host.pack(side="right", padx=(8, 0))
        self.btn_trace = ctk.CTkButton(hdr, text="Run", width=70, command=self._run_trace, font=ctk.CTkFont(size=12))
        self.btn_trace.pack(side="right")

        self.txt_trace = ctk.CTkTextbox(card, height=160, fg_color="transparent", text_color=theme.FG_SECONDARY, font=ctk.CTkFont(family="Menlo", size=11))
        self.txt_trace.pack(fill="x", padx=16, pady=(0, 12))
        self.txt_trace.insert("1.0", "Press 'Run' to trace route…")
        self.txt_trace.configure(state="disabled")

    def _run_trace(self) -> None:
        host = (self.trace_host.get() or "8.8.8.8").strip()
        self.btn_trace.configure(state="disabled", text="Running…")
        self._set_textbox(self.txt_trace, f"Tracing route to {host}…")

        def work() -> None:
            res = traceroute_collector.traceroute(host)
            out = "\n".join(res.get("lines") or [res.get("raw") or ""])

            def apply() -> None:
                self._set_textbox(self.txt_trace, out)
                self.btn_trace.configure(state="normal", text="Run")

            self._safe_ui(apply)

        threading.Thread(target=work, daemon=True).start()

    # ── Interfaces ───────────────────────────────────────────────────

    def _build_iface_card(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color=theme.BG_CARD, border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", padx=16, pady=(4, 16))

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(hdr, text="Network Interfaces", font=ctk.CTkFont(size=13, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")
        self.btn_iface = ctk.CTkButton(hdr, text="Refresh", width=80, command=self._load_interfaces, font=ctk.CTkFont(size=12))
        self.btn_iface.pack(side="right")

        self.txt_if = ctk.CTkTextbox(card, height=200, fg_color="transparent", text_color=theme.FG_SECONDARY, font=ctk.CTkFont(family="Menlo", size=11))
        self.txt_if.pack(fill="x", padx=16, pady=(0, 12))
        self.txt_if.insert("1.0", "Loading…")
        self.txt_if.configure(state="disabled")

    def _load_interfaces(self) -> None:
        self.btn_iface.configure(state="disabled", text="Loading…")

        def work() -> None:
            snap = interface_collector.snapshot()
            text = (
                "── Network Setup ──\n"
                + snap["networksetup"]
                + "\n\n── Default Route ──\n"
                + snap["route_default"]
                + "\n\n── ARP Table ──\n"
                + snap["arp"][:8000]
                + "\n\n── ifconfig ──\n"
                + snap["ifconfig"][:12000]
            )

            def apply() -> None:
                self._set_textbox(self.txt_if, text)
                self.btn_iface.configure(state="normal", text="Refresh")

            self._safe_ui(apply)

        threading.Thread(target=work, daemon=True).start()

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _set_textbox(tb: ctk.CTkTextbox, text: str) -> None:
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        tb.insert("1.0", text)
        tb.configure(state="disabled")

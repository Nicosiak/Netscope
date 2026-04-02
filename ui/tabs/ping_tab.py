"""Ping tab — grouped sections with clear visual hierarchy."""

from __future__ import annotations

import csv
from tkinter import filedialog
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from analysis import thresholds
from collectors import interface_collector
from ui import theme

_CARD = dict(fg_color=theme.BG_CARD, corner_radius=10, border_width=1, border_color=theme.BORDER)
_PAD = 16


def _section_label(parent: Any, text: str) -> None:
    ctk.CTkFrame(parent, fg_color=theme.DIVIDER, height=1).pack(fill="x", padx=_PAD, pady=(14, 0))
    ctk.CTkLabel(parent, text=text.upper(), font=ctk.CTkFont(size=10, weight="bold"),
                 text_color=theme.FG_MUTED).pack(anchor="w", padx=_PAD + 4, pady=(6, 4))


class PingTab:
    def __init__(self, master: Any) -> None:
        self.master = master
        self._on_target_change: Optional[Callable[[str], None]] = None
        self._log: List[Dict[str, Any]] = []

        outer = ctk.CTkScrollableFrame(master, fg_color=theme.BG_PRIMARY)
        outer.pack(fill="both", expand=True)

        # ── Section 1: Target ────────────────────────────────────────
        _section_label(outer, "Target")
        self._build_target_selector(outer)

        # ── Section 2: Live Stats ────────────────────────────────────
        _section_label(outer, "Statistics")
        self._build_stat_cards(outer)

        # ── Section 3: Chart ─────────────────────────────────────────
        _section_label(outer, "Latency Graph")
        self._build_chart(outer)

        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.pack(fill="x", padx=_PAD, pady=(2, 16))
        ctk.CTkButton(btn_row, text="Export Log", width=100, height=26, command=self._export_csv,
                       font=ctk.CTkFont(size=10), fg_color=theme.BG_CARD, hover_color=theme.BG_CARD_HOVER,
                       border_width=1, border_color=theme.BORDER, text_color=theme.FG_MUTED
                       ).pack(side="right")

    def _build_target_selector(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, **_CARD)
        card.pack(fill="x", padx=_PAD, pady=(0, 4))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=(12, 6))
        ctk.CTkLabel(row1, text="Ping Target", font=ctk.CTkFont(size=12, weight="bold"), text_color=theme.FG_PRIMARY).pack(side="left")
        self.lbl_active = ctk.CTkLabel(row1, text="→ 8.8.8.8", font=ctk.CTkFont(size=12), text_color=theme.ACCENT_BRIGHT)
        self.lbl_active.pack(side="right")

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=(0, 8))
        self.var_target = ctk.StringVar(value="8.8.8.8")
        for val, label in (("8.8.8.8", "Google"), ("1.1.1.1", "Cloudflare"), ("router", "Router"), ("custom", "Custom")):
            ctk.CTkRadioButton(row2, text=label, variable=self.var_target, value=val, command=self._apply_target,
                                font=ctk.CTkFont(size=11), text_color=theme.FG_SECONDARY).pack(side="left", padx=6)

        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.pack(fill="x", padx=20, pady=(0, 12))
        self.entry_custom = ctk.CTkEntry(row3, width=200, placeholder_text="hostname or IP", font=ctk.CTkFont(size=12),
                                          fg_color=theme.BG_INPUT, border_color=theme.BORDER, text_color=theme.FG_PRIMARY)
        self.entry_custom.pack(side="left")
        ctk.CTkButton(row3, text="Apply", width=60, height=28, command=self._apply_target,
                       font=ctk.CTkFont(size=11), fg_color=theme.ACCENT_DIM, hover_color=theme.ACCENT).pack(side="left", padx=8)

    def _build_stat_cards(self, parent: Any) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=_PAD, pady=(0, 4))
        for col in range(6):
            row.columnconfigure(col, weight=1)

        self._stat_labels: Dict[str, ctk.CTkLabel] = {}
        for i, (key, label, unit) in enumerate([
            ("current", "Current", "ms"), ("min", "Min", "ms"), ("avg", "Avg", "ms"),
            ("max", "Max", "ms"), ("jitter", "Jitter", "ms"), ("loss", "Loss", "%"),
        ]):
            cell = ctk.CTkFrame(row, corner_radius=8, fg_color=theme.BG_CARD, border_width=1, border_color=theme.BORDER)
            cell.grid(row=0, column=i, padx=3, sticky="nsew")
            ctk.CTkLabel(cell, text=label, font=ctk.CTkFont(size=9), text_color=theme.FG_MUTED).pack(padx=8, pady=(8, 0))
            val_lbl = ctk.CTkLabel(cell, text="—", font=ctk.CTkFont(size=16, weight="bold"), text_color=theme.FG_PRIMARY)
            val_lbl.pack(padx=8, pady=(0, 2))
            ctk.CTkLabel(cell, text=unit, font=ctk.CTkFont(size=9), text_color=theme.FG_MUTED).pack(padx=8, pady=(0, 6))
            self._stat_labels[key] = val_lbl

    def _build_chart(self, parent: Any) -> None:
        card = ctk.CTkFrame(parent, **_CARD)
        card.pack(fill="both", expand=True, padx=_PAD, pady=(0, 4))

        self._fig = Figure(figsize=(7, 2.6), dpi=100)
        self._ax = self._fig.add_subplot(111)
        self._line, = self._ax.plot([], [], color=theme.COLOR_LATENCY, linewidth=2)
        self._loss_scatter = self._ax.scatter([], [], color=theme.COLOR_PING_LOSS, s=24, zorder=5, marker="x")
        self._ax.axhline(y=20, color=theme.COLOR_PING_GOOD, linewidth=0.6, linestyle="--", alpha=0.4)
        self._ax.axhline(y=80, color=theme.COLOR_PING_HIGH, linewidth=0.6, linestyle="--", alpha=0.4)
        self._ax.set_ylabel("ms", fontsize=9)
        theme.style_figure(self._fig)

        self._canvas = FigureCanvasTkAgg(self._fig, master=card)
        self._canvas.get_tk_widget().configure(bg=theme.CHART_BG, highlightthickness=0)
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

    def bind_target_change(self, cb: Callable[[str], None]) -> None:
        self._on_target_change = cb

    def _resolve_target(self) -> str:
        choice = self.var_target.get()
        if choice == "custom":
            return (self.entry_custom.get() or "8.8.8.8").strip()
        if choice == "router":
            snap = interface_collector.snapshot()
            return snap.get("default_gateway") or "192.168.1.1"
        return choice

    def _apply_target(self) -> None:
        host = self._resolve_target()
        self.lbl_active.configure(text=f"→ {host}")
        if self._on_target_change:
            self._on_target_change(host)

    def _export_csv(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "target", "rtt_ms", "lost", "min_ms", "avg_ms", "max_ms", "jitter_ms", "loss_pct"])
            for row in self._log:
                w.writerow([row.get("ts", ""), row.get("target", ""), row.get("rtt_ms", ""), row.get("lost", ""),
                            row.get("min_ms", ""), row.get("avg_ms", ""), row.get("max_ms", ""), row.get("jitter_ms", ""), row.get("loss_pct", "")])

    def on_ping_sample(self, payload: Dict[str, Any]) -> None:
        self._log.append(payload)
        if len(self._log) > 3600:
            self._log = self._log[-1800:]

        hist = payload.get("history_ms") or []
        xs, ys, loss_x = [], [], []
        for i, v in enumerate(hist):
            if v is None:
                loss_x.append(i)
            else:
                xs.append(i)
                ys.append(v)

        self._line.set_data(xs, ys)
        total = len(hist)
        if total:
            self._ax.set_xlim(-1, max(60, total))
        if ys:
            pad = max(3.0, (max(ys) - min(ys)) * 0.15 + 2.0)
            y_lo = max(0, min(ys) - pad)
            y_hi = max(ys) + pad
        else:
            y_lo, y_hi = 0, 100
        self._ax.set_ylim(y_lo, y_hi)

        if loss_x:
            loss_y = [y_lo + (y_hi - y_lo) * 0.05] * len(loss_x)
            self._loss_scatter.set_offsets(np.column_stack([loss_x, loss_y]))
        else:
            self._loss_scatter.set_offsets(np.empty((0, 2)))
        self._canvas.draw_idle()

        cur = payload.get("rtt_ms")
        _, col = thresholds.classify_ping_ms(cur)
        self._stat_labels["current"].configure(text=f"{cur:.1f}" if cur is not None else "LOSS", text_color=col if cur is not None else theme.COLOR_POOR)

        def fmt(v: Any) -> str:
            return f"{v:.1f}" if isinstance(v, (int, float)) else "—"

        self._stat_labels["min"].configure(text=fmt(payload.get("min_ms")))
        self._stat_labels["avg"].configure(text=fmt(payload.get("avg_ms")))
        self._stat_labels["max"].configure(text=fmt(payload.get("max_ms")))
        self._stat_labels["jitter"].configure(text=fmt(payload.get("jitter_ms")))
        lp = payload.get("loss_pct")
        self._stat_labels["loss"].configure(
            text=f"{lp:.1f}" if isinstance(lp, (int, float)) else "—",
            text_color=theme.COLOR_POOR if isinstance(lp, (int, float)) and lp > 1.0 else theme.FG_PRIMARY,
        )

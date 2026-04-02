"""WiFiman-inspired dark color palette and matplotlib styling."""

from __future__ import annotations

import warnings

from matplotlib.figure import Figure

warnings.filterwarnings("ignore", message=".*tight_layout.*")

# ── WiFiman-matched palette ──────────────────────────────────────────
# Sampled from the Ubiquiti WiFiman screenshots

# Accent — WiFiman uses a bright blue for active tabs and interactive elements
ACCENT = "#3b82f6"
ACCENT_BRIGHT = "#60a5fa"
ACCENT_DIM = "#2563eb"

# Signal quality — WiFiman uses these exact tones
COLOR_EXCELLENT = "#22c55e"  # bright green
COLOR_GOOD = "#3b82f6"       # blue
COLOR_FAIR = "#f59e0b"       # amber/orange
COLOR_POOR = "#ef4444"       # red
COLOR_UNKNOWN = "#4b5563"    # gray

# Speed colors — WiFiman uses cyan for download, purple/magenta for upload
COLOR_DOWNLOAD = "#06b6d4"   # cyan
COLOR_UPLOAD = "#a855f7"     # purple
COLOR_LATENCY = "#22c55e"    # green

# Ping
COLOR_PING_GOOD = "#22c55e"
COLOR_PING_WARN = "#f59e0b"
COLOR_PING_HIGH = "#ef4444"
COLOR_PING_LOSS = "#ef4444"

# ── Surface colors (dark only — WiFiman is always dark) ──────────────
BG_PRIMARY = "#0f1117"       # near-black, WiFiman's main background
BG_CARD = "#1a1d27"          # slightly lighter card surface
BG_CARD_HOVER = "#242836"    # hover/active state
BG_INPUT = "#1e2230"         # input fields
FG_PRIMARY = "#e8eaed"       # bright white text
FG_SECONDARY = "#9ca3af"     # gray text for labels
FG_MUTED = "#6b7280"         # dimmer gray for hints
BORDER = "#2a2e3a"           # subtle borders between cards
DIVIDER = "#1f2430"          # thin line between sections

# Chart
CHART_BG = "#0f1117"         # matches app background
CHART_GRID = "#1f2937"       # very subtle grid lines
CHART_FG = "#9ca3af"         # axis labels
CHART_LINE = "#ef4444"       # WiFiman uses red for the RSSI signal line


def style_figure(fig: Figure) -> None:
    """Apply WiFiman-style dark theme to a matplotlib Figure."""
    fig.patch.set_facecolor(CHART_BG)
    for ax in fig.get_axes():
        ax.set_facecolor(CHART_BG)
        ax.tick_params(colors=CHART_FG, labelsize=8)
        ax.xaxis.label.set_color(CHART_FG)
        ax.yaxis.label.set_color(CHART_FG)
        ax.title.set_color(FG_PRIMARY)
        for spine in ax.spines.values():
            spine.set_color(CHART_GRID)
        ax.grid(True, color=CHART_GRID, alpha=0.6, linewidth=0.5)
    try:
        fig.tight_layout(pad=1.2)
    except Exception:
        pass

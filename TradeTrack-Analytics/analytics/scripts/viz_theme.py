"""
TradeTrack Analytics — shared visual theme.
============================================

One design system for every output surface (matplotlib PNGs, Plotly HTML and
the dashboard), so the charts read as a single product rather than ten
different people's defaults.

Colour decisions, and why:

  * Categorical slots are assigned in a FIXED order and never cycled — the
    same asset keeps the same hue in every chart it appears in.
  * The eight-hue set was checked with a colour-vision-deficiency validator
    against this exact dark surface: worst adjacent CVD separation dE 8.4,
    worst normal-vision separation dE 19.3, all eight >= 3:1 contrast on the
    surface. Slot order is the safety mechanism, not decoration.
  * Profit/loss uses the reserved STATUS colours (good / critical), not
    categorical slots. Profit-vs-loss is a state, not a series, and in a
    trading context green/red is a domain convention readers rely on. Both
    clear 3:1 on the surface (5.41:1 and 3.78:1) and are always paired with a
    label or sign so colour never carries the meaning alone.
  * A single sequential blue ramp handles magnitude (heatmaps); a blue<->red
    diverging ramp with a neutral grey midpoint handles polarity.
"""
from __future__ import annotations

import matplotlib as mpl
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import PathPatch
from matplotlib.path import Path

# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
SURFACE = "#12161c"        # chart surface
PAGE = "#0b0e13"           # page plane behind the cards
TEXT_PRIMARY = "#f2f4f7"   # 16.5:1
TEXT_SECONDARY = "#a8b0bd"  # 8.3:1
TEXT_MUTED = "#7c8698"     # 4.9:1
GRID = "#1e242e"
AXIS = "#2a323f"
BORDER = "#232b36"

# Validated categorical order — do not reorder, do not cycle past slot 8.
CATEGORICAL = [
    "#3987e5",  # 1 blue
    "#d95926",  # 2 orange
    "#199e70",  # 3 aqua
    "#c98500",  # 4 yellow
    "#d55181",  # 5 magenta
    "#008300",  # 6 green
    "#9085e9",  # 7 violet
    "#e66767",  # 8 red
]

# Reserved status colours (profit / loss polarity).
PROFIT = "#0ca30c"
LOSS = "#d03b3b"
WARNING = "#fab219"
NEUTRAL = "#7c8698"

# Sequential blue ramp (light -> dark reversed for a dark surface: near-zero
# recedes toward the surface, high magnitude comes forward).
SEQUENTIAL = ["#101a28", "#16324f", "#1c5cab", "#2a78d6", "#5598e7", "#9ec5f4"]
CMAP_SEQ = LinearSegmentedColormap.from_list("tt_seq", SEQUENTIAL)

# Diverging red <-> neutral <-> blue, neutral grey midpoint (never a hue).
CMAP_DIV = LinearSegmentedColormap.from_list(
    "tt_div", ["#8c2b2b", "#d03b3b", "#e08a8a", "#383f4a", "#7fb0ee", "#2a78d6", "#18426f"]
)

# Stable hue assignment so an asset/strategy keeps its colour across charts.
ASSET_COLORS = {
    "BTC": CATEGORICAL[0], "ETH": CATEGORICAL[1], "GOLD": CATEGORICAL[3],
    "NASDAQ": CATEGORICAL[2], "US30": CATEGORICAL[6], "EURUSD": CATEGORICAL[4],
}
SESSION_COLORS = {
    "Asia": CATEGORICAL[0], "London": CATEGORICAL[1], "New York": CATEGORICAL[2],
}


def apply_theme() -> None:
    """Install the theme as matplotlib defaults."""
    mpl.rcParams.update({
        "figure.facecolor": PAGE,
        "figure.edgecolor": PAGE,
        "savefig.facecolor": PAGE,
        "savefig.edgecolor": PAGE,
        "savefig.bbox": "tight",
        "savefig.dpi": 160,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": TEXT_SECONDARY,
        "axes.titlecolor": TEXT_PRIMARY,
        "axes.titlesize": 13,
        "axes.titleweight": "600",
        "axes.titlepad": 14,
        "axes.labelsize": 10,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "grid.alpha": 1.0,
        "xtick.color": TEXT_MUTED,
        "ytick.color": TEXT_MUTED,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "text.color": TEXT_PRIMARY,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "legend.labelcolor": TEXT_SECONDARY,
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "figure.autolayout": False,
    })


def style_axes(ax, xgrid: bool = False, ygrid: bool = True) -> None:
    """Recessive chrome: horizontal rules only, no vertical clutter."""
    ax.grid(axis="y", visible=ygrid)
    ax.grid(axis="x", visible=xgrid)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(AXIS)
    ax.tick_params(length=0)


def title(ax, headline: str, sub: str | None = None) -> None:
    """Title + optional deck line. The deck states the finding, not the axes.

    The title pad has to clear the deck line, otherwise the two overlap: the
    axes title is placed relative to the axes top in points, while the deck is
    placed in axes-fraction coordinates.
    """
    ax.set_title(headline, loc="left", pad=30 if sub else 12)
    if sub:
        ax.text(0.0, 1.012, sub, transform=ax.transAxes, fontsize=9.5,
                color=TEXT_MUTED, ha="left", va="bottom", wrap=True)


# --------------------------------------------------------------------------
# Marks
# --------------------------------------------------------------------------
def _rounded_end_path(x0, y0, x1, y1, r, horizontal: bool) -> Path:
    """Rectangle with only the DATA END rounded; the baseline end stays square.

    A bar anchored to a zero baseline should meet that baseline flat — rounding
    all four corners detaches the mark from its own axis and makes small values
    read as larger than they are.
    """
    if horizontal:
        r = min(r, abs(x1 - x0), abs(y1 - y0) / 2)
        s = 1 if x1 >= x0 else -1
        verts = [
            (x0, y0), (x1 - s * r, y0),
            (x1, y0), (x1, y0 + r),
            (x1, y1 - r),
            (x1, y1), (x1 - s * r, y1),
            (x0, y1), (x0, y0),
        ]
        codes = [Path.MOVETO, Path.LINETO, Path.CURVE3, Path.CURVE3,
                 Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO, Path.CLOSEPOLY]
    else:
        r = min(r, abs(y1 - y0), abs(x1 - x0) / 2)
        s = 1 if y1 >= y0 else -1
        verts = [
            (x0, y0), (x0, y1 - s * r),
            (x0, y1), (x0 + r, y1),
            (x1 - r, y1),
            (x1, y1), (x1, y1 - s * r),
            (x1, y0), (x0, y0),
        ]
        codes = [Path.MOVETO, Path.LINETO, Path.CURVE3, Path.CURVE3,
                 Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO, Path.CLOSEPOLY]
    return Path(verts, codes)


def rounded_bars(ax, positions, values, colors, width=0.68, horizontal=False,
                 radius_frac=0.10, baseline=0.0):
    """Thin bars with a 4px-equivalent rounded data end and a surface gap."""
    span = max(abs(np.max(values)), abs(np.min(values)), 1e-9)
    r = span * radius_frac * 0.35
    patches = []
    for pos, val, col in zip(positions, values, colors):
        if horizontal:
            path = _rounded_end_path(baseline, pos - width / 2, val, pos + width / 2,
                                     r, horizontal=True)
        else:
            path = _rounded_end_path(pos - width / 2, baseline, pos + width / 2, val,
                                     r, horizontal=False)
        # The 1.2pt surface-coloured edge is the 2px gap between adjacent fills.
        p = PathPatch(path, facecolor=col, edgecolor=SURFACE, linewidth=1.2, zorder=3)
        ax.add_patch(p)
        patches.append(p)
    ax.autoscale_view()
    return patches


def pnl_colors(values) -> list[str]:
    """Status colouring for a P&L series — profit good, loss critical."""
    return [PROFIT if v >= 0 else LOSS for v in values]


def money(v: float, decimals: int = 0) -> str:
    """Compact currency label: $1.2M / $340K / $820."""
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1_000_000:
        return f"{sign}${a / 1_000_000:.2f}M"
    if a >= 1_000:
        return f"{sign}${a / 1_000:.0f}K"
    return f"{sign}${a:,.{decimals}f}"


def footnote(fig, text: str) -> None:
    fig.text(0.005, -0.02, text, fontsize=8, color=TEXT_MUTED, ha="left", va="top")


# --------------------------------------------------------------------------
# Plotly
# --------------------------------------------------------------------------
def plotly_layout(title_text: str, subtitle: str | None = None) -> dict:
    """Matching layout for the interactive Plotly exports."""
    t = title_text
    if subtitle:
        t += f"<br><span style='font-size:12px;color:{TEXT_MUTED}'>{subtitle}</span>"
    return dict(
        title=dict(text=t, x=0, xanchor="left",
                   font=dict(size=17, color=TEXT_PRIMARY)),
        paper_bgcolor=PAGE,
        plot_bgcolor=SURFACE,
        font=dict(family="Helvetica Neue, Helvetica, Arial, sans-serif",
                  size=12, color=TEXT_SECONDARY),
        xaxis=dict(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS,
                   tickfont=dict(color=TEXT_MUTED)),
        yaxis=dict(gridcolor=GRID, zerolinecolor=AXIS, linecolor=AXIS,
                   tickfont=dict(color=TEXT_MUTED)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_SECONDARY)),
        hoverlabel=dict(bgcolor="#1b212b", bordercolor=BORDER,
                        font=dict(color=TEXT_PRIMARY, size=12)),
        margin=dict(l=64, r=28, t=88, b=56),
    )

"""Standardized chart color system and chrome (chart chrome, categorical series).

This module is identical, byte-for-byte, across all six repos in the
github.com/alexc-hue project-controls toolkit (schedule-health-analyzer,
project-controls-dashboard, change-control-register, risk-trend-tracker,
project-controls-reporting-engine, recovery-scenario-planner). Each repo
carries its own copy so it stays independently cloneable and runnable
without pulling in the others, the same rationale the vendored engines
already document. project-controls-dashboard is the canonical source; if
the palette changes, update it there first and re-sync the rest.
"""

from __future__ import annotations

CHART_BG = "#fcfcfb"
INK = "#10182b"
GRID = "#e1e0d9"
SERIES_1 = "#2a78d6"
SERIES_2 = "#eb6834"
SERIES_3 = "#1baf7a"


def apply_chrome(fig, axes) -> None:
    """Apply the standardized chart chrome (background, ink, gridlines) to a figure."""
    fig.patch.set_facecolor(CHART_BG)
    if hasattr(axes, "flatten"):
        axes = axes.flatten().tolist()
    elif not isinstance(axes, (list, tuple)):
        axes = [axes]
    for ax in axes:
        ax.set_facecolor(CHART_BG)
        ax.title.set_color(INK)
        ax.xaxis.label.set_color(INK)
        ax.yaxis.label.set_color(INK)
        ax.tick_params(colors=INK)
        for spine in ax.spines.values():
            spine.set_color(INK)

"""
Recovery Scenario Planner
------------------------------------
Runs the vendored CPM and EVM engines (see engines/) against the Ridgeline
programme's current status, applies each of the three canned interventions
in src/interventions.py, and prints a before/after comparison plus the
ranked recommendation with rationale from src/recommend.py.

This adds no new EVM, CPM, or risk-scoring logic: all of that already exists
in the standalone toolkit repos this account publishes, vendored unchanged
under engines/ (see each module's header for its source). The only new code
is the intervention parametrization, the decision-rule scoring, and this
orchestration layer, following the same pattern
project-controls-reporting-engine already uses to compose the toolkit's
engines against one shared programme.

Run:
    pip install -r requirements.txt
    python planner.py
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import pandas as pd

from engines import chart_style
from engines.dashboard import metrics as dash
from engines.risk import metrics as risk
from engines.schedule import cpm as cpm_engine
from engines.schedule import metrics as sched
from engines.formatting import money

from src import interventions as iv
from src import recommend

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

BAC = 2_400_000
PROJECT_START = "2026-01-05"
STATUS_DATE = "2026-08-01"

# Chart generation is best-effort, but only for genuinely environmental
# failure modes: an unwritable assets dir (OSError) or a matplotlib backend/
# rendering failure (RuntimeError). KeyError/TypeError/ValueError are
# deliberately NOT caught here -- those are exactly the exceptions a real
# coding bug (a typo'd attribute, a wrong type passed in) would raise, and
# swallowing them into a one-line "chart generation skipped" message would
# hide the bug instead of surfacing it.
CHART_EXCEPTIONS = (OSError, RuntimeError)


def load_programme_status():
    activities = sched.load_activities(os.path.join(DATA_DIR, "activities.csv"))

    ts = dash.load_timeseries(os.path.join(DATA_DIR, "cost_schedule_timeseries.csv"))
    summary = dash.project_summary(ts, BAC)

    snapshots = risk.load_snapshots(os.path.join(DATA_DIR, "risk_snapshots.csv"))
    exposure_trend = risk.portfolio_exposure_trend(snapshots)
    portfolio_exposure = float(exposure_trend["total_exposure"].iloc[-1])

    return activities, summary, snapshots, portfolio_exposure


def build_scenarios(activities, snapshots, portfolio_exposure):
    baseline_result = cpm_engine.run_cpm(
        activities, duration_col="baseline_duration_days", start_date=pd.Timestamp(PROJECT_START)
    )

    do_nothing = iv.do_nothing(activities, baseline_result, PROJECT_START, portfolio_exposure)
    add_resources = iv.add_resources(
        activities, baseline_result, PROJECT_START, do_nothing.forecast_finish, portfolio_exposure,
        do_nothing.comparison,
    )
    fast_track = iv.fast_track(
        activities, baseline_result, PROJECT_START, do_nothing.forecast_finish, snapshots, portfolio_exposure
    )

    return baseline_result, [do_nothing, add_resources, fast_track]


def print_comparison(baseline_result, scenarios, summary) -> None:
    print("=" * 68)
    print("RECOVERY SCENARIO COMPARISON")
    print("Ridgeline LNG Compressor Station Retrofit, as of", STATUS_DATE)
    print("=" * 68)
    print()
    print(f"Baseline finish:  {baseline_result.project_finish.date()}")
    print(
        f"Cost performance to date: SPI {summary['spi']:.2f}  CPI {summary['cpi']:.2f}  "
        f"EAC {money(summary['eac'])}  VAC {money(summary['vac'])}"
    )
    print()
    print(f"{'Option':42}{'Finish':13}{'Days recov.':13}{'Cost impact':14}{'Revised EAC':14}{'Risk exposure':>13}")
    print("-" * 108)
    for s in scenarios:
        revised_eac = summary["eac"] + s.cost_impact
        print(
            f"{s.label:42}{s.forecast_finish.date().isoformat():13}"
            f"{s.days_recovered:>+5d}        "
            f"{money(s.cost_impact):>10}    "
            f"{money(revised_eac):>10}    "
            f"{s.risk_exposure:>9.1f}"
        )
    print()


def chart_comparison(scenarios) -> str | None:
    """Generate a simple before/after bar chart: forecast finish slip and revised EAC per option."""
    try:
        labels = [s.label for s in scenarios]
        slips = [s.slip_days for s in scenarios]
        costs = [s.cost_impact for s in scenarios]
        # The palette assumes exactly 3 canned scenarios (do_nothing,
        # add_resources, fast_track) by design. Assert that invariant with a
        # clear message instead of cycling colors, which would silently
        # assign two different scenarios the same color and misrepresent
        # the chart -- a bad failure mode for a tool whose whole point is
        # accurate reporting.
        assert len(scenarios) <= 3, (
            f"chart_comparison has only 3 palette colors but got {len(scenarios)} scenarios; "
            "extend the palette deliberately before adding a 4th scenario"
        )
        colors = [chart_style.SERIES_1, chart_style.SERIES_2, chart_style.SERIES_3][:len(scenarios)]

        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

        ax = axes[0]
        ax.barh(labels, slips, color=colors)
        ax.set_title("Forecast finish slip vs. baseline (days)")
        ax.axvline(0, color=chart_style.INK, linewidth=0.8, alpha=0.6)
        ax.grid(color=chart_style.GRID, linewidth=0.6, axis="x")

        ax = axes[1]
        ax.barh(labels, costs, color=colors)
        ax.set_title("Incremental cost of the intervention ($)")
        ax.grid(color=chart_style.GRID, linewidth=0.6, axis="x")

        chart_style.apply_chrome(fig, axes)
        fig.suptitle("Recovery Scenario Comparison: Ridgeline LNG Compressor Station Retrofit",
                     fontsize=12, color=chart_style.INK)
        fig.tight_layout()
        out_path = os.path.join(ASSETS_DIR, "before_after_comparison.png")
        fig.savefig(out_path, dpi=140, facecolor=chart_style.CHART_BG)
        plt.close(fig)
        return out_path
    except CHART_EXCEPTIONS as exc:
        print(f"(chart generation skipped: {exc!r})")
        return None


def main() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)

    activities, summary, snapshots, portfolio_exposure = load_programme_status()
    baseline_result, scenarios = build_scenarios(activities, snapshots, portfolio_exposure)

    print_comparison(baseline_result, scenarios, summary)

    do_nothing = next(s for s in scenarios if s.name == "do_nothing")
    ranked = recommend.rank_scenarios(
        scenarios, do_nothing.slip_days, summary["spi"], summary["cpi"], portfolio_exposure
    )
    recommend.print_recommendation(ranked, summary["spi"], summary["cpi"], do_nothing.slip_days, portfolio_exposure)

    chart_path = chart_comparison(scenarios)
    if chart_path:
        print()
        print("-" * 68)
        print(f"Comparison chart saved to {chart_path}")


if __name__ == "__main__":
    main()

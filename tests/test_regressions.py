"""Regression tests for bugs fixed in commits 1ac999c and 9ea7476.

Each test was confirmed to fail with its fix temporarily reverted before
being committed.
"""

from __future__ import annotations

import pandas as pd
import pytest

import planner
from engines.schedule import cpm as cpm_engine
from src import interventions
from src.interventions import ScenarioResult, add_resources, fast_track
from src.recommend import score_scenario

START = "2026-01-01"


def _scenario(name, days_recovered=0, cost_impact=0.0, risk_exposure=50.0, slip_days=0):
    return ScenarioResult(
        name=name, label=name, activities=None, comparison=None, forecast_finish=None,
        slip_days=slip_days, days_recovered=days_recovered, cost_impact=cost_impact,
        risk_exposure=risk_exposure, rationale="test",
    )


# --- 1ac999c -----------------------------------------------------------------

def test_recovery_component_floors_at_zero_when_an_option_loses_time():
    """An option that makes the finish later (negative days recovered) scores
    zero on recovery, not a negative number that drags the total below 0."""
    result = score_scenario(
        _scenario("add_resources", days_recovered=-10), slip_before=20,
        spi=1.0, cpi=1.0, baseline_exposure=50,
    )
    assert result["recovery_component"] == pytest.approx(0.0)


def test_crash_cost_is_billed_on_the_cut_actually_applied():
    """4 days, 0% complete: the ideal cut is 1.2 days, but the duration can
    only drop to round(2.8) = 3, so 1 day is actually recovered. Cost has to
    follow the 1 day applied, not the 1.2 days on paper."""
    activities = pd.DataFrame({
        "activity_id": ["A1"], "predecessors": [[]], "activity_name": ["Work"],
        "phase": ["Test"], "status": ["Not Started"], "percent_complete": [0],
        "current_duration_days": [4], "baseline_duration_days": [4],
    })
    baseline = cpm_engine.run_cpm(activities, "baseline_duration_days", pd.Timestamp(START))
    result = add_resources(
        activities=activities, baseline_result=baseline, project_start=START,
        current_before_finish=baseline.project_finish, portfolio_exposure=10.0,
        current_before_comparison=pd.DataFrame({"activity_id": ["A1"], "is_critical": [True]}),
    )
    assert result.days_recovered == 1
    assert result.cost_impact == pytest.approx(1 * interventions.CRASH_COST_PER_DAY)


def test_chained_fast_track_pairs_read_the_original_predecessors(monkeypatch):
    """With chained pairs (B->C, then C->D), D must pick up C's original
    predecessor (B), not the list C was just rewritten to in the same loop."""
    monkeypatch.setattr(interventions, "FAST_TRACK_PAIRS", [("B", "C"), ("C", "D")])
    monkeypatch.setattr(interventions, "FAST_TRACK_SENSITIVE_RISK_IDS", [])
    activities = pd.DataFrame({
        "activity_id": ["A", "B", "C", "D"],
        "predecessors": [[], ["A"], ["B"], ["C"]],
        "activity_name": ["A", "B", "C", "D"], "phase": ["T"] * 4,
        "status": ["Not Started"] * 4, "percent_complete": [0] * 4,
        "current_duration_days": [2, 2, 2, 2], "baseline_duration_days": [2, 2, 2, 2],
    })
    baseline = cpm_engine.run_cpm(activities, "baseline_duration_days", pd.Timestamp(START))
    snapshots = pd.DataFrame({
        "snapshot_date": pd.to_datetime(["2026-01-01"]), "risk_id": ["R01"], "exposure": [5],
    })
    result = fast_track(
        activities=activities, baseline_result=baseline, project_start=START,
        current_before_finish=baseline.project_finish, risk_snapshots=snapshots,
        portfolio_exposure=5.0,
    )
    preds = dict(zip(result.activities["activity_id"], result.activities["predecessors"]))
    assert preds["C"] == ["A"]
    assert preds["D"] == ["B"]


# --- 9ea7476 -----------------------------------------------------------------

def test_a_coding_bug_in_the_chart_is_not_swallowed(monkeypatch, tmp_path):
    """Only environmental failures (unwritable dir, backend errors) may be
    reduced to 'chart generation skipped'. A KeyError is a real bug and has to
    surface."""
    monkeypatch.setattr(planner, "ASSETS_DIR", str(tmp_path))

    def broken_chrome(fig, axes):
        raise KeyError("simulated bug")

    monkeypatch.setattr(planner.chart_style, "apply_chrome", broken_chrome)
    scenarios = [_scenario("a"), _scenario("b"), _scenario("c")]
    with pytest.raises(KeyError):
        planner.chart_comparison(scenarios)


def test_a_fourth_scenario_fails_loudly_instead_of_reusing_a_color(monkeypatch, tmp_path):
    monkeypatch.setattr(planner, "ASSETS_DIR", str(tmp_path))
    scenarios = [_scenario(n) for n in ("a", "b", "c", "d")]
    with pytest.raises(AssertionError, match="only 3 palette colors"):
        planner.chart_comparison(scenarios)

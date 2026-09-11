"""Tests for src/interventions.py: add_resources (crash) and fast_track
(re-sequence). Small hand-built activity sets, not the repo's sample CSVs.
"""

from __future__ import annotations

import pandas as pd
import pytest

from engines.schedule import cpm as cpm_engine
from src.interventions import FAST_TRACK_COORDINATION_COST, add_resources, fast_track


def test_add_resources_crashes_critical_activity():
    activities = pd.DataFrame({
        "activity_id": ["A2"],
        "predecessors": [[]],
        "activity_name": ["Critical Work"],
        "phase": ["Test"],
        "status": ["In Progress"],
        "percent_complete": [0],
        "current_duration_days": [10],
        "baseline_duration_days": [10],
    })
    start = pd.Timestamp("2026-01-01")
    baseline_result = cpm_engine.run_cpm(activities, duration_col="baseline_duration_days", start_date=start)
    current_before_comparison = pd.DataFrame({"activity_id": ["A2"], "is_critical": [True]})

    result = add_resources(
        activities=activities,
        baseline_result=baseline_result,
        project_start="2026-01-01",
        current_before_finish=baseline_result.project_finish,  # not yet crashed
        portfolio_exposure=10.0,
        current_before_comparison=current_before_comparison,
    )

    # remaining=10, cut=10*0.30=3, new_duration=round(10-3)=7, applied_cut=3.
    assert result.activities.loc[0, "current_duration_days"] == 7
    assert result.cost_impact == pytest.approx(3 * 5000)
    assert result.days_recovered == 3
    assert result.risk_exposure == pytest.approx(10.0)  # unaffected by crashing


def test_add_resources_clamps_negative_applied_cut():
    """A fractional current_duration_days close to its own crash floor can make
    round(current_duration_days - cut) land ABOVE current_duration_days (the
    "nothing left to cut" case) -- applied_cut must clamp to zero, not go
    negative and corrupt the aggregated cost."""
    activities = pd.DataFrame({
        "activity_id": ["A1"],
        "predecessors": [[]],
        "activity_name": ["Near-Done Activity"],
        "phase": ["Test"],
        "status": ["In Progress"],
        "percent_complete": [95],
        "current_duration_days": [4.6],
        "baseline_duration_days": [5],
    })
    start = pd.Timestamp("2026-01-01")
    baseline_result = cpm_engine.run_cpm(activities, duration_col="baseline_duration_days", start_date=start)
    current_before_comparison = pd.DataFrame({"activity_id": ["A1"], "is_critical": [True]})

    result = add_resources(
        activities=activities,
        baseline_result=baseline_result,
        project_start="2026-01-01",
        current_before_finish=baseline_result.project_finish,
        portfolio_exposure=42.0,
        current_before_comparison=current_before_comparison,
    )

    # round(4.6 - 0.069) = round(4.531) = 5, which is ABOVE current_duration_days
    # (4.6) -- without the clamp this activity would contribute a negative
    # "days cut" to the total.
    assert result.activities.loc[0, "current_duration_days"] == 5
    assert result.cost_impact == pytest.approx(0.0)


def test_fast_track_resequences_pair_and_uplifts_sensitive_risk_exposure():
    activities = pd.DataFrame({
        "activity_id": ["M2", "CM1", "CM2"],
        "predecessors": [[], ["M2"], ["CM1"]],
        "activity_name": ["Gate Milestone", "Pre-commissioning Checks", "Functional Testing"],
        "phase": ["Test", "Test", "Test"],
        "status": ["Complete", "In Progress", "Not Started"],
        "percent_complete": [100, 50, 0],
        "current_duration_days": [5, 3, 4],
    })
    start = pd.Timestamp("2026-01-01")
    baseline_result = cpm_engine.run_cpm(activities, duration_col="current_duration_days", start_date=start)
    # Sequential baseline: M2(0-5), CM1(5-8), CM2(8-12) -> finish day 12.
    assert baseline_result.project_finish == pd.Timestamp("2026-01-13")

    risk_snapshots = pd.DataFrame({
        "risk_id": ["R03", "R06", "R99"],
        "snapshot_date": [pd.Timestamp("2026-01-01")] * 3,
        "exposure": [10, 6, 100],
    })

    result = fast_track(
        activities=activities,
        baseline_result=baseline_result,
        project_start="2026-01-01",
        current_before_finish=baseline_result.project_finish,
        risk_snapshots=risk_snapshots,
        portfolio_exposure=50.0,
    )

    # CM2 now starts from CM1's own predecessor (M2), not CM1's finish.
    resequenced = result.activities.set_index("activity_id")
    assert resequenced.loc["CM2", "predecessors"] == ["M2"]
    assert resequenced.loc["CM1", "predecessors"] == ["M2"]  # unchanged

    # M2(0-5), CM1(5-8), CM2(5-9) in parallel with CM1 -> finish day 9.
    assert result.forecast_finish == pd.Timestamp("2026-01-10")
    assert result.days_recovered == 3
    assert result.cost_impact == pytest.approx(FAST_TRACK_COORDINATION_COST)

    # Only R03/R06 (the stated sensitive risks) get the uplift; R99 does not.
    assert result.risk_exposure == pytest.approx(50.0 + (10 + 6) * 0.25)

"""Canned, parametric recovery interventions for the Ridgeline programme.

Three named, stated adjustments to the vendored CPM engine's inputs, each
re-run through the exact same unmodified engine (see engines/schedule/cpm.py).
None of this is a simulation or a machine-learned forecast: every
intervention is a short rule a project controls function could say out loud
in a status meeting, then a rerun of the same forward/backward-pass CPM the
rest of the toolkit already uses.

  1. add_resources  - crash the critical path (expensive, blunt)
  2. fast_track      - re-sequence a stated sequential pair to run in
                        parallel (the lever actually used in the real
                        recovery this repo is modeled on)
  3. do_nothing       - accept the delay and re-baseline; the honest
                        do-nothing comparison point

See recommend.py for how these three get ranked against a given programme
status, and planner.py for how they're run end to end.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from engines.schedule import cpm as cpm_engine
from engines.schedule import metrics as sched

# ---- Add resources (crash the critical path) ---------------------------
# Deliberately the more expensive, less clever lever. This is NOT what was
# actually done in the real recovery this repo is modeled on, that was a
# re-sequencing move (see fast_track below). It's modeled here so the
# recommendation engine has a costly-but-schedule-logic-preserving option to
# weigh against the cheaper re-sequencing move.
CRASH_PCT = 0.30            # cut this share off the REMAINING duration of not-yet-complete critical activities
CRASH_COST_PER_DAY = 5000   # $ per day of schedule recovered, stated and flat, no learning curve modeled

# ---- Re-sequence / fast-track -------------------------------------------
# "Sequential phases are a scheduling assumption, not a physical law": CM1
# (Pre-commissioning Checks) and CM2 (Functional Testing) are linked
# finish-to-start in the source data, but functional-test planning and setup
# doesn't actually require every pre-commissioning check signed off first,
# only the checks for the specific loop under test. No predecessor is
# deleted from the activities that gate this pair (M2, E3 still gate CM1
# exactly as before); only the CM1->CM2 link itself is re-timed so CM2
# starts from the same upstream gate as CM1 instead of waiting on CM1's
# finish.
FAST_TRACK_PAIRS = [("CM1", "CM2")]      # (upstream, downstream): downstream now starts when upstream starts
FAST_TRACK_COORDINATION_COST = 3000      # $ flat: added QA/inspection overhead for running the pair concurrently
FAST_TRACK_RISK_UPLIFT_PCT = 0.25        # exposure uplift applied to the compression-sensitive risks below
FAST_TRACK_SENSITIVE_RISK_IDS = ["R03", "R06"]  # risks explicitly about a compressed commissioning window


@dataclass
class ScenarioResult:
    name: str
    label: str
    activities: pd.DataFrame
    comparison: pd.DataFrame
    forecast_finish: pd.Timestamp
    slip_days: int          # forecast finish vs. the original baseline
    days_recovered: int     # forecast finish pulled back vs. the do-nothing forecast
    cost_impact: float      # incremental $ to apply this intervention (0 if none)
    risk_exposure: float    # portfolio exposure after this intervention's stated effect, if any
    rationale: str          # one sentence, printed alongside the fit score


def _current_cpm(activities: pd.DataFrame, project_start: str) -> cpm_engine.CpmResult:
    return cpm_engine.run_cpm(
        activities, duration_col="current_duration_days", start_date=pd.Timestamp(project_start)
    )


def do_nothing(
    activities: pd.DataFrame,
    baseline_result: cpm_engine.CpmResult,
    project_start: str,
    portfolio_exposure: float,
) -> ScenarioResult:
    """Accept the delay and re-baseline: no schedule change, the honest comparison point."""
    current = _current_cpm(activities, project_start)
    comparison = sched.compare_schedules(activities, baseline_result, current)
    slip = (current.project_finish - baseline_result.project_finish).days

    return ScenarioResult(
        name="do_nothing",
        label="Accept the delay and re-baseline",
        activities=activities,
        comparison=comparison,
        forecast_finish=current.project_finish,
        slip_days=slip,
        days_recovered=0,
        cost_impact=0.0,
        risk_exposure=portfolio_exposure,
        rationale=(
            f"No schedule change: forecast finish stays {current.project_finish.date()}, "
            f"{slip} days late against baseline, at zero incremental cost and no added risk. "
            f"This is the option the other two get measured against, not a lever."
        ),
    )


def add_resources(
    activities: pd.DataFrame,
    baseline_result: cpm_engine.CpmResult,
    project_start: str,
    current_before_finish: pd.Timestamp,
    portfolio_exposure: float,
    current_before_comparison: pd.DataFrame,
) -> ScenarioResult:
    """Crash the critical path: pay to shrink remaining duration on not-yet-complete critical activities."""
    critical_ids = set(current_before_comparison.loc[current_before_comparison["is_critical"], "activity_id"])

    crashed = activities.copy()
    total_days_cut = 0
    for i, row in crashed.iterrows():
        if row["activity_id"] in critical_ids and row["percent_complete"] < 100:
            remaining = row["current_duration_days"] * (1 - row["percent_complete"] / 100)
            cut = remaining * CRASH_PCT
            new_duration = max(1, round(row["current_duration_days"] - cut))
            applied_cut = row["current_duration_days"] - new_duration
            crashed.at[i, "current_duration_days"] = new_duration
            total_days_cut += applied_cut

    current = _current_cpm(crashed, project_start)
    comparison = sched.compare_schedules(crashed, baseline_result, current)
    slip = (current.project_finish - baseline_result.project_finish).days
    days_recovered = (current_before_finish - current.project_finish).days
    cost = total_days_cut * CRASH_COST_PER_DAY

    return ScenarioResult(
        name="add_resources",
        label="Add resources (crash the critical path)",
        activities=crashed,
        comparison=comparison,
        forecast_finish=current.project_finish,
        slip_days=slip,
        days_recovered=days_recovered,
        cost_impact=cost,
        risk_exposure=portfolio_exposure,  # unaffected: extra crew doesn't touch the compression risks below
        rationale=(
            f"Buys back {days_recovered} days by paying for extra crew/shift capacity on the "
            f"still-open critical activities, a stated {CRASH_PCT:.0%} cut to their remaining "
            f"duration at ${CRASH_COST_PER_DAY:,}/day saved, ${cost:,.0f} total. The most "
            f"expensive of the three options, and not the lever actually used in the real "
            f"recovery this tool is modeled on."
        ),
    )


def fast_track(
    activities: pd.DataFrame,
    baseline_result: cpm_engine.CpmResult,
    project_start: str,
    current_before_finish: pd.Timestamp,
    risk_snapshots: pd.DataFrame,
    portfolio_exposure: float,
) -> ScenarioResult:
    """Re-sequence a stated sequential pair to run in parallel. No predecessor is deleted from
    the activities gating the pair, only the pair's own internal ordering is re-timed."""
    resequenced = activities.copy()
    original_pred_map = dict(zip(resequenced["activity_id"], resequenced["predecessors"]))
    pred_map = dict(original_pred_map)
    for upstream, downstream in FAST_TRACK_PAIRS:
        # Read from the original, unmutated map so a chained pair (upstream of
        # one = downstream of another) can't pick up an already-overwritten
        # predecessor list from an earlier iteration of this loop.
        pred_map[downstream] = list(original_pred_map[upstream])
    resequenced["predecessors"] = resequenced["activity_id"].map(pred_map)

    current = _current_cpm(resequenced, project_start)
    comparison = sched.compare_schedules(resequenced, baseline_result, current)
    slip = (current.project_finish - baseline_result.project_finish).days
    days_recovered = (current_before_finish - current.project_finish).days

    latest_date = risk_snapshots["snapshot_date"].max()
    latest = risk_snapshots[risk_snapshots["snapshot_date"] == latest_date]
    sensitive_exposure = latest.loc[latest["risk_id"].isin(FAST_TRACK_SENSITIVE_RISK_IDS), "exposure"].sum()
    uplifted_exposure = portfolio_exposure + sensitive_exposure * FAST_TRACK_RISK_UPLIFT_PCT

    pairs_desc = ", ".join(f"{u}->{d}" for u, d in FAST_TRACK_PAIRS)
    risk_desc = "/".join(FAST_TRACK_SENSITIVE_RISK_IDS)
    return ScenarioResult(
        name="fast_track",
        label="Re-sequence / fast-track",
        activities=resequenced,
        comparison=comparison,
        forecast_finish=current.project_finish,
        slip_days=slip,
        days_recovered=days_recovered,
        cost_impact=FAST_TRACK_COORDINATION_COST,
        risk_exposure=uplifted_exposure,
        rationale=(
            f"Recovers {days_recovered} days by running {pairs_desc} in parallel instead of "
            f"back-to-back, for a stated ${FAST_TRACK_COORDINATION_COST:,} coordination cost, "
            f"far cheaper than crashing, but raises exposure on the two risks that already flag "
            f"a compressed commissioning window ({risk_desc}) by a stated "
            f"{FAST_TRACK_RISK_UPLIFT_PCT:.0%}."
        ),
    )

"""Schedule health metrics: baseline vs current CPM comparison and a composite health score.

Vendored from github.com/alexc-hue/schedule-health-analyzer (src/metrics.py),
unchanged except the import path for the local cpm module.
"""

from __future__ import annotations

import pandas as pd

from engines.schedule import cpm

NEAR_CRITICAL_DAYS = 5    # current float at or below this counts as near-critical
EROSION_THRESHOLD_DAYS = 10  # float lost beyond this counts as "eroded"


def load_activities(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["predecessors"] = df["predecessors"].fillna("").apply(
        lambda s: [p.strip() for p in str(s).split(";") if p.strip()]
    )
    return df


def run_baseline_and_current(activities: pd.DataFrame, project_start: str):
    start = pd.Timestamp(project_start)
    baseline = cpm.run_cpm(activities, duration_col="baseline_duration_days", start_date=start)
    current = cpm.run_cpm(activities, duration_col="current_duration_days", start_date=start)
    return baseline, current


def compare_schedules(activities: pd.DataFrame, baseline: cpm.CpmResult, current: cpm.CpmResult) -> pd.DataFrame:
    merged = (
        activities[["activity_id", "activity_name", "phase", "status", "percent_complete"]]
        .merge(
            baseline.schedule[["activity_id", "early_start", "early_finish", "total_float"]].rename(
                columns={"early_start": "baseline_start", "early_finish": "baseline_finish",
                         "total_float": "baseline_float"}
            ),
            on="activity_id",
        )
        .merge(
            current.schedule[["activity_id", "early_start", "early_finish", "total_float", "is_critical"]].rename(
                columns={"early_start": "current_start", "early_finish": "current_finish",
                         "total_float": "current_float"}
            ),
            on="activity_id",
        )
    )
    merged["slip_days"] = (merged["current_finish"] - merged["baseline_finish"]).dt.days
    merged["float_erosion"] = merged["baseline_float"] - merged["current_float"]
    merged["is_near_critical"] = (~merged["is_critical"]) & (merged["current_float"] <= NEAR_CRITICAL_DAYS)
    return merged


def schedule_health_score(comparison: pd.DataFrame, baseline_finish: pd.Timestamp, current_finish: pd.Timestamp) -> dict:
    slip_days = (current_finish - baseline_finish).days
    schedule_score = max(0.0, 50.0 - slip_days * 1.5)

    eroded_share = (comparison["float_erosion"] >= EROSION_THRESHOLD_DAYS).mean()
    erosion_score = 25.0 * (1 - eroded_share)

    critical_share = (comparison["is_critical"] | comparison["is_near_critical"]).mean()
    concentration_score = 25.0 * (1 - critical_share)

    total = schedule_score + erosion_score + concentration_score
    return {
        "slip_days": slip_days,
        "schedule_score": round(schedule_score, 1),
        "erosion_score": round(erosion_score, 1),
        "concentration_score": round(concentration_score, 1),
        "total_score": round(max(0.0, min(100.0, total)), 1),
        "pct_activities_eroded": round(eroded_share * 100, 1),
        "pct_activities_critical_or_near": round(critical_share * 100, 1),
    }

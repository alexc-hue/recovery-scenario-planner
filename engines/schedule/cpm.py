"""Critical Path Method: forward/backward pass over an activity dependency network.

Vendored unchanged from github.com/alexc-hue/schedule-health-analyzer
(src/cpm.py). Calendar-day durations, no resource or working-calendar
constraints.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class CpmResult:
    schedule: pd.DataFrame  # activity_id, early_start, early_finish, late_start, late_finish, total_float, is_critical
    project_finish: pd.Timestamp


def _topological_order(activities: pd.DataFrame) -> list[str]:
    predecessors = {row.activity_id: set(row.predecessors) for row in activities.itertuples()}
    remaining = dict(predecessors)
    resolved: list[str] = []
    resolved_set: set[str] = set()
    while remaining:
        ready = sorted(aid for aid, preds in remaining.items() if preds <= resolved_set)
        if not ready:
            raise ValueError("Cycle detected in activity network (or an unknown predecessor id).")
        for aid in ready:
            resolved.append(aid)
            resolved_set.add(aid)
            del remaining[aid]
    return resolved


def run_cpm(activities: pd.DataFrame, duration_col: str, start_date: pd.Timestamp) -> CpmResult:
    order = _topological_order(activities)
    duration = dict(zip(activities["activity_id"], activities[duration_col]))
    preds = dict(zip(activities["activity_id"], activities["predecessors"]))

    early_start: dict[str, pd.Timestamp] = {}
    early_finish: dict[str, pd.Timestamp] = {}
    for aid in order:
        es = max((early_finish[p] for p in preds[aid]), default=start_date)
        early_start[aid] = es
        early_finish[aid] = es + pd.Timedelta(days=round(duration[aid]))

    project_finish = max(early_finish.values())

    successors: dict[str, list[str]] = {aid: [] for aid in order}
    for aid, plist in preds.items():
        for p in plist:
            successors[p].append(aid)

    late_start: dict[str, pd.Timestamp] = {}
    late_finish: dict[str, pd.Timestamp] = {}
    for aid in reversed(order):
        lf = min((late_start[s] for s in successors[aid]), default=project_finish)
        late_finish[aid] = lf
        late_start[aid] = lf - pd.Timedelta(days=round(duration[aid]))

    rows = []
    for aid in order:
        total_float = (late_start[aid] - early_start[aid]).days
        rows.append({
            "activity_id": aid,
            "early_start": early_start[aid],
            "early_finish": early_finish[aid],
            "late_start": late_start[aid],
            "late_finish": late_finish[aid],
            "total_float": total_float,
            "is_critical": total_float <= 0,
        })
    return CpmResult(schedule=pd.DataFrame(rows), project_finish=project_finish)

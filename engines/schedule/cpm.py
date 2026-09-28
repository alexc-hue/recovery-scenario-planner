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
    """Activities in dependency order, one pass over the network.

    Activities are released in rounds: round 0 is everything with no
    predecessors, and each later round is everything whose last predecessor
    was released in the round before. Within a round, activity IDs are sorted,
    so the order is the same on every run. Each link is visited once, so the
    cost grows with activities + links rather than activities x rounds.
    """
    predecessors = {row.activity_id: set(row.predecessors) for row in activities.itertuples()}
    waiting_on = {aid: len(preds) for aid, preds in predecessors.items()}
    successors: dict[str, list[str]] = {}
    for aid, preds in predecessors.items():
        for p in preds:
            successors.setdefault(p, []).append(aid)

    resolved: list[str] = []
    ready = sorted(aid for aid, count in waiting_on.items() if count == 0)
    while ready:
        resolved.extend(ready)
        released = []
        for aid in ready:
            for succ in successors.get(aid, ()):
                waiting_on[succ] -= 1
                if waiting_on[succ] == 0:
                    released.append(succ)
        ready = sorted(released)
    if len(resolved) < len(predecessors):
        # Anything left is on a cycle, or waits on a predecessor ID that isn't
        # in the activity list, so it can never be released.
        raise ValueError("Cycle detected in activity network (or an unknown predecessor id).")
    return resolved


def run_cpm(activities: pd.DataFrame, duration_col: str, start_date: pd.Timestamp) -> CpmResult:
    if activities.empty:
        raise ValueError("No activities found in activities.csv")

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

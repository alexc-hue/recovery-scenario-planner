"""Risk trend metrics: exposure over time, per-risk trajectory, mitigation effectiveness.

Vendored unchanged from github.com/alexc-hue/risk-trend-tracker
(src/metrics.py).
"""

from __future__ import annotations

import pandas as pd

TREND_THRESHOLD = 2  # exposure delta at or beyond this counts as worsening/improving, not stable


def load_snapshots(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["snapshot_date", "mitigation_due_date"])
    df["exposure"] = df["probability"] * df["impact"]
    return df.sort_values(["risk_id", "snapshot_date"]).reset_index(drop=True)


def portfolio_exposure_trend(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Total exposure across all risks present at each snapshot date."""
    return (
        snapshots.groupby("snapshot_date")["exposure"]
        .sum()
        .reset_index()
        .rename(columns={"exposure": "total_exposure"})
        .sort_values("snapshot_date")
    )


CLOSED_STATUSES = {"closed", "resolved"}


def _delta_trend(delta: float) -> str:
    if delta >= TREND_THRESHOLD:
        return "Worsening"
    if delta <= -TREND_THRESHOLD:
        return "Improving"
    return "Stable"


def per_risk_trajectory(snapshots: pd.DataFrame, latest_snapshot: pd.Timestamp) -> pd.DataFrame:
    """First vs. last recorded exposure per risk, classified as a trend."""
    has_status = "status" in snapshots.columns and snapshots["status"].notna().any()
    rows = []
    for risk_id, group in snapshots.groupby("risk_id"):
        group = group.sort_values("snapshot_date")
        first, last = group.iloc[0], group.iloc[-1]
        delta = last["exposure"] - first["exposure"]
        missing_from_latest = last["snapshot_date"] < latest_snapshot
        last_status = str(last["status"]).strip().lower() if has_status and pd.notna(last.get("status")) else ""

        if last_status in CLOSED_STATUSES:
            # The register's own status field says this risk is done -- trust it
            # regardless of whether it's still being reported in later snapshots.
            trend = "Closed/Resolved"
        elif missing_from_latest:
            if has_status:
                # Status data exists but never said Closed/Resolved, so a risk
                # dropping out of the latest snapshot is unconfirmed, not closed.
                trend = "Dropped (Unconfirmed)"
            else:
                # No status data at all: fall back to the old absence-based inference.
                trend = "Closed/Resolved"
        else:
            trend = _delta_trend(delta)
        rows.append({
            "risk_id": risk_id,
            "description": last["description"],
            "category": last["category"],
            "first_snapshot": first["snapshot_date"],
            "first_exposure": first["exposure"],
            "last_snapshot": last["snapshot_date"],
            "last_exposure": last["exposure"],
            "delta": delta,
            "trend": trend,
        })
    return pd.DataFrame(rows).sort_values("delta", ascending=False).reset_index(drop=True)


def mitigation_effectiveness(snapshots: pd.DataFrame) -> pd.DataFrame:
    """For risks with a mitigation due date, compare avg exposure before vs after it."""
    rows = []
    for risk_id, group in snapshots.groupby("risk_id"):
        # Use the most recently recorded due date, not the earliest -- a later
        # reschedule of the mitigation deadline should not be silently ignored.
        due_series = group["mitigation_due_date"].dropna()
        due = due_series.iloc[-1] if not due_series.empty else pd.NaT
        if pd.isna(due):
            continue
        before = group[group["snapshot_date"] < due]["exposure"]
        # Strictly after: a snapshot dated exactly on the due date has zero
        # elapsed observation time and shouldn't count as post-mitigation.
        after = group[group["snapshot_date"] > due]["exposure"]
        if before.empty or after.empty:
            verdict = "Too early to assess"
            avg_before = before.mean() if not before.empty else float("nan")
            avg_after = after.mean() if not after.empty else float("nan")
        else:
            avg_before, avg_after = before.mean(), after.mean()
            if avg_after < avg_before:
                verdict = "Effective"
            elif avg_after > avg_before:
                verdict = "Ineffective"
            else:
                verdict = "Held Steady"
        rows.append({
            "risk_id": risk_id,
            "description": group["description"].iloc[0],
            "mitigation_due_date": due,
            "avg_exposure_before": avg_before,
            "avg_exposure_after": avg_after,
            "verdict": verdict,
        })
    return pd.DataFrame(rows)


def risk_trajectory_score(
    exposure_trend: pd.DataFrame, effectiveness: pd.DataFrame, snapshots: pd.DataFrame
) -> dict:
    first_total = exposure_trend["total_exposure"].iloc[0]
    last_total = exposure_trend["total_exposure"].iloc[-1]
    pct_change = (last_total - first_total) / first_total * 100 if first_total else 0.0

    # Churn control: the raw portfolio totals above move whenever risks are
    # added to or dropped from the register, which isn't the same thing as
    # existing risks getting better or worse. Score the trend only over risks
    # present at BOTH the earliest and latest snapshot dates, so register
    # growth/shrinkage can't masquerade as a real trajectory change.
    first_date = snapshots["snapshot_date"].min()
    last_date = snapshots["snapshot_date"].max()
    first_snap = snapshots[snapshots["snapshot_date"] == first_date]
    last_snap = snapshots[snapshots["snapshot_date"] == last_date]
    shared_ids = set(first_snap["risk_id"]) & set(last_snap["risk_id"])
    shared_first_total = first_snap.loc[first_snap["risk_id"].isin(shared_ids), "exposure"].sum()
    shared_last_total = last_snap.loc[last_snap["risk_id"].isin(shared_ids), "exposure"].sum()
    shared_pct_change = (
        (shared_last_total - shared_first_total) / shared_first_total * 100
        if shared_first_total
        else 0.0
    )
    trend_score = max(0.0, 50.0 - max(0.0, shared_pct_change) * 1.5)

    assessable = effectiveness[effectiveness["verdict"] != "Too early to assess"]
    effective_count = (assessable["verdict"] == "Effective").sum()
    mitigation_score = (
        50.0 * effective_count / len(assessable) if len(assessable) else 25.0  # neutral if none assessable
    )

    total = trend_score + mitigation_score
    return {
        "first_total_exposure": first_total,
        "last_total_exposure": last_total,
        "exposure_pct_change": round(pct_change, 1),
        "shared_risk_count": len(shared_ids),
        "shared_first_exposure": shared_first_total,
        "shared_last_exposure": shared_last_total,
        "shared_exposure_pct_change": round(shared_pct_change, 1),
        "trend_score": round(trend_score, 1),
        "mitigation_score": round(mitigation_score, 1),
        "total_score": round(max(0.0, min(100.0, total)), 1),
        "assessable_mitigations": len(assessable),
        "effective_mitigations": int(effective_count),
    }

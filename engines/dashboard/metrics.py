"""Earned value, schedule, and risk metrics for the project controls dashboard.

Vendored unchanged from github.com/alexc-hue/project-controls-dashboard
(src/metrics.py) so this engine is self-contained and runnable without
cloning that repo alongside it. See that repo for the original context,
tests, and standalone CLI.
"""

from __future__ import annotations

import pandas as pd


def load_timeseries(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["period_label"] = pd.to_datetime(df["period_label"], format="%Y-%m")
    return df.sort_values("period").reset_index(drop=True)


def actuals_only(df: pd.DataFrame) -> pd.DataFrame:
    """Rows up to and including the current status date (where EV/AC are known)."""
    return df.dropna(subset=["earned_value_cum", "actual_cost_cum"]).copy()


def add_performance_indices(df: pd.DataFrame) -> pd.DataFrame:
    """Attach SPI/CPI/SV/CV computed at each reported period (cumulative basis)."""
    out = df.copy()
    out["sv"] = out["earned_value_cum"] - out["planned_value_cum"]
    out["cv"] = out["earned_value_cum"] - out["actual_cost_cum"]
    out["spi"] = out["earned_value_cum"] / out["planned_value_cum"]
    out["cpi"] = out["earned_value_cum"] / out["actual_cost_cum"]
    return out


def project_summary(df: pd.DataFrame, bac: float) -> dict:
    """Headline EVM figures as of the latest period with actuals."""
    latest = add_performance_indices(actuals_only(df)).iloc[-1]

    pv, ev, ac = latest["planned_value_cum"], latest["earned_value_cum"], latest["actual_cost_cum"]
    spi, cpi = latest["spi"], latest["cpi"]

    eac = bac / cpi
    etc = eac - ac
    vac = bac - eac
    tcpi = (bac - ev) / (bac - ac) if (bac - ac) else float("nan")

    return {
        "status_period": latest["period_label"].strftime("%Y-%m"),
        "bac": bac,
        "pv": pv,
        "ev": ev,
        "ac": ac,
        "sv": ev - pv,
        "sv_pct": (ev - pv) / pv * 100,
        "cv": ev - ac,
        "cv_pct": (ev - ac) / ev * 100,
        "spi": spi,
        "cpi": cpi,
        "percent_complete": ev / bac * 100,
        "eac": eac,
        "etc": etc,
        "vac": vac,
        "tcpi": tcpi,
    }


def load_milestones(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["planned_date", "current_date"])
    df["slip_days"] = (df["current_date"] - df["planned_date"]).dt.days
    df["milestone_status"] = df["slip_days"].apply(
        lambda d: "On Track" if d <= 0 else ("At Risk" if d <= 14 else "Delayed")
    )
    return df


def load_risk_register(path: str, status_date: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["mitigation_due_date"])
    df["exposure"] = df["probability"] * df["impact"]
    status_dt = pd.Timestamp(status_date)
    df["overdue"] = (df["status"] != "Closed") & (df["mitigation_due_date"] < status_dt)
    return df.sort_values("exposure", ascending=False).reset_index(drop=True)


def load_change_register(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date_raised"])
    return df.sort_values("cost_impact", ascending=False).reset_index(drop=True)


def change_impact_summary(changes: pd.DataFrame, bac: float) -> dict:
    """Cost/schedule impact of the change register, split approved vs pending.

    Reported alongside the EVM summary, not fed back into CPI/EAC: this keeps
    performance variance (how well the work is being executed) separate from
    scope-change variance (how much the baseline itself has moved), which is
    the distinction a change register is actually for.
    """
    approved = changes[changes["status"] == "Approved"]
    pending = changes[changes["status"] == "Pending"]
    approved_cost = approved["cost_impact"].sum()
    return {
        "approved_cost_impact": approved_cost,
        "approved_schedule_days": int(approved["schedule_impact_days"].sum()),
        "revised_budget": bac + approved_cost,
        "pending_count": len(pending),
        "pending_cost_exposure": pending["cost_impact"].sum(),
        "pending_schedule_exposure_days": int(pending["schedule_impact_days"].sum()),
    }


def forecast_completion_date(
    milestones: pd.DataFrame, spi: float, project_start: str, planned_finish: str
) -> pd.Timestamp:
    """Simple SPI-based forecast: stretch remaining planned duration by 1/SPI."""
    start = pd.Timestamp(project_start)
    planned_end = pd.Timestamp(planned_finish)
    total_planned_days = (planned_end - start).days
    forecast_days = total_planned_days / spi
    return start + pd.Timedelta(days=round(forecast_days))

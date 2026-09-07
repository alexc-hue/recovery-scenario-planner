"""Stated decision-rule table: rank the three canned interventions against a
given programme status (SPI/CPI, critical-path delay, top risk exposure).

Not a model, not ML. Every scenario gets a 0-100 fit score built from three
named, capped components, each explainable in one sentence, the same
"a score a sponsor can't have explained back to them in one sentence isn't
useful" standard schedule-health-analyzer's Schedule Health Score and
risk-trend-tracker's Risk Trajectory Score already hold themselves to:

  - Recovery   (0-40): how much of the delay this option actually buys back.
  - Cost       (0-30): how much of a stated, CPI-linked spending ceiling it uses.
  - Risk       (0-30): how much headroom is left against a stated risk-tolerance band.

One additional stated rule sits on top: accepting the delay when SPI is
already below the common EVM "amber" threshold (0.90) gets a flat penalty,
since passively stacking more slip onto a programme already flagged at risk
is a judgment call a rule table should surface, not something a sponsor
should default into by omission.
"""

from __future__ import annotations

from src.interventions import ScenarioResult

RISK_TOLERANCE_PCT = 0.30       # exposure can rise up to this share before the risk component hits zero
SPI_FLOOR = 0.90                # the common EVM "amber" threshold: SPI below this counts as already at risk
DO_NOTHING_SPI_PENALTY = 15.0   # flat penalty applied to accepting the delay when SPI is below the floor


def _cost_ceiling(cpi: float) -> float:
    """How much a sponsor at this cost performance would plausibly tolerate spending on recovery.

    A stated, banded rule: the worse CPI already is, the less appetite there
    is to spend more money buying back schedule.
    """
    if cpi >= 0.95:
        return 20000.0
    if cpi >= 0.85:
        return 10000.0
    return 4000.0


def score_scenario(scenario: ScenarioResult, slip_before: int, spi: float, cpi: float, baseline_exposure: float) -> dict:
    recovery = 40.0 * max(0.0, min(1.0, scenario.days_recovered / slip_before)) if slip_before else 0.0

    ceiling = _cost_ceiling(cpi)
    cost_component = 30.0 * max(0.0, 1.0 - scenario.cost_impact / ceiling)

    risk_increase_pct = (
        (scenario.risk_exposure - baseline_exposure) / baseline_exposure if baseline_exposure else 0.0
    )
    risk_component = 30.0 * max(0.0, 1.0 - max(0.0, risk_increase_pct) / RISK_TOLERANCE_PCT)

    total = recovery + cost_component + risk_component
    penalty_applied = False
    if scenario.name == "do_nothing" and spi < SPI_FLOOR:
        total = max(0.0, total - DO_NOTHING_SPI_PENALTY)
        penalty_applied = True

    return {
        "name": scenario.name,
        "label": scenario.label,
        "recovery_component": round(recovery, 1),
        "cost_component": round(cost_component, 1),
        "risk_component": round(risk_component, 1),
        "spi_penalty_applied": penalty_applied,
        "total_score": round(min(100.0, total), 1),
        "rationale": scenario.rationale,
    }


def rank_scenarios(
    scenarios: list[ScenarioResult], slip_before: int, spi: float, cpi: float, baseline_exposure: float
) -> list[dict]:
    scored = [score_scenario(s, slip_before, spi, cpi, baseline_exposure) for s in scenarios]
    return sorted(scored, key=lambda r: r["total_score"], reverse=True)


def print_recommendation(ranked: list[dict], spi: float, cpi: float, slip_before: int, baseline_exposure: float) -> None:
    print("=" * 68)
    print("RECOVERY OPTION RANKING")
    print(
        f"Current status: SPI {spi:.2f}  CPI {cpi:.2f}  "
        f"critical-path delay {slip_before:+d}d  "
        f"portfolio risk exposure {baseline_exposure:.0f}"
    )
    print("=" * 68)
    print()
    for i, r in enumerate(ranked, start=1):
        print(f"{i}. {r['label']}  -  Fit score {r['total_score']}/100")
        print(
            f"   Recovery {r['recovery_component']}/40   "
            f"Cost {r['cost_component']}/30   "
            f"Risk {r['risk_component']}/30"
            + ("   (SPI penalty applied)" if r["spi_penalty_applied"] else "")
        )
        print(f"   {r['rationale']}")
        print()

    top = ranked[0]
    print(f"RECOMMENDATION: {top['label']} (fit score {top['total_score']}/100).")

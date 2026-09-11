"""Tests for src/recommend.py: the stated 0-100 fit score (_cost_ceiling,
score_scenario). Small hand-built ScenarioResult instances, not the repo's
sample data.
"""

from __future__ import annotations

import pytest

from src.interventions import ScenarioResult
from src.recommend import _cost_ceiling, score_scenario


def _scenario(name, days_recovered, cost_impact, risk_exposure):
    return ScenarioResult(
        name=name, label=name, activities=None, comparison=None, forecast_finish=None,
        slip_days=0, days_recovered=days_recovered, cost_impact=cost_impact,
        risk_exposure=risk_exposure, rationale="test",
    )


def test_cost_ceiling_bands():
    assert _cost_ceiling(0.98) == 20000.0
    assert _cost_ceiling(0.95) == 20000.0  # boundary: >= 0.95
    assert _cost_ceiling(0.90) == 10000.0  # boundary: >= 0.85, < 0.95
    assert _cost_ceiling(0.85) == 10000.0  # boundary: >= 0.85
    assert _cost_ceiling(0.50) == 4000.0


def test_score_scenario_basic_components():
    scenario = _scenario("fast_track", days_recovered=5, cost_impact=1000, risk_exposure=55)
    result = score_scenario(scenario, slip_before=10, spi=0.95, cpi=0.95, baseline_exposure=50)

    assert result["recovery_component"] == pytest.approx(20.0)  # 40 * 5/10
    assert result["cost_component"] == pytest.approx(28.5)  # 30 * (1 - 1000/20000)
    assert result["risk_component"] == pytest.approx(20.0)  # 30 * (1 - 0.10/0.30)
    assert result["spi_penalty_applied"] is False
    assert result["total_score"] == pytest.approx(68.5)


def test_score_scenario_do_nothing_gets_spi_penalty_when_amber():
    scenario = _scenario("do_nothing", days_recovered=0, cost_impact=0, risk_exposure=50)
    result = score_scenario(scenario, slip_before=10, spi=0.85, cpi=0.95, baseline_exposure=50)

    # recovery=0, cost=30 (no spend), risk=30 (no increase) -> 60, then the
    # flat 15-point penalty for accepting a delay while SPI is already amber.
    assert result["spi_penalty_applied"] is True
    assert result["total_score"] == pytest.approx(45.0)


def test_score_scenario_non_do_nothing_never_gets_spi_penalty():
    scenario = _scenario("add_resources", days_recovered=0, cost_impact=0, risk_exposure=50)
    result = score_scenario(scenario, slip_before=10, spi=0.5, cpi=0.95, baseline_exposure=50)
    assert result["spi_penalty_applied"] is False


def test_score_scenario_zero_slip_before_guards_recovery_component():
    scenario = _scenario("fast_track", days_recovered=0, cost_impact=0, risk_exposure=50)
    result = score_scenario(scenario, slip_before=0, spi=1.0, cpi=1.0, baseline_exposure=50)
    assert result["recovery_component"] == pytest.approx(0.0)


def test_score_scenario_risk_component_floors_at_zero_beyond_tolerance():
    """An exposure increase beyond RISK_TOLERANCE_PCT (30%) must floor the
    risk component at zero, not go negative."""
    scenario = _scenario("fast_track", days_recovered=0, cost_impact=0, risk_exposure=100)
    result = score_scenario(scenario, slip_before=10, spi=1.0, cpi=1.0, baseline_exposure=50)
    assert result["risk_component"] == pytest.approx(0.0)

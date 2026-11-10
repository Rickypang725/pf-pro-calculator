"""Golden-test contract for src/pfpro/engine.py.

Every expected value in vectors.json was independently recomputed from the
formulas in docs/02-functional-spec.md and matches the reference tool's live
UI to full precision (verified 2026-11-09). DO NOT weaken these assertions;
implement the engine until they pass.

Engine API expected by this contract (implementer may adjust names only by
updating this file's imports in the same commit):

    from pfpro.engine import (
        solve_irr,            # (cashflows: list[float]) -> float | None
        effective_rate,       # (hibor_1m, h_spread, prime_rate, p_spread) -> float
        project,              # (params: ProjectionParams, table) -> list[Row]
        stress_matrix,        # (params, table, rates, ratios, stress_year) -> list[list[Cell]]
    )

where ProjectionParams carries the base_params fields of vectors.json and a
Row exposes at least: year, interest, surrender, gross, net, irr, cashflows.
Any equivalent structure is fine as long as the assertions below hold.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pytest

VECTORS = json.loads((Path(__file__).parent / "vectors.json").read_text())
BASE = VECTORS["base_params"]
TABLE = VECTORS["benefit_table"]
EXP = VECTORS["expected"]

TOL = 1e-6  # full-precision agreement with the reference model


@dataclass
class Params:
    total_premium: float
    discount_percent: float
    surrender0_percent: float
    ltv_percent: float
    bank_fx: float
    fwd_fx: float
    rate_brackets: list
    achievement_percent: float


PARAMS = Params(**BASE)


# ---------------------------------------------------------------- solve_irr
def test_solve_irr_golden_values():
    solve_irr = _engine_attr("solve_irr")
    # Year-7 cashflow from the verified model: [outlay, -interest x6, final]
    h = EXP["outlay_usd"]
    z = EXP["annual_interest"]
    final7 = EXP["year7"]["gross"] - z
    irr7 = solve_irr([h] + [-z] * 6 + [final7])
    assert irr7 == pytest.approx(EXP["year7"]["irr"], abs=TOL)

    final8 = EXP["year8"]["gross"] - z
    irr8 = solve_irr([h] + [-z] * 7 + [final8])
    assert irr8 == pytest.approx(EXP["year8"]["irr"], abs=TOL)


def test_solve_irr_returns_none_without_sign_change():
    solve_irr = _engine_attr("solve_irr")
    # All-negative cashflows (e.g. early surrender years) must give None,
    # matching the reference tool's em-dash display.
    assert solve_irr([-1000, -100, -50]) is None
    assert solve_irr([1000, 100, 50]) is None
    assert solve_irr([0, 0, 0]) is None


def test_solve_irr_simple_known_rate():
    solve_irr = _engine_attr("solve_irr")
    # 2-year investment: -1000 now, +500 in yr 1, +600 in yr 2
    # exact IRR = 1/x - 1 where x = (-5 + sqrt(265)) / 12 ~ 0.0639
    irr = solve_irr([-1000, 500, 600])
    assert irr is not None
    assert irr == pytest.approx(0.0639, abs=1e-3)


# ----------------------------------------------------------- effective_rate
def test_effective_rate_cases():
    effective_rate = _engine_attr("effective_rate")
    for case in VECTORS["effective_rate_cases"]:
        got = effective_rate(
            case["hibor_1m"], case["h_spread"], case["prime_rate"], case["p_spread"]
        )
        assert got == pytest.approx(case["expected"], abs=TOL), case


# ------------------------------------------------------------------ project
def test_loan_outlay_leverage():
    rows = _project()
    assert _loan_usd(PARAMS) == pytest.approx(EXP["loan_usd"], abs=TOL)
    outlay = _outlay_usd(PARAMS)
    assert outlay == pytest.approx(EXP["outlay_usd"], abs=TOL)
    assert outlay * PARAMS.fwd_fx == pytest.approx(EXP["outlay_hkd"], abs=1e-4)
    assert _loan_usd(PARAMS) * PARAMS.bank_fx == pytest.approx(EXP["loan_hkd"], abs=1e-4)
    assert PARAMS.total_premium / abs(outlay) == pytest.approx(EXP["leverage"], abs=TOL)
    assert len(rows) == len(TABLE)


def test_projection_yearly_golden_rows():
    rows = {r.year: r for r in _project()}
    for year_key in ["year4", "year5", "year7", "year8", "year9", "year10", "year20"]:
        year = int(year_key[4:])
        row = rows[year]
        exp = EXP[year_key]
        assert row.interest == pytest.approx(EXP["annual_interest"], abs=TOL)
        assert row.surrender == pytest.approx(exp["surrender"], abs=TOL)
        assert row.gross == pytest.approx(exp["gross"], abs=TOL)
        assert row.net == pytest.approx(exp["net"], abs=TOL)
        if exp["irr"] is None:
            assert row.irr is None
        else:
            assert row.irr == pytest.approx(exp["irr"], abs=TOL)


def test_projection_cashflow_shape():
    # IRR must be derivable from the row's own cashflows: [outlay, -interest
    # x (year-1), gross - interest]. This pins down the *definition*, not
    # just the number.
    solve_irr = _engine_attr("solve_irr")
    rows = {r.year: r for r in _project()}
    for year, row in rows.items():
        assert len(row.cashflows) == year + 1
        assert row.cashflows[0] == pytest.approx(EXP["outlay_usd"], abs=TOL)
        for cf in row.cashflows[1:year]:
            assert cf == pytest.approx(-EXP["annual_interest"], abs=TOL)
        assert row.cashflows[-1] == pytest.approx(row.gross - row.interest, abs=TOL)
        if row.irr is not None:
            assert solve_irr(row.cashflows) == pytest.approx(row.irr, abs=1e-9)


def test_bracket_lookup():
    project = _engine_attr("project")
    brackets = VECTORS["bracket_lookup_cases"][0]
    for case in brackets["cases"]:
        params = Params(**{**BASE, "rate_brackets": brackets["brackets"]})
        one_year_table = [{"year": case["year"], "guaranteed": 75000,
                           "reversionary": 0, "special": 0}]
        rows = project(params, one_year_table)
        assert rows[0].interest == pytest.approx(
            EXP["loan_usd"] * case["expected_rate"] / 100, abs=1e-4
        ), case


# ----------------------------------------------------------- stress_matrix
def test_stress_matrix_golden_cells():
    stress_matrix = _engine_attr("stress_matrix")
    rates = sorted({c["rate"] for c in VECTORS["stress_matrix_cells"]})
    ratios = sorted({c["achievement"] for c in VECTORS["stress_matrix_cells"]}, reverse=True)
    stress_year = VECTORS["stress_matrix_cells"][0]["stress_year"]
    matrix = stress_matrix(PARAMS, TABLE, rates, ratios, stress_year)

    # matrix layout: one row per achievement ratio, one column per rate
    assert matrix.achievement_rows == ratios
    assert len(matrix.rows) == len(ratios)
    assert all(len(row) == len(rates) for row in matrix.rows)
    for cell_case in VECTORS["stress_matrix_cells"]:
        i = ratios.index(cell_case["achievement"])
        j = rates.index(cell_case["rate"])
        cell = matrix.rows[i][j]
        assert cell.irr is not None
        assert cell.irr * 100 == pytest.approx(cell_case["irr_percent"], abs=0.005), cell_case


def test_stress_matrix_inserts_current_rate_column():
    # Reference behaviour: if the current rate is not on the 2.00-5.00 grid,
    # it is inserted and the column list stays sorted.
    stress_matrix = _engine_attr("stress_matrix")
    grid = VECTORS["rate_columns"]
    current = BASE["rate_brackets"][0]["rate"]  # 4.11
    assert current not in grid
    matrix = stress_matrix(PARAMS, TABLE, grid, [100], 20)
    assert matrix.rate_columns == sorted(grid + [current])


# ------------------------------------------------------------------ helpers
def _engine_attr(name):
    try:
        import pfpro.engine as engine
    except ImportError as exc:  # pragma: no cover - guidance for the agent
        pytest.fail(f"pfpro.engine not importable yet: {exc}. Implement M0 first.")
    assert hasattr(engine, name), f"engine.{name} missing"
    return getattr(engine, name)


def _loan_usd(p: Params) -> float:
    return p.total_premium * p.surrender0_percent / 100 * p.ltv_percent / 100


def _outlay_usd(p: Params) -> float:
    loan = _loan_usd(p)
    return -((p.total_premium * (1 - p.discount_percent / 100)) * p.fwd_fx
             - loan * p.bank_fx) / p.fwd_fx


def _project():
    project = _engine_attr("project")
    return project(PARAMS, TABLE)

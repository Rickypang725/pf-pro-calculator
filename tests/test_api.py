"""API-layer tests for src/pfpro/api.py (FastAPI TestClient).

Covers the M1 acceptance points: the three endpoints behave correctly,
invalid input is rejected with 422, golden-vector values survive the
JSON round-trip, every response carries the §7 disclaimer, and the
OpenAPI document is served. Engine-level tests (test_engine.py) must
keep passing unchanged.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pfpro.api import DISCLAIMER, app

VECTORS = json.loads((Path(__file__).parent / "vectors.json").read_text())
BASE = VECTORS["base_params"]
TABLE = VECTORS["benefit_table"]
EXPECTED = VECTORS["expected"]

client = TestClient(app)


def _projection_payload() -> dict:
    return {**BASE, "table": TABLE}


def _stress_payload() -> dict:
    return {
        **_projection_payload(),
        "rates": VECTORS["rate_columns"],
        "ratios": VECTORS["achievement_rows"],
        "stress_year": VECTORS["stress_matrix_cells"][0]["stress_year"],
    }


# ------------------------------------------------------------------ healthz
def test_healthz_ok():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ------------------------------------------------------------- openapi docs
def test_openapi_documentation_available():
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert {"/projection", "/stress", "/healthz"} <= set(spec.json()["paths"])


# ---------------------------------------------------------------- projection
def test_projection_golden_values_roundtrip():
    response = client.post("/projection", json=_projection_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["disclaimer"] == DISCLAIMER
    rows = {row["year"]: row for row in body["rows"]}
    assert len(body["rows"]) == len(TABLE)
    assert rows[20]["net"] == pytest.approx(EXPECTED["year20"]["net"], abs=1e-6)
    assert rows[20]["irr"] == pytest.approx(EXPECTED["year20"]["irr"], abs=1e-6)
    assert rows[4]["irr"] is None  # no sign change -> null -> "—" in the UI
    assert rows[10]["cashflows"][0] == pytest.approx(EXPECTED["outlay_usd"], abs=1e-6)
    assert len(rows[10]["cashflows"]) == 11


@pytest.mark.parametrize(
    "patch",
    [
        {"ltv_percent": 101},  # 0 < LTV <= 100
        {"ltv_percent": 0},
        {"bank_fx": 0},  # fx > 0
        {"fwd_fx": -7.85},
        {"total_premium": 0},
        {"discount_percent": 101},  # percentages within 0..100
        {"surrender0_percent": -1},
        {"achievement_percent": -5},
        {"rate_brackets": [{"end_year": 0, "rate": -1}]},  # rate >= 0
        {"rate_brackets": []},  # at least one segment
        {"rate_brackets": [{"end_year": 0, "rate": 1}] * 4},  # at most three
        {"rate_brackets": [{"end_year": 10, "rate": 1}, {"end_year": 5, "rate": 2}]},
        {"rate_brackets": [{"end_year": 0, "rate": 1}, {"end_year": 5, "rate": 2}]},
    ],
    ids=[
        "ltv-above-100",
        "ltv-zero",
        "bank-fx-zero",
        "fwd-fx-negative",
        "premium-zero",
        "discount-above-100",
        "surrender-negative",
        "achievement-negative",
        "bracket-rate-negative",
        "brackets-empty",
        "brackets-too-many",
        "brackets-not-increasing",
        "open-segment-not-last",
    ],
)
def test_projection_range_validation(patch):
    response = client.post("/projection", json=_projection_payload() | patch)
    assert response.status_code == 422, patch


@pytest.mark.parametrize(
    "table",
    [
        [],  # at least one year
        [{"year": 0, "guaranteed": 1, "reversionary": 0, "special": 0}],  # positive years
        [{"year": -3, "guaranteed": 1, "reversionary": 0, "special": 0}],
        [{"year": 1, "guaranteed": -1, "reversionary": 0, "special": 0}],  # amounts >= 0
        [  # strictly increasing years
            {"year": 2, "guaranteed": 1, "reversionary": 0, "special": 0},
            {"year": 1, "guaranteed": 1, "reversionary": 0, "special": 0},
        ],
    ],
    ids=["empty", "year-zero", "year-negative", "amount-negative", "years-unsorted"],
)
def test_projection_table_validation(table):
    response = client.post("/projection", json=_projection_payload() | {"table": table})
    assert response.status_code == 422, table


# --------------------------------------------------------------------- stress
def test_stress_golden_cells_roundtrip():
    response = client.post("/stress", json=_stress_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["disclaimer"] == DISCLAIMER
    columns = body["rate_columns"]
    achievement_rows = body["achievement_rows"]
    assert achievement_rows == VECTORS["achievement_rows"]
    # current rate (4.11) is off the 2.00-5.00 grid and gets inserted
    assert columns == sorted(set(VECTORS["rate_columns"]) | {4.11})
    assert len(body["rows"]) == len(achievement_rows)
    assert all(len(row) == len(columns) for row in body["rows"])
    for case in VECTORS["stress_matrix_cells"]:
        i = achievement_rows.index(case["achievement"])
        j = columns.index(case["rate"])
        cell = body["rows"][i][j]
        assert cell["irr"] is not None
        assert cell["irr"] * 100 == pytest.approx(case["irr_percent"], abs=0.005)


@pytest.mark.parametrize(
    "patch",
    [
        {"rates": []},
        {"rates": [2.0, -0.25]},
        {"ratios": []},
        {"ratios": [0]},
        {"ratios": [100.5]},
        {"stress_year": 0},
    ],
    ids=[
        "rates-empty",
        "rates-negative",
        "ratios-empty",
        "ratio-zero",
        "ratio-above-100",
        "stress-year-zero",
    ],
)
def test_stress_range_validation(patch):
    response = client.post("/stress", json=_stress_payload() | patch)
    assert response.status_code == 422, patch

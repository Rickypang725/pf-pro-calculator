"""FastAPI layer over the pfpro calculation engine (docs/03-roadmap.md M1).

The engine stays pure (standard library only); this module adds Pydantic
request validation and JSON endpoints on top of it. Endpoints:

- ``POST /projection`` — year-by-year projection for a case.
- ``POST /stress``     — IRR stress matrix over rates x fulfilment ratios.
- ``GET  /healthz``    — liveness probe.

Every response carries the disclaimer text required by
docs/02-functional-spec.md §7.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Compliance text mandated by docs/02-functional-spec.md §7 for every output.
DISCLAIMER = (
    "Illustrative figures. Returns exclude bank fees and retained-asset "
    "opportunity costs. FX rates are assumptions. Past fulfilment ratios "
    "are not indicative of future performance. Final loan terms subject to "
    "bank confirmation."
)

NonNegRate = Annotated[float, Field(ge=0.0)]
AchvPercent = Annotated[float, Field(gt=0.0, le=100.0)]


class RateBracketIn(BaseModel):
    """One segment of the loan's piecewise rate schedule.

    ``end_year`` is the last policy year the segment applies to; ``0`` marks
    the open-ended final segment. ``rate`` is a percentage, >= 0.
    """

    end_year: int = Field(ge=0)
    rate: NonNegRate


class BenefitEntry(BaseModel):
    """One policy year's benefit illustration row (amounts in USD, >= 0)."""

    year: int = Field(gt=0)
    guaranteed: float = Field(ge=0.0)
    reversionary: float = Field(ge=0.0)
    special: float = Field(ge=0.0)


class ProjectionRequest(BaseModel):
    """Inputs for POST /projection; field ranges per docs/01-architecture.md."""

    total_premium: float = Field(gt=0.0)
    discount_percent: float = Field(ge=0.0, le=100.0)
    surrender0_percent: float = Field(ge=0.0, le=100.0)
    ltv_percent: float = Field(gt=0.0, le=100.0)
    bank_fx: float = Field(gt=0.0)
    fwd_fx: float = Field(gt=0.0)
    rate_brackets: list[RateBracketIn] = Field(min_length=1, max_length=3)
    achievement_percent: float = Field(ge=0.0)
    table: list[BenefitEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_structure(self) -> ProjectionRequest:
        ends = [b.end_year for b in self.rate_brackets]
        if ends.count(0) > 1:
            raise ValueError("rate_brackets: at most one open segment (end_year=0)")
        if 0 in ends and ends[-1] != 0:
            raise ValueError("rate_brackets: the open segment (end_year=0) must be last")
        closed = [e for e in ends if e != 0]
        if closed != sorted(closed) or len(set(closed)) != len(closed):
            raise ValueError("rate_brackets: end_year values must be strictly increasing")
        years = [e.year for e in self.table]
        if years != sorted(years) or len(set(years)) != len(years):
            raise ValueError("table: years must be strictly increasing")
        return self


class StressRequest(ProjectionRequest):
    """Inputs for POST /stress: a projection case plus scenario axes."""

    rates: list[NonNegRate] = Field(min_length=1)
    ratios: list[AchvPercent] = Field(min_length=1)
    stress_year: int = Field(gt=0)


class RowOut(BaseModel):
    """One policy year's projection output (mirrors engine.Row)."""

    model_config = ConfigDict(from_attributes=True)

    year: int
    rate: float
    interest: float
    surrender: float
    gross: float
    net: float
    irr: float | None
    cashflows: tuple[float, ...]


class CellOut(BaseModel):
    """One stress-matrix cell (mirrors engine.Cell)."""

    model_config = ConfigDict(from_attributes=True)

    rate: float
    achievement: float
    irr: float | None


class ProjectionResponse(BaseModel):
    rows: list[RowOut]
    disclaimer: str


class StressResponse(BaseModel):
    rate_columns: list[float]
    achievement_rows: list[float]
    rows: list[list[CellOut]]
    disclaimer: str


class HealthResponse(BaseModel):
    status: str


# --------------------------------------------------------------------- app

from fastapi import FastAPI  # noqa: E402  (kept below schema defs for readability)

from pfpro import engine


def _to_params(req: ProjectionRequest) -> engine.ProjectionParams:
    """Map the API request onto the engine's pure input dataclass."""
    return engine.ProjectionParams(
        total_premium=req.total_premium,
        discount_percent=req.discount_percent,
        surrender0_percent=req.surrender0_percent,
        ltv_percent=req.ltv_percent,
        bank_fx=req.bank_fx,
        fwd_fx=req.fwd_fx,
        rate_brackets=tuple(
            engine.RateBracket(end_year=b.end_year, rate=b.rate)
            for b in req.rate_brackets
        ),
        achievement_percent=req.achievement_percent,
    )


def _to_table(req: ProjectionRequest) -> list[dict[str, float | int]]:
    return [entry.model_dump() for entry in req.table]


def create_app() -> FastAPI:
    """Build the FastAPI application exposing the engine over HTTP."""
    application = FastAPI(
        title="pfpro",
        version="0.1.0",
        description="Premium-financing calculator API (clean-room rebuild). "
                    "Illustrative figures only; see the disclaimer field on "
                    "every response.",
    )

    @application.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.post("/projection", response_model=ProjectionResponse)
    def projection(req: ProjectionRequest) -> ProjectionResponse:
        rows = engine.project(_to_params(req), _to_table(req))
        return ProjectionResponse(rows=rows, disclaimer=DISCLAIMER)

    @application.post("/stress", response_model=StressResponse)
    def stress(req: StressRequest) -> StressResponse:
        matrix = engine.stress_matrix(
            _to_params(req),
            _to_table(req),
            req.rates,
            req.ratios,
            req.stress_year,
        )
        return StressResponse(
            rate_columns=matrix.rate_columns,
            achievement_rows=matrix.achievement_rows,
            rows=matrix.rows,
            disclaimer=DISCLAIMER,
        )

    return application


app = create_app()

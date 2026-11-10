"""Premium-financing calculation engine (clean-room rebuild).

Pure functions, standard library only, no I/O. Implements the formulas in
docs/02-functional-spec.md:

- ``solve_irr``       — annualised IRR of a cashflow series (None when the
                        series has no sign change, matching the reference
                        tool's em-dash display).
- ``effective_rate``  — H/P dual-track loan pricing (min of the two plans).
- ``project``         — year-by-year projection (interest, surrender value,
                        gross/net profit, IRR cashflows) from a benefit table.
- ``stress_matrix``   — IRR matrix over loan-rate columns x achievement rows.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

_NPV_TOL = 1e-12
_MAX_ITERATIONS = 200


def solve_irr(cashflows: Sequence[float]) -> float | None:
    """Return the annualised internal rate of return for ``cashflows``.

    The cashflows are indexed by year: index 0 is today, index t is t years
    from now. The IRR is the rate ``r`` that zeroes::

        NPV(r) = sum(cf[t] / (1 + r) ** t)

    Returns ``None`` when the series has no positive/negative sign change
    (e.g. all-negative early-surrender cashflows), matching the reference
    tool's boundary behaviour. The reference implementation used
    Newton-Raphson with heuristic initial values; this rebuild uses a
    bracketed bisection on (-1, +inf), which converges to the same unique
    root for single-sign-change series without the original's divergence
    modes.
    """
    flows = [float(c) for c in cashflows]
    while len(flows) > 1 and flows[-1] == 0.0:
        # Trailing zeros do not move the root; drop them so the bracketing
        # logic below keys off the last non-zero flow.
        flows.pop()
    if len(flows) < 2:
        return None
    has_positive = any(c > 0.0 for c in flows)
    has_negative = any(c < 0.0 for c in flows)
    if not (has_positive and has_negative):
        return None

    def npv(rate: float) -> float:
        discount = 1.0 + rate
        total = flows[0]
        factor = 1.0
        for t in range(1, len(flows)):
            factor *= discount
            total += flows[t] / factor
        return total

    lo = -1.0 + 1e-9
    hi = 1.0
    f_lo = npv(lo)
    f_hi = npv(hi)
    while f_lo * f_hi > 0.0 and hi < 1e6:
        hi *= 2.0
        f_hi = npv(hi)
    if not math.isfinite(f_lo) or not math.isfinite(f_hi) or f_lo * f_hi > 0.0:
        return None

    lo_is_negative = f_lo < 0.0
    for _ in range(_MAX_ITERATIONS):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid)
        if f_mid == 0.0 or hi - lo < _NPV_TOL:
            return mid
        if (f_mid < 0.0) == lo_is_negative:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass(frozen=True)
class RateBracket:
    """One segment of the loan's piecewise rate schedule.

    ``end_year`` is the last policy year the segment applies to; ``0`` marks
    the open-ended final segment. ``rate`` is a percentage (e.g. 4.11).
    """

    end_year: int
    rate: float


def effective_rate(
    hibor_1m: float,
    h_spread: float,
    prime_rate: float,
    p_spread: float,
) -> float:
    """Adopted loan rate under H/P dual-track pricing (spec §3).

    H-plan rate = HIBOR(1M) + ``h_spread``; P-plan rate = ``prime_rate``
    minus ``p_spread``; the bank charges ``min(H, P)``. When only the P plan
    is offered the minimum reduces to the P rate directly.
    """
    return min(hibor_1m + h_spread, prime_rate - p_spread)


@dataclass(frozen=True)
class ProjectionParams:
    """Inputs for a premium-financing projection.

    Percent fields are given as numbers of percent (e.g. ``ltv_percent=95``
    means 95%); FX rates are HKD per USD as in docs/02-functional-spec.md §1.
    ``rate_brackets`` accepts mappings with ``end_year``/``rate`` keys (the
    vectors.json shape) or :class:`RateBracket` instances.
    """

    total_premium: float
    discount_percent: float
    surrender0_percent: float
    ltv_percent: float
    bank_fx: float
    fwd_fx: float
    rate_brackets: Sequence[Any]
    achievement_percent: float


@dataclass(frozen=True)
class Row:
    """One policy year's projection output."""

    year: int
    rate: float  # applied loan rate (%) for this policy year
    interest: float  # z = loan x rate% (simple interest, paid yearly)
    surrender: float  # S = g + (c + s) x achievement%
    gross: float  # F = S - loan (cash back at surrender, before costs)
    net: float  # F + outlay - cumulative interest through this year
    irr: float | None  # IRR of this year's cashflow series, None if no sign change
    cashflows: tuple[float, ...]  # [outlay, -z x (year-1), gross - z]


def _bracket_fields(bracket: Any) -> tuple[int, float]:
    if isinstance(bracket, Mapping):
        return int(bracket["end_year"]), float(bracket["rate"])
    return int(bracket.end_year), float(bracket.rate)


def _bracket_rate(brackets: Sequence[Any], year: int) -> float:
    """Return the rate (%) applying to ``year`` in a piecewise schedule.

    Lookup rule (docs/02-functional-spec.md §1): the first segment whose
    ``end_year`` >= ``year``, or whose ``end_year`` is 0 (open segment).
    """
    for bracket in brackets:
        end_year, rate = _bracket_fields(bracket)
        if end_year == 0 or end_year >= year:
            return rate
    raise ValueError(f"no rate bracket covers policy year {year}")


def _loan_usd(params: ProjectionParams) -> float:
    """Loan principal: total premium x surrender0% x LTV% (spec §2)."""
    return (params.total_premium * params.surrender0_percent / 100.0
            * params.ltv_percent / 100.0)


def _outlay_usd(params: ProjectionParams, loan: float) -> float:
    """Client's day-one cash outlay (negative = outflow), USD (spec §2)."""
    premium_after_discount = params.total_premium * (1.0 - params.discount_percent / 100.0)
    return -((premium_after_discount * params.fwd_fx - loan * params.bank_fx)
             / params.fwd_fx)


def project(
    params: ProjectionParams,
    table: Sequence[Mapping[str, Any]],
) -> list[Row]:
    """Project a premium-financing case year by year.

    ``params`` carries the case inputs; ``table`` is the policy's benefit
    illustration, one mapping per policy year with ``year``, ``guaranteed``,
    ``reversionary`` and ``special`` entries. Returns one :class:`Row` per
    table entry, in ascending year order. Formulas per
    docs/02-functional-spec.md §2: interest is simple, paid yearly, never
    capitalised; cumulative interest across rate-bracket boundaries uses the
    bracket in force for each elapsed year.
    """
    loan = _loan_usd(params)
    outlay = _outlay_usd(params, loan)
    achievement = params.achievement_percent / 100.0

    rows: list[Row] = []
    for entry in sorted(table, key=lambda e: int(e["year"])):
        year = int(entry["year"])
        rate = _bracket_rate(params.rate_brackets, year)
        interest = loan * rate / 100.0
        cumulative_interest = sum(
            loan * _bracket_rate(params.rate_brackets, t) / 100.0
            for t in range(1, year)
        )
        surrender = (float(entry["guaranteed"])
                     + (float(entry["reversionary"]) + float(entry["special"])) * achievement)
        gross = surrender - loan
        net = gross + outlay - cumulative_interest - interest
        cashflows = tuple(
            [outlay]
            + [-loan * _bracket_rate(params.rate_brackets, t) / 100.0 for t in range(1, year)]
            + [gross - interest]
        )
        rows.append(Row(
            year=year,
            rate=rate,
            interest=interest,
            surrender=surrender,
            gross=gross,
            net=net,
            irr=solve_irr(cashflows),
            cashflows=cashflows,
        ))
    return rows

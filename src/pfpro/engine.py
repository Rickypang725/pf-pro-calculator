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
from typing import Sequence

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

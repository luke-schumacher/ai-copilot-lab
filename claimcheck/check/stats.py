"""
The one statistical decision every stamp is built from.

A claim is directional: this driver's number is bigger (or smaller) than the
comparison's, by an amount worth caring about. Given the difference `d` in the
claimed direction, its interval `[L, U]` and the size that matters `tol`:

    Supported       L > 0 and d >= tol
    Contradicted    U < tol         (confidently smaller than tol, or reversed)
    Can't tell yet  otherwise

The two conditions cannot both hold (U >= d >= tol), so the outcome is unique.
It is an equivalence-plus-superiority test, so "Contradicted" has to be earned
by the data rather than being the absence of "Supported".

No scipy: the t quantiles are tabulated, which is all a t interval needs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from claimcheck.check import thresholds as th

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
CANT_TELL = "cant_tell"

LABEL = {
    SUPPORTED: "Supported",
    CONTRADICTED: "Contradicted",
    CANT_TELL: "Can't tell yet",
}

# One-sided 95 % t quantiles (two-sided 90 %), by degrees of freedom.
_T95 = {
    1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895,
    8: 1.860, 9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782, 13: 1.771,
    14: 1.761, 15: 1.753, 16: 1.746, 17: 1.740, 18: 1.734, 19: 1.729,
    20: 1.725, 25: 1.708, 30: 1.697, 40: 1.684, 60: 1.671, 120: 1.658,
}
_Z95 = 1.645


def t95(df: float) -> float:
    """One-sided 95 % t quantile, interpolated in 1/df between table rows."""
    if not math.isfinite(df) or df > 120:
        return _Z95
    df = max(float(df), 1.0)
    keys = sorted(_T95)
    if df in _T95:
        return _T95[int(df)]
    lo = max(k for k in keys if k <= df)
    hi = min(k for k in keys if k >= df)
    if lo == hi:
        return _T95[lo]
    w = (1.0 / df - 1.0 / hi) / (1.0 / lo - 1.0 / hi)
    return w * _T95[lo] + (1.0 - w) * _T95[hi]


@dataclass(frozen=True)
class Comparison:
    """A difference between two groups of laps, in the claimed direction."""

    diff: float            # mean(driver) - mean(reference), signed so + = as claimed
    low: float
    high: float
    tol: float
    n_driver: int
    n_ref: int
    mean_driver: float
    mean_ref: float
    method: str            # "welch" | "one-sample"
    stamp: str

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


def decide(diff: float, low: float, high: float, tol: float) -> str:
    if low > 0.0 and diff >= tol:
        return SUPPORTED
    if high < tol:
        return CONTRADICTED
    return CANT_TELL


def compare(driver: Sequence[float], reference: Sequence[float], tol: float,
            direction: int = +1) -> Optional[Comparison]:
    """
    Compare a metric between the driver's laps and the reference laps.

    `direction` is +1 when the claim is "driver's value is larger" (later
    brake point, longer corner time) and -1 when "smaller" (earlier brake
    point, lower minimum speed). Returns None when there is nothing to
    compare at all; the caller decides what too-few means.
    """
    d = np.asarray([x for x in driver if x is not None and np.isfinite(x)], float)
    r = np.asarray([x for x in reference if x is not None and np.isfinite(x)], float)
    if d.size == 0 or r.size == 0:
        return None
    md, mr = float(d.mean()), float(r.mean())
    diff = direction * (md - mr)
    vd = float(d.var(ddof=1)) if d.size > 1 else float("nan")

    if r.size >= 2 and d.size >= 2:
        vr = float(r.var(ddof=1))
        se2 = vd / d.size + vr / r.size
        se = math.sqrt(se2)
        num = se2 * se2
        den = ((vd / d.size) ** 2 / (d.size - 1)) + ((vr / r.size) ** 2 / (r.size - 1))
        df = num / den if den > 0 else float("inf")
        method = "welch"
    elif d.size >= 2:
        # A single reference lap: its own noise is unknown, so only the
        # driver's scatter enters. The page says so.
        se = math.sqrt(vd / d.size)
        df = d.size - 1
        method = "one-sample"
    else:
        return Comparison(diff, -math.inf, math.inf, tol, int(d.size), int(r.size),
                          md, mr, "single-lap", CANT_TELL)

    if se == 0.0:
        low = high = diff
    else:
        half = t95(df) * se
        low, high = diff - half, diff + half
    return Comparison(diff, low, high, tol, int(d.size), int(r.size), md, mr,
                      method, decide(diff, low, high, tol))


def robust_keep(values: Sequence[float]) -> np.ndarray:
    """Boolean mask of values that are not robust outliers (see thresholds)."""
    x = np.asarray(values, float)
    keep = np.isfinite(x)
    if keep.sum() < th.OUTLIER_MIN_LAPS:
        return keep
    med = float(np.median(x[keep]))
    mad = float(np.median(np.abs(x[keep] - med)))
    if mad == 0.0:
        return keep
    return keep & (np.abs(x - med) <= th.OUTLIER_K * 1.4826 * mad)

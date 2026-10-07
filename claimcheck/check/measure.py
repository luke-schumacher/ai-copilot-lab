"""
What a driver did in a corner, lap by lap, in numbers a race engineer uses.

Every metric is measured on the reference distance axis inside the corner's
window, so "brake point 312 m" means the same marker board on every lap.
Every pedal threshold is named in `thresholds.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from claimcheck.check import thresholds as th
from claimcheck.check.session import Dataset, LapTrace
from claimcheck.check.track import Corner, Track, first_crossing
from claimcheck.car import GENERIC as CAR        # generic wheelbase and steering ratio

#: Metric name -> (label, unit, decimals). The order is the page's order.
METRICS = {
    "corner_time_s": ("corner time", "s", 3),
    "brake_point_m": ("brake point", "m", 1),
    "peak_brake_bar": ("peak brake pressure", "bar", 1),
    "v_min_kph": ("minimum speed", "km/h", 1),
    "throttle_on_m": ("throttle pick-up", "m", 1),
    "full_throttle_m": ("full throttle", "m", 1),
    "coasting_s": ("coasting", "s", 2),
    "full_throttle_share": ("full-throttle share", "", 2),
    "understeer_deg": ("understeer angle", "°", 2),
}


@dataclass
class CornerLap:
    """One lap through one corner."""

    lap: LapTrace
    corner: Corner
    values: Dict[str, Optional[float]]
    phases: Dict[str, float]          # entry / mid / exit time, s
    brake_censored: bool = False      # already braking when the window opened


def _t_at(lap: LapTrace, s: float) -> float:
    return float(np.interp(s, lap.s, lap.t))


def _mask(lap: LapTrace, lo: float, hi: float) -> np.ndarray:
    return (lap.s >= lo) & (lap.s <= hi)


def corner_lap(lap: LapTrace, c: Corner) -> CornerLap:
    s = lap.s
    win = _mask(lap, c.entry_m, c.exit_m)
    vals: Dict[str, Optional[float]] = {k: None for k in METRICS}
    phases = {name: _t_at(lap, b) - _t_at(lap, a) for name, (a, b) in c.phases().items()}
    vals["corner_time_s"] = _t_at(lap, c.exit_m) - _t_at(lap, c.entry_m)
    if win.sum() < 3:
        return CornerLap(lap, c, vals, phases)

    v = np.nan_to_num(lap.v_kph)
    thr = np.nan_to_num(lap.throttle)
    brk = np.nan_to_num(lap.brake)

    # Minimum speed, and where.
    idx = np.flatnonzero(win)
    k_min = idx[int(np.argmin(v[idx]))]
    vals["v_min_kph"] = float(v[k_min])
    s_vmin = float(s[k_min])

    # Brake point: first crossing of the threshold between the previous apex
    # and this one, independent of the time window.
    censored = False
    bp = first_crossing(s, brk, th.BRAKE_ON_BAR, c.brake_from_m, c.apex_m + 20.0, already=True)
    if bp is not None and bp <= c.brake_from_m + th.GRID_M:
        censored = True
    vals["brake_point_m"] = bp
    brake_zone = _mask(lap, c.brake_from_m, c.apex_m + 20.0)
    vals["peak_brake_bar"] = float(brk[brake_zone].max()) if brake_zone.any() and bp is not None else None

    # Throttle: from its lowest point in the corner, back up through 20 %
    # (pick-up) and 95 % (full). If it never dropped, there is no pick-up.
    lead = _mask(lap, c.entry_m, s_vmin + 30.0)
    if lead.any():
        li = np.flatnonzero(lead)
        s_low = float(s[li[int(np.argmin(thr[li]))]])
        if thr[li].min() < th.THROTTLE_ON_PCT:
            vals["throttle_on_m"] = first_crossing(s, thr, th.THROTTLE_ON_PCT, s_low, c.exit_m)
        if thr[li].min() < th.THROTTLE_FULL_PCT:
            vals["full_throttle_m"] = first_crossing(s, thr, th.THROTTLE_FULL_PCT, s_low, c.exit_m)

    # Coasting time and full-throttle share, over the window.
    dt = np.diff(lap.t, append=lap.t[-1])
    ds = np.diff(s, append=s[-1])
    coast = (thr < th.PEDAL_OFF_PCT) & (brk < th.BRAKE_OFF_BAR) & win
    vals["coasting_s"] = float(dt[coast].sum())
    span = float(ds[win].sum())
    vals["full_throttle_share"] = float(ds[win & (thr >= th.THROTTLE_FULL_PCT)].sum() / span) if span > 0 else None

    # Understeer angle: road-wheel angle minus the Ackermann angle.
    if lap.steer is not None and np.isfinite(lap.steer).any():
        steer = np.nan_to_num(lap.steer)
        ay = np.nan_to_num(lap.ay_g)
        with np.errstate(divide="ignore", invalid="ignore"):
            slip = (ay * 9.81 * CAR.wheelbase_m) / ((v / 3.6) ** 2) * 57.295
            us = np.abs(steer / CAR.steering_ratio) - np.abs(slip)
        gate = win & (np.abs(steer) > th.UNDERSTEER_MIN_STEER_DEG) & (np.abs(ay) > 0.3) & (v > 30.0)
        if gate.sum() >= 3:
            vals["understeer_deg"] = float(np.mean(us[gate]))

    return CornerLap(lap, c, vals, phases, censored)


@dataclass
class TyreFit:
    slope_s_per_lap: float
    residual_std_s: float
    n_laps: int

    @property
    def credible(self) -> bool:
        """Degradation only: a positive slope bigger than its own scatter."""
        return (self.slope_s_per_lap > 0.0 and
                self.slope_s_per_lap > self.residual_std_s / max(self.n_laps ** 0.5, 1.0))


def tyre_fits(data: Dataset, min_laps: int = 4) -> Dict[tuple, TyreFit]:
    """Lap time against tyre age, per driver and stint, valid laps only."""
    groups: Dict[tuple, List[LapTrace]] = {}
    for lp in data.valid():
        groups.setdefault((lp.driver, lp.source, lp.stint), []).append(lp)
    out: Dict[tuple, TyreFit] = {}
    for key, laps in groups.items():
        ages = np.array([lp.age for lp in laps], float)
        times = np.array([lp.time_s for lp in laps], float)
        if len(laps) < min_laps or ages.max() == ages.min():
            continue
        b, a = np.polyfit(ages, times, 1)
        resid = times - (b * ages + a)
        out[key] = TyreFit(float(b), float(resid.std()), len(laps))
    return out


class Measurements:
    """Every valid lap through every corner, computed once."""

    def __init__(self, data: Dataset, track: Track):
        self.data, self.track = data, track
        self.by_corner: Dict[str, List[CornerLap]] = {
            c.name: [corner_lap(lp, c) for lp in data.valid()] for c in track.corners
        }
        self.fits = tyre_fits(data)
        ref_times = {c.name: self._ref_time(c) for c in track.corners}
        total = sum(ref_times.values()) or 1.0
        self.share = {name: t / total for name, t in ref_times.items()}

    def _ref_time(self, c: Corner) -> float:
        return _t_at(self.track.reference, c.exit_m) - _t_at(self.track.reference, c.entry_m)

    def tyre_correction(self, cl: CornerLap) -> float:
        """Seconds this lap lost in this corner to tyre age alone (0 if not credible)."""
        fit = self.fits.get((cl.lap.driver, cl.lap.source, cl.lap.stint))
        if fit is None or not fit.credible:
            return 0.0
        return fit.slope_s_per_lap * cl.lap.age * self.share[cl.corner.name]

    def laps(self, corner: str, driver: str) -> List[CornerLap]:
        return [cl for cl in self.by_corner.get(corner, []) if cl.lap.driver == driver]

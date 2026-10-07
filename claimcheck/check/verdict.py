"""
The judge: a claim, the laps, and one of three stamps.

The rules are in `docs/implementation-plan.md` §5 and the numbers in
`thresholds.py`. Nothing here reads the sentence and nothing here calls a
model: given the same `ClaimSpec` and the same files, the stamp is the same
every time.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from claimcheck.check import thresholds as th
from claimcheck.check.claim import CAUSES, EFFECTS, OWN_BEST, UNSUPPORTED, ClaimSpec, describe
from claimcheck.check.measure import METRICS, CornerLap, Measurements
from claimcheck.check.stats import (CANT_TELL, CONTRADICTED, LABEL, SUPPORTED, Comparison,
                                compare, robust_keep)
from claimcheck.check.track import Corner


@dataclass
class Test:
    name: str                 # "effect" or a cause key
    label: str
    metric: str
    comparison: Optional[Comparison]
    stamp: str
    note: str = ""
    share: Optional[float] = None     # of the loss, in this cause's phases
    direction: int = 1                # the sign of (driver - reference) the claim asserts

    def to_dict(self) -> dict:
        label, unit, dec = METRICS[self.metric]
        c = self.comparison
        out = {"name": self.name, "label": self.label, "metric": self.metric,
               "metric_label": label, "unit": unit, "stamp": self.stamp,
               "note": self.note, "share": None if self.share is None else round(self.share, 3)}
        if c is not None:
            out.update(c.to_dict())
        return out


@dataclass
class Verdict:
    stamp: str
    headline: str
    spec: ClaimSpec
    understood: str
    driver: Optional[str] = None
    reference: str = ""
    corner: Optional[Corner] = None
    tests: List[Test] = field(default_factory=list)
    where: Dict[str, float] = field(default_factory=dict)
    pointers: List[Test] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    rows: List[dict] = field(default_factory=list)
    plot_laps: Tuple[Optional[str], Optional[str]] = (None, None)  # driver lap key, reference lap key
    checked_at: str = field(default_factory=lambda: _dt.datetime.now().isoformat(timespec="seconds"))

    @property
    def label(self) -> str:
        return LABEL[self.stamp]

    def to_dict(self) -> dict:
        return {
            "stamp": self.stamp, "label": self.label, "headline": self.headline,
            "understood": self.understood, "spec": self.spec.to_dict(),
            "driver": self.driver, "reference": self.reference,
            "corner": self.corner.to_dict() if self.corner else None,
            "tests": [t.to_dict() for t in self.tests],
            "where": {k: round(v, 3) for k, v in self.where.items()},
            "pointers": [t.to_dict() for t in self.pointers],
            "caveats": list(self.caveats), "rows": self.rows,
            "plot_laps": list(self.plot_laps), "thresholds": th.VERSION,
            "checked_at": self.checked_at,
        }


# ---- wording ---------------------------------------------------------------

def _fmt(metric: str, x: float, signed: bool = False) -> str:
    _, unit, dec = METRICS[metric]
    if metric == "full_throttle_share":
        s = f"{x * 100:+.0f} pp" if signed else f"{x * 100:.0f} %"
        return s
    s = f"{x:+.{dec}f}" if signed else f"{x:.{dec}f}"
    return f"{s} {unit}".strip()


def _diff_words(metric: str, d: float) -> str:
    """mean(driver) - mean(reference), said the way an engineer says it."""
    a = abs(d)
    if metric == "corner_time_s":
        return f"{'loses' if d > 0 else 'gains'} {a:.2f} s"
    if metric == "brake_point_m":
        return f"brakes {a:.0f} m {'later' if d > 0 else 'earlier'}"
    if metric == "throttle_on_m":
        return f"picks up the throttle {a:.0f} m {'later' if d > 0 else 'earlier'}"
    if metric == "full_throttle_m":
        return f"reaches full throttle {a:.0f} m {'later' if d > 0 else 'earlier'}"
    if metric == "v_min_kph":
        return f"carries {a:.1f} km/h {'more' if d > 0 else 'less'} minimum speed"
    if metric == "peak_brake_bar":
        return f"brakes {a:.0f} bar {'harder' if d > 0 else 'softer'} at peak"
    if metric == "coasting_s":
        return f"coasts {a:.2f} s {'longer' if d > 0 else 'less'}"
    if metric == "full_throttle_share":
        return f"is flat {a * 100:.0f} pp {'more' if d > 0 else 'less'} of the corner"
    if metric == "understeer_deg":
        return f"shows {a:.2f}° {'more' if d > 0 else 'less'} understeer"
    return _fmt(metric, d, signed=True)


def _interval_words(metric: str, c: Comparison, direction: int) -> str:
    lo, hi = sorted((direction * c.low, direction * c.high))
    return f"{_fmt(metric, lo, True)} to {_fmt(metric, hi, True)}"


# ---- the judge ---------------------------------------------------------------

def _cant(spec: ClaimSpec, why: str, **kw) -> Verdict:
    return Verdict(stamp=CANT_TELL, headline=why, spec=spec, understood=describe(spec), **kw)


def judge(spec: ClaimSpec, m: Measurements) -> Verdict:
    data, track = m.data, m.track
    drivers = data.drivers
    understood = describe(spec)

    # ---- can the claim be pinned to a driver and a corner at all? ----
    driver = spec.driver
    if driver is None and len(drivers) == 1:
        driver = drivers[0]
    if driver is None:
        return _cant(spec, "Which driver? Loaded: " + ", ".join(drivers) + ".",
                     caveats=list(spec.unread))
    if driver not in drivers:
        return _cant(spec, f"{driver} is not in the loaded session ({', '.join(drivers)}).")
    spec.driver = driver
    understood = describe(spec)

    if spec.corner is None:
        names = ", ".join(c.name for c in track.corners)
        return _cant(spec, f"Which corner? This lap has {names}.", driver=driver,
                     caveats=list(spec.unread))
    corner = track.corner(spec.corner)
    if corner is None:
        return _cant(spec, f"There is no {spec.corner} on this lap: the tool found "
                     f"{len(track.corners)} corners (T1–T{len(track.corners)}). See the map.",
                     driver=driver)

    caveats = list(spec.unread)
    for key in spec.unsupported:
        caveats.append(UNSUPPORTED[key])
    if not spec.effect and not spec.causes:
        why = (UNSUPPORTED[spec.unsupported[0]] if spec.unsupported
               else "There is no claim here I can test.")
        return _cant(spec, why, driver=driver, corner=corner, caveats=caveats)

    # ---- who is it compared with? ----
    own = data.valid(driver)
    others = [d for d in drivers if d != driver and data.valid(d)]
    if spec.versus and spec.versus not in (OWN_BEST,) and spec.versus not in drivers:
        return _cant(spec, f"{spec.versus} is not in the loaded session.", driver=driver,
                     corner=corner)
    d_laps = m.laps(corner.name, driver)
    if spec.versus not in (None, OWN_BEST):
        ref_driver = spec.versus
        r_laps = m.laps(corner.name, ref_driver)
        reference = f"{ref_driver}'s valid laps"
    elif spec.versus is None and others:
        ref_driver = min(others, key=lambda d: data.best(d).time_s)
        r_laps = m.laps(corner.name, ref_driver)
        reference = f"{ref_driver}'s valid laps (the fastest other driver)"
    else:
        best = data.best(driver)
        r_laps = [cl for cl in d_laps if cl.lap is best]
        d_laps = [cl for cl in d_laps if cl.lap is not best]
        reference = f"{driver}'s own fastest lap ({best.number}, {best.time_s:.3f} s)"
        caveats.append("The comparison is a single lap, so its own noise is unknown "
                       "and only the other laps' scatter counts.")

    # ---- set aside the corner-time outliers ----
    def corrected(cls: List[CornerLap]) -> List[float]:
        return [cl.values["corner_time_s"] - m.tyre_correction(cl) for cl in cls]

    excluded = []
    for group in ("d", "r"):
        cls = d_laps if group == "d" else r_laps
        keep = robust_keep(corrected(cls))
        excluded += [cl for cl, k in zip(cls, keep) if not k]
        if group == "d":
            d_laps = [cl for cl, k in zip(cls, keep) if k]
        else:
            r_laps = [cl for cl, k in zip(cls, keep) if k]
    for cl in excluded:
        caveats.append(f"{cl.lap.label} set aside in {corner.name}: its corner time is far "
                       "outside the others (traffic or a moment?).")
    if any(m.tyre_correction(cl) for cl in d_laps + r_laps):
        caveats.append("Tyre wear corrected: a credible lap-time trend was found and its "
                       "share removed from each corner time.")

    rows = _rows(d_laps, r_laps, excluded, driver)
    plot = (_median_lap(d_laps), _fastest(r_laps))
    base = dict(spec=spec, understood=understood, driver=driver, reference=reference,
                corner=corner, rows=rows, plot_laps=plot)

    if len(d_laps) < th.MIN_LAPS:
        return Verdict(stamp=CANT_TELL, caveats=caveats, headline=(
            f"Only {len(d_laps)} clean lap{'s' if len(d_laps) != 1 else ''} for {driver} "
            f"through {corner.name}; {th.MIN_LAPS} are needed. The next session will settle it."),
            **base)
    if not r_laps:
        return Verdict(stamp=CANT_TELL, caveats=caveats,
                       headline=f"Nothing to compare {driver} with in {corner.name}.", **base)

    # ---- the effect: corner time ----
    direction = +1 if spec.effect != "gains" else -1
    eff_cmp = compare(corrected(d_laps), corrected(r_laps), th.TOL["corner_time_s"], direction)
    effect = Test("effect", EFFECTS.get(spec.effect or "loses"), "corner_time_s",
                  eff_cmp, eff_cmp.stamp if eff_cmp else CANT_TELL, direction=direction)
    where = _where(d_laps, r_laps)
    loss = sum(where.values())

    # ---- the causes ----
    tests: List[Test] = [effect] if spec.effect else []
    cause_tests = [_cause_test(key, d_laps, r_laps, where, loss) for key in spec.causes]
    tests += cause_tests

    # ---- combine ----
    stamp, headline = _combine(spec, driver, corner, effect, cause_tests, reference)
    if spec.unsupported and stamp == SUPPORTED:
        # The part we can check holds; the "because" we cannot check decides.
        what = {"oversteer": "oversteer", "line": "the line", "car": "the setup"}
        named = " or ".join(what[k] for k in spec.unsupported)
        stamp = CANT_TELL
        headline = (f"{headline.rstrip('.')}. Whether that is down to {named} can't be "
                    f"checked: {UNSUPPORTED[spec.unsupported[0]]}")
    if not spec.effect and cause_tests:
        tests.insert(0, effect)  # context, not part of the stamp
        effect.note = "context only: the claim says nothing about time"

    # ---- what the data points to, when the claim did not explain it ----
    pointers: List[Test] = []
    claimed_ok = any(t.stamp == SUPPORTED for t in cause_tests) and stamp == SUPPORTED
    if spec.effect == "loses" and effect.stamp == SUPPORTED and not claimed_ok:
        for key in CAUSES:
            if key in spec.causes and any(t.name == key and t.stamp == SUPPORTED and
                                          (t.share or 0) >= th.SHARE_SUPPORTS for t in cause_tests):
                continue
            t = _cause_test(key, d_laps, r_laps, where, loss)
            phases = th.CAUSE_PHASES[key]
            if t.stamp == SUPPORTED and (not phases or (t.share or 0) >= th.SHARE_SUPPORTS):
                pointers.append(t)
        pointers.sort(key=lambda t: -(t.share or 0))

    return Verdict(stamp=stamp, headline=headline, tests=tests, where=where,
                   pointers=pointers[:3], caveats=caveats, **base)


def _values(cls: List[CornerLap], metric: str) -> List[float]:
    return [cl.values[metric] for cl in cls if cl.values.get(metric) is not None]


def _where(d: List[CornerLap], r: List[CornerLap]) -> Dict[str, float]:
    out = {}
    for p in ("entry", "mid", "exit"):
        out[p] = float(np.mean([cl.phases[p] for cl in d]) - np.mean([cl.phases[p] for cl in r]))
    return out


def _cause_test(key: str, d: List[CornerLap], r: List[CornerLap],
                where: Dict[str, float], loss: float) -> Test:
    label, metric, direction = CAUSES[key]
    dv, rv = _values(d, metric), _values(r, metric)
    phases = th.CAUSE_PHASES[key]
    share = (sum(where[p] for p in phases) / loss) if (phases and loss > 0) else None
    if not rv:
        what = METRICS[metric][0]
        return Test(key, label, metric, None, CANT_TELL, share=share, direction=direction,
                    note=f"no {what} on the comparison laps in this corner")
    if len(dv) < th.MIN_LAPS:
        return Test(key, label, metric, None, CANT_TELL, share=share, direction=direction,
                    note=f"{METRICS[metric][0]} found on only {len(dv)} of the driver's laps")
    c = compare(dv, rv, th.TOL[metric], direction)
    note = ""
    if metric == "brake_point_m" and any(cl.brake_censored for cl in d + r):
        note = "some laps were already braking when the corner window opened"
    return Test(key, label, metric, c, c.stamp, note=note, share=share, direction=direction)


def _combine(spec: ClaimSpec, driver: str, corner: Corner, effect: Test,
             causes: List[Test], reference: str) -> Tuple[str, str]:
    cn = corner.name
    vs = reference.split("'s")[0] if "'s" in reference else reference
    vs_short = "their own best lap" if "own fastest" in reference else vs
    ec = effect.comparison

    def eff_words() -> str:
        return (f"{driver} {_diff_words('corner_time_s', ec.mean_driver - ec.mean_ref)} in {cn} "
                f"against {vs_short} (90 % range {_interval_words('corner_time_s', ec, effect.direction)}, "
                f"{ec.n_driver} vs {ec.n_ref} laps)")

    def cause_words(t: Test) -> str:
        c = t.comparison
        return (f"{_diff_words(t.metric, c.mean_driver - c.mean_ref)} "
                f"(range {_interval_words(t.metric, c, t.direction)})")

    # Effect first, when the claim makes one.
    if spec.effect:
        if ec is None or effect.stamp == CANT_TELL:
            if ec is None:
                return CANT_TELL, f"Not enough laps to compare {driver} in {cn}."
            return CANT_TELL, (f"Too close to call: {eff_words()}. The laps scatter more "
                               f"than the difference.")
        if effect.stamp == CONTRADICTED:
            return CONTRADICTED, (f"{driver} does not {'lose' if spec.effect == 'loses' else 'gain'} "
                                  f"meaningful time in {cn}: {eff_words()}.")
        if not causes:
            return SUPPORTED, f"{eff_words()[0].upper()}{eff_words()[1:]}."

    # Then the causes.
    if any(t.stamp == CONTRADICTED for t in causes):
        bad = next(t for t in causes if t.stamp == CONTRADICTED)
        lead = (f"{driver} {('loses' if spec.effect == 'loses' else 'gains')} time in {cn}, but "
                if spec.effect else f"In {cn}, {driver} ")
        if bad.comparison is not None:
            return CONTRADICTED, f"{lead}{cause_words(bad)} — not {bad.label}."
        return CONTRADICTED, f"{lead}not {bad.label}."
    if any(t.stamp == CANT_TELL for t in causes):
        t = next(t for t in causes if t.stamp == CANT_TELL)
        lead = ""
        if spec.effect and effect.stamp == SUPPORTED:
            lead = (f"{driver} {_diff_words('corner_time_s', ec.mean_driver - ec.mean_ref)} "
                    f"in {cn}, but ")
        if t.comparison is None:
            return CANT_TELL, f"{lead}'{t.label}' can't be checked in {cn}: {t.note}."
        what = f"whether '{t.label}' explains it" if lead else f"whether {driver} {t.label} in {cn}"
        return CANT_TELL, (f"{lead}{what} is too close to call: {cause_words(t)}.")

    # Every cause holds. With an effect, is the time lost where they would lose it?
    words = "; ".join(cause_words(t) for t in causes)
    if not spec.effect:
        return SUPPORTED, f"In {cn}, {driver} {words}, against {vs_short}."
    shares = [t.share for t in causes if t.share is not None]
    if shares:
        share = min(shares)
        phases = sorted({p for t in causes for p in th.CAUSE_PHASES[t.name]})
        where = " and ".join(phases)
        if share >= th.SHARE_SUPPORTS:
            return SUPPORTED, (f"{eff_words()}. And {driver} {words}: "
                               f"{share:.0%} of the loss is in the {where}.")
        if share < th.SHARE_CONTRADICTS:
            return CONTRADICTED, (f"{driver} does {', '.join(t.label for t in causes)} "
                                  f"({words}), but only {max(share, 0):.0%} of the time "
                                  f"is lost in the {where}. The loss is elsewhere in the corner.")
        return CANT_TELL, (f"Partly: {driver} {words}, but only {share:.0%} of the loss is "
                           f"in the {where}.")
    return SUPPORTED, f"{eff_words()}. And {driver} {words}."


# ---- the lap table and plot choice -------------------------------------------

def _rows(d: List[CornerLap], r: List[CornerLap], excluded: List[CornerLap], driver: str) -> List[dict]:
    out = []
    for role, cls in (("driver", d), ("reference", r), ("set aside", excluded)):
        for cl in cls:
            row = {"role": role, "driver": cl.lap.driver, "lap": cl.lap.number,
                   "lap_time_s": round(cl.lap.time_s, 3), "key": cl.lap.key}
            for k, v in cl.values.items():
                row[k] = None if v is None else round(v, 3)
            row.update({f"phase_{p}": round(t, 3) for p, t in cl.phases.items()})
            out.append(row)
    return out


def _median_lap(cls: List[CornerLap]) -> Optional[str]:
    if not cls:
        return None
    ordered = sorted(cls, key=lambda cl: cl.values["corner_time_s"])
    return ordered[len(ordered) // 2].lap.key


def _fastest(cls: List[CornerLap]) -> Optional[str]:
    if not cls:
        return None
    return min(cls, key=lambda cl: cl.values["corner_time_s"]).lap.key

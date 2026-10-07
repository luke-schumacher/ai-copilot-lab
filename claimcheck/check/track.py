"""
One distance axis for every lap, and the corners along it.

Comparing laps by *time* puts the same corner at a different second on every
lap. Comparing them by their own integrated distance drifts by tens of metres
over a lap, because every driver takes a slightly different line. So the
fastest valid lap becomes the reference path, and every sample of every other
lap is *projected* onto it: its position becomes "how far along the reference
lap is the nearest point". Two laps braking at the same marker board then
brake at the same distance, whatever line they took to get there.

Corners are found once, on the reference lap, from lateral acceleration, and
numbered T1..Tn from the line. That numbering is the tool's, not the
circuit's: the map on the page shows it, and aliases cover the difference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from claimcheck.check import thresholds as th
from claimcheck.check.session import Dataset, LapTrace, from_local, to_local


@dataclass
class Corner:
    number: int
    apex_m: float
    v_min_kph: float
    direction: str           # "left" | "right"
    peak_g: float
    start_m: float           # where lateral g first passes the threshold
    end_m: float
    entry_m: float = 0.0     # the measurement window
    exit_m: float = 0.0
    mid_from_m: float = 0.0  # the slow zone around the apex
    mid_to_m: float = 0.0
    ref_brake_m: Optional[float] = None
    ref_full_throttle_m: Optional[float] = None
    brake_from_m: float = 0.0  # braking for this corner is searched from here
    names: List[str] = field(default_factory=list)
    label: Optional[str] = None   # from a track profile; otherwise T<number>

    @property
    def name(self) -> str:
        return self.label or f"T{self.number}"

    def phases(self) -> Dict[str, Tuple[float, float]]:
        return {
            "entry": (self.entry_m, self.mid_from_m),
            "mid": (self.mid_from_m, self.mid_to_m),
            "exit": (self.mid_to_m, self.exit_m),
        }

    def to_dict(self) -> dict:
        return {
            "name": self.name, "names": list(self.names),
            "apex_m": round(self.apex_m, 1), "v_min_kph": round(self.v_min_kph, 1),
            "direction": self.direction, "peak_g": round(self.peak_g, 2),
            "entry_m": round(self.entry_m, 1), "exit_m": round(self.exit_m, 1),
            "mid_from_m": round(self.mid_from_m, 1), "mid_to_m": round(self.mid_to_m, 1),
            "ref_brake_m": None if self.ref_brake_m is None else round(self.ref_brake_m, 1),
        }


@dataclass
class Track:
    reference: LapTrace
    length_m: float
    corners: List[Corner]
    path_x: np.ndarray = field(repr=False)
    path_y: np.ndarray = field(repr=False)
    path_s: np.ndarray = field(repr=False)

    def corner(self, name: str) -> Optional[Corner]:
        key = name.strip().lower()
        for c in self.corners:
            if c.name.lower() == key or key in (n.lower() for n in c.names):
                return c
        return None

    def xy_at(self, s: float) -> Tuple[float, float]:
        return (float(np.interp(s, self.path_s, self.path_x)),
                float(np.interp(s, self.path_s, self.path_y)))


# ---- projection --------------------------------------------------------

def _nearest_on(ax, ay, bx, by, px, py):
    """Per-segment closest point to (px, py): (fraction along, squared distance)."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    with np.errstate(divide="ignore", invalid="ignore"):
        u = np.where(L2 > 0, ((px - ax) * dx + (py - ay) * dy) / L2, 0.0)
    u = np.clip(u, 0.0, 1.0)
    qx, qy = ax + u * dx, ay + u * dy
    return u, (qx - px) ** 2 + (qy - py) ** 2


def _closed(path_x: np.ndarray, path_y: np.ndarray):
    """Segments of the closed loop: point i to point i+1, the last back to 0."""
    bx, by = np.roll(path_x, -1), np.roll(path_y, -1)
    seg_len = np.hypot(bx - path_x, by - path_y)
    s_start = np.concatenate(([0.0], np.cumsum(seg_len)[:-1]))
    return bx, by, seg_len, s_start, float(seg_len.sum())


def project(lap: LapTrace, path_x: np.ndarray, path_y: np.ndarray) -> np.ndarray:
    """
    Distance along the reference loop for every sample of `lap`.

    The search moves forward with the car, through a window of segments
    ahead of the last match, so it cannot jump across the circuit where two
    parts of the track run close together. If the window loses the car (more
    than 25 m away), it searches the whole loop once and carries on from
    there. The loop is closed, so the line is just another point on it. Each
    result is unwrapped to the representative nearest the previous sample's,
    which keeps a lap counting through the line instead of jumping back to
    zero.
    """
    bx, by, seg_len, s_start, L = _closed(path_x, path_y)
    n = len(path_x)
    everywhere = np.arange(n)
    s_out = np.empty(len(lap.x))

    def nearest(k: int, idx: np.ndarray):
        u, d2 = _nearest_on(path_x[idx], path_y[idx], bx[idx], by[idx], lap.x[k], lap.y[k])
        j = int(np.argmin(d2))
        seg = int(idx[j])
        return seg, s_start[seg] + u[j] * seg_len[seg], float(d2[j])

    i, s_raw, _ = nearest(0, everywhere)
    prev = s_raw - L if s_raw > 0.5 * L else s_raw
    s_out[0] = prev
    for k in range(1, len(lap.x)):
        i, s_raw, d2 = nearest(k, np.arange(i - 3, i + 40) % n)
        if d2 > 25.0 ** 2:
            i, s_raw, _ = nearest(k, everywhere)
        s = s_raw + L * round((prev - s_raw) / L)
        s_out[k] = prev = s
    return np.maximum.accumulate(s_out)


# ---- corner detection ----------------------------------------------------

def _smooth(v: np.ndarray, n: int, loop: bool = True) -> np.ndarray:
    """Moving average over `n` points. A lap is a loop; a stretch of one is not."""
    if n <= 1 or len(v) < n:
        return v
    k = np.ones(n) / n
    pad = n // 2
    if loop:
        vp = np.concatenate((v[-pad:], v, v[:pad]))
    else:
        vp = np.concatenate((np.full(pad, v[0]), v, np.full(pad, v[-1])))
    return np.convolve(vp, k, mode="same")[pad:pad + len(v)]


def first_crossing(s: np.ndarray, v: np.ndarray, level: float,
                   lo: float, hi: float, already: bool = False) -> Optional[float]:
    """
    First s in [lo, hi] where v rises through `level`, interpolated between
    samples. If v is already above `level` at `lo`, returns `lo` when
    `already` is set and None otherwise.
    """
    idx = np.flatnonzero((s >= lo) & (s <= hi))
    if idx.size == 0:
        return None
    if v[idx[0]] >= level:
        return float(s[idx[0]]) if already else None
    for a, b in zip(idx[:-1], idx[1:]):
        if v[a] < level <= v[b]:
            f = (level - v[a]) / (v[b] - v[a]) if v[b] != v[a] else 0.0
            return float(s[a] + f * (s[b] - s[a]))
    return None


def build(data: Dataset, reference: Optional[LapTrace] = None,
          profile: Optional[dict] = None) -> Track:
    """
    Reference path, projections for every lap, corners and their windows.

    With a `profile` (see `save_profile`), the corners are the profile's,
    pinned by GPS apex, so their names stay put whichever lap is fastest.
    """
    ref = reference or data.best()
    if ref is None:
        raise ValueError("no valid lap to use as the reference")

    # The path: one lap of the reference's own samples, line to line,
    # de-duplicated, closed back on itself.
    one = (ref.t >= 0.0) & (ref.t < ref.time_s)
    px, py = ref.x[one], ref.y[one]
    keep = np.concatenate(([True], np.hypot(np.diff(px), np.diff(py)) > 0.05))
    px, py = px[keep], py[keep]
    _, _, _, ps, length = _closed(px, py)

    for lap in data.laps:
        lap.s = project(lap, px, py)
    # The lap starts at the line: re-zero the axis there.
    s_line = float(np.interp(0.0, ref.t, ref.s))
    for lap in data.laps:
        # Strictly increasing, so time-at-distance is a function.
        lap.s = lap.s - s_line + np.arange(len(lap.s)) * 1e-6
    ps = ps - s_line

    corners = _detect(ref, length)
    if profile:
        corners = _from_profile(profile, corners, ref, px, py, ps, data.origin, length)
    _windows(corners, ref, length)
    return Track(reference=ref, length_m=length, corners=corners,
                 path_x=px, path_y=py, path_s=ps)


def _locate(px: np.ndarray, py: np.ndarray, ps: np.ndarray, length: float,
            x: float, y: float) -> Tuple[float, float]:
    """Nearest point on the closed path: (distance along it, metres away)."""
    bx, by, seg_len, _, _ = _closed(px, py)
    u, d2 = _nearest_on(px, py, bx, by, x, y)
    i = int(np.argmin(d2))
    return float(np.mod(ps[i] + u[i] * seg_len[i], length)), float(np.sqrt(d2[i]))


def _from_profile(profile: dict, detected: List[Corner], ref: LapTrace, px, py, ps,
                  origin, length: float) -> List[Corner]:
    s_grid, v, ay, _, _ = _grid(ref, length)
    out: List[Corner] = []
    for item in profile.get("corners", []):
        lat, lon = item["apex"]
        x, y = to_local(np.array([lat]), np.array([lon]), origin)
        s_apex, off = _locate(px, py, ps, length, float(x[0]), float(y[0]))
        if off > 60.0:
            continue  # not on this lap: a different layout, or the wrong file
        near = min(detected, key=lambda c: abs(c.apex_m - s_apex)) if detected else None
        if near is not None and abs(near.apex_m - s_apex) <= 60.0:
            start, end, peak = near.start_m, near.end_m, near.peak_g
        else:
            start, end = s_apex - 40.0, s_apex + 40.0
            m = (s_grid >= start) & (s_grid <= end)
            peak = float(np.max(np.abs(ay[m]))) if m.any() else 0.0
        m = (s_grid >= s_apex - 25.0) & (s_grid <= s_apex + 25.0)
        k = int(np.flatnonzero(m)[np.argmin(v[m])]) if m.any() else int(np.searchsorted(s_grid, s_apex))
        out.append(Corner(number=0, apex_m=float(s_grid[k]), v_min_kph=float(v[k]),
                          direction=item.get("direction", near.direction if near else "?"),
                          peak_g=peak, start_m=start, end_m=end,
                          names=list(item.get("aka", [])), label=item.get("name")))
    out.sort(key=lambda c: c.apex_m)
    for n, c in enumerate(out, start=1):
        c.number = n
    return out


def save_profile(track: "Track", origin, path, name: str = "", made_from=()) -> dict:
    """Pin the current corners by GPS apex, so the next session finds the same ones."""
    import json
    corners = []
    for c in track.corners:
        x, y = track.xy_at(c.apex_m)
        lat, lon = from_local(x, y, origin)
        corners.append({"name": c.name, "aka": list(c.names), "direction": c.direction,
                        "apex": [round(lat, 7), round(lon, 7)],
                        "note": f"apex {c.apex_m:.0f} m after the line, {c.v_min_kph:.0f} km/h"})
    profile = {"track": name, "made_from": list(made_from),
               "reference": track.reference.label, "corners": corners,
               "how_to_edit": "Rename 'name' to the official turn number, add nicknames to 'aka', "
                              "delete a corner to ignore it. Apexes are latitude/longitude."}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=1, ensure_ascii=False)
    return profile


def _grid(lap: LapTrace, length: float):
    s = np.arange(0.0, length, th.GRID_M)
    def at(v):
        return np.interp(s, lap.s, np.nan_to_num(v))
    return s, at(lap.v_kph), at(lap.ay_g), at(lap.brake), at(lap.throttle)


def _minima(v: np.ndarray, min_rise: float) -> List[int]:
    """
    Indices of the speed valleys in `v`, with hysteresis: a valley only ends
    when the speed climbs `min_rise` above its bottom, and a new one only
    starts when it falls `min_rise` below the crest in between. A flat bottom,
    or a wobble smaller than `min_rise`, is one valley.
    """
    if len(v) == 0:
        return []
    mins: List[int] = []
    lo_v, lo_i = float(v[0]), 0
    hi_v = float(v[0])
    falling = True
    for i in range(1, len(v)):
        x = float(v[i])
        if falling:
            if x < lo_v:
                lo_v, lo_i = x, i
            elif x > lo_v + min_rise:
                mins.append(lo_i)
                falling, hi_v = False, x
        else:
            if x > hi_v:
                hi_v = x
            elif x < hi_v - min_rise:
                falling, lo_v, lo_i = True, x, i
    if falling:
        mins.append(lo_i)
    return mins


#: Two speed minima inside one stretch of lateral g are two corners when the
#: car gains at least this much speed between them.
SPLIT_RISE_KPH = 10.0


def _detect(ref: LapTrace, length: float) -> List[Corner]:
    s, v, ay, _, _ = _grid(ref, length)
    ay_f = _smooth(ay, max(int(round(th.AY_SMOOTH_M / th.GRID_M)), 1))
    on = np.abs(ay_f) >= th.AY_CORNER_G
    sign = np.sign(ay_f)

    # Heading along the reference path, for left/right from geometry rather
    # than from a sensor's sign convention.
    k_xy = max(int(round(10.0 / th.GRID_M)), 1)
    gx = _smooth(np.interp(s, ref.s, ref.x), k_xy)
    gy = _smooth(np.interp(s, ref.s, ref.y), k_xy)
    psi = np.unwrap(np.arctan2(np.gradient(gy), np.gradient(gx)))

    # Runs of the same direction above the threshold.
    runs: List[List[int]] = []
    start = None
    for i in range(len(s)):
        if on[i] and (start is None or sign[i] == sign[start]):
            if start is None:
                start = i
            continue
        if start is not None:
            runs.append([start, i - 1])
            start = i if on[i] else None
    if start is not None:
        runs.append([start, len(s) - 1])

    # Merge same-direction runs separated by a short gap.
    merged: List[List[int]] = []
    for r in runs:
        if merged:
            p = merged[-1]
            gap = (r[0] - p[1]) * th.GRID_M
            if sign[r[0]] == sign[p[0]] and gap < th.CORNER_MERGE_GAP_M:
                p[1] = r[1]
                continue
        merged.append(r)

    # Split a run where the car speeds up between two minima.
    pieces: List[Tuple[int, int, int]] = []    # (a, b, apex)
    for a, b in merged:
        if (b - a) * th.GRID_M < th.CORNER_MIN_LEN_M:
            continue
        if float(np.max(np.abs(ay_f[a:b + 1]))) < th.AY_PEAK_G:
            continue
        v_run = _smooth(v[a:b + 1], 3, loop=False)
        mins = [a + m for m in _minima(v_run, SPLIT_RISE_KPH)]
        if not mins:
            mins = [a + int(np.argmin(v[a:b + 1]))]
        bounds = [a]
        for m1, m2 in zip(mins[:-1], mins[1:]):
            bounds.append(m1 + int(np.argmax(v[m1:m2 + 1])))
        bounds.append(b)
        for k, apex in enumerate(mins):
            pieces.append((bounds[k], bounds[k + 1], apex))

    corners: List[Corner] = []
    for a, b, k in pieces:
        turn = float(psi[b] - psi[a])
        corners.append(Corner(
            number=0, apex_m=float(s[k]), v_min_kph=float(v[k]),
            direction="left" if turn > 0 else "right",
            peak_g=float(np.max(np.abs(ay_f[a:b + 1]))),
            start_m=float(s[a]), end_m=float(s[b]),
        ))
    for n, c in enumerate(corners, start=1):
        c.number = n
    return corners


def _windows(corners: List[Corner], ref: LapTrace, length: float) -> None:
    s, v, _, brk, thr = _grid(ref, length)
    for i, c in enumerate(corners):
        # Braking for this corner starts after the previous corner's apex.
        lo = c.apex_m - th.BRAKE_SEARCH_M
        if i > 0:
            lo = max(lo, corners[i - 1].apex_m)
        c.brake_from_m = max(lo, 0.0)
        c.ref_brake_m = first_crossing(s, brk, th.BRAKE_ON_BAR, lo, c.apex_m)
        opens = c.ref_brake_m if c.ref_brake_m is not None else c.start_m
        c.entry_m = max(opens - th.ENTRY_MARGIN_M, 0.0)
        c.ref_full_throttle_m = first_crossing(s, thr, th.THROTTLE_FULL_PCT,
                                               c.apex_m, length, already=True)
        closes = c.ref_full_throttle_m if c.ref_full_throttle_m is not None else c.end_m
        c.exit_m = min(max(closes, c.end_m) + th.EXIT_MARGIN_M, length)

    # Neighbours may not overlap: split at the fastest point between apexes,
    # but never after the second corner's braking has begun.
    for a, b in zip(corners[:-1], corners[1:]):
        if a.exit_m > b.entry_m:
            m = (s > a.apex_m) & (s < b.apex_m)
            split = float(s[m][np.argmax(v[m])]) if m.any() else 0.5 * (a.apex_m + b.apex_m)
            if b.ref_brake_m is not None:
                split = min(split, b.ref_brake_m - 20.0)
            split = max(split, a.apex_m + 10.0)
            a.exit_m = b.entry_m = split

    for c in corners:
        m = (s >= c.entry_m) & (s <= c.exit_m)
        slow = v <= c.v_min_kph * th.MID_SPEED_FACTOR
        k = int(np.searchsorted(s, c.apex_m))
        lo = hi = min(k, len(s) - 1)
        while lo > 0 and slow[lo - 1] and m[lo - 1]:
            lo -= 1
        while hi < len(s) - 1 and slow[hi + 1] and m[hi + 1]:
            hi += 1
        c.mid_from_m = max(float(s[lo]), c.entry_m)
        c.mid_to_m = min(float(s[hi]), c.exit_m)


def alias(track: Track, mapping: Dict[str, str]) -> None:
    """`{"Hairpin": "T6"}` lets a claim say "Hairpin"."""
    for name, target in mapping.items():
        c = track.corner(target)
        if c is not None and name not in c.names:
            c.names.append(name)

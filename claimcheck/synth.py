"""
Synthetic VBOX sessions with mistakes planted where we choose.

The claim check is only worth trusting if it finds what is there and nothing
else. Real data cannot test that, because nobody knows the right answer. Here
the right answer is written into the generator: driver BB brakes 15 m early
at T2 and is 15 m late on the throttle at T5, and otherwise drives exactly
like AA, give or take noise. A correct checker supports the first two claims,
contradicts the obvious wrong ones, and says "can't tell" when the laps run
out.

The circuit is a closed loop of six corners (two of them a chicane), and the
speed comes from a forward-backward solver with a friction limit, power-limited
acceleration and drag. It is not a vehicle model. It only needs to produce
traces with the shape of real ones. The files are written in the real `.vbo`
layout with every quirk `claimcheck.ingest.vbo` has to handle: minutes for
position, longitude positive west, HHMMSS time, units aligned to the tail of
the channel list, CRLF.

It contains no real data, so anyone can run it.

    python -m claimcheck.synth out/        # writes AA.vbo and BB.vbo
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from claimcheck.car import GENERIC

G = 9.80665
MU = 1.35                 # lateral grip, g
BRAKE_G = 1.25
TRACTION_G = 0.65
POWER_W = 350_000.0       # generic, round
MASS_KG = 1400.0          # generic: car plus driver
CDA = 0.85
RHO = 1.2
V_TOP = 250.0 / 3.6
WHEELBASE = GENERIC.wheelbase_m
STEER_RATIO = GENERIC.steering_ratio
DS = 0.5                  # solver grid, m

ORIGIN = (50.0, 6.0)      # somewhere in the Eifel; no real circuit
LINE_ON_A = 100.0         # start/finish, metres into the first straight

#: (kind, a, b): straight length | arc (radius, signed degrees, + = left).
_PIECES: List[Tuple[str, float, float]] = [
    ("straight", 800.0, 0.0),
    ("arc", 25.0, 90.0),       # T1, a hairpin
    ("straight", 400.0, 0.0),
    ("arc", 60.0, 90.0),       # T2
    ("straight", 300.0, 0.0),
    ("arc", 80.0, -25.0),      # T3, chicane right
    ("arc", 80.0, 25.0),       # T4, chicane left
    ("straight", None, 0.0),   # closes x
    ("arc", 40.0, 90.0),       # T5
    ("straight", None, 0.0),   # closes y
    ("arc", 120.0, 90.0),      # T6, fast
]


@dataclass
class Circuit:
    s: np.ndarray              # from the line
    x: np.ndarray
    y: np.ndarray
    heading: np.ndarray        # radians, math convention
    kappa: np.ndarray          # 1/m, + = left
    corners: List[Tuple[float, float, float]]   # (start, end, radius) from the line
    length: float


def circuit() -> Circuit:
    """Lay the pieces out, solve the two free straights so the loop closes."""
    def trace(free: Sequence[float]):
        pts, kap = [(0.0, 0.0, 0.0)], [0.0]
        arcs: List[Tuple[float, float, float]] = []
        x = y = h = 0.0
        s = 0.0
        fi = iter(free)
        for kind, a, deg in _PIECES:
            if kind == "straight":
                length = a if a is not None else next(fi)
                n = max(int(round(length / DS)), 1)
                for _ in range(n):
                    x += math.cos(h) * length / n
                    y += math.sin(h) * length / n
                    pts.append((x, y, h)); kap.append(0.0)
                s += length
            else:
                radius, ang = a, math.radians(deg)
                length = abs(ang) * radius
                n = max(int(round(length / DS)), 1)
                k = math.copysign(1.0 / radius, ang)
                start = s
                for _ in range(n):
                    h0 = h
                    h += ang / n
                    hm = 0.5 * (h0 + h)
                    x += math.cos(hm) * length / n
                    y += math.sin(hm) * length / n
                    pts.append((x, y, h)); kap.append(k)
                s += length
                arcs.append((start, s, radius))
        return np.array(pts), np.array(kap), arcs, s

    pts, _, _, _ = trace([0.0, 0.0])
    ex, ey = pts[-1, 0], pts[-1, 1]
    # The two free straights run west (closes x) and south (closes y).
    pts, kap, arcs, total = trace([ex, ey])
    seg = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
    s = np.concatenate(([0.0], np.cumsum(seg)))
    # Re-index from the start/finish line.
    i0 = int(np.searchsorted(s, LINE_ON_A))
    roll = lambda a: np.concatenate((a[i0:-1], a[:i0]))
    x, y, h, k = roll(pts[:, 0]), roll(pts[:, 1]), roll(pts[:, 2]), roll(kap)
    length = float(s[-1])
    s_line = np.concatenate((s[i0:-1] - s[i0], s[:i0] + length - s[i0]))
    corners = [((a - s[i0]) % length, (b - s[i0]) % length, r) for a, b, r in arcs]
    corners.sort()
    return Circuit(s_line, x, y, h, k, corners, length)


@dataclass
class Style:
    """How one driver drives. Corner numbers are 1-based from the line."""

    name: str
    brake_early_m: Dict[int, float] = field(default_factory=dict)
    late_throttle_m: Dict[int, float] = field(default_factory=dict)
    slow_kph: Dict[int, float] = field(default_factory=dict)
    understeer_deg: Dict[int, float] = field(default_factory=dict)
    noise_m: float = 0.5
    noise_v: float = 0.002
    seed: int = 1
    #: Every driver leaves a little on the table everywhere, so noise can go
    #: both ways without asking for more than the friction limit gives.
    base_m: float = 6.0


def _a_acc(v: np.ndarray | float) -> np.ndarray | float:
    v = np.maximum(v, 1.0)
    drive = np.minimum(TRACTION_G * G, POWER_W / (MASS_KG * v))
    return drive - 0.5 * RHO * CDA * v * v / MASS_KG


def _a_brk(v: float) -> float:
    return BRAKE_G * G + 0.5 * RHO * CDA * v * v / MASS_KG


def drive(c: Circuit, style: Style, laps: int, rng: np.random.Generator):
    """
    Speed along the whole session: an out-lap fragment, `laps` full laps,
    an in-lap fragment. Returns arrays on the solver grid.
    """
    L = c.length
    s_from, s_to = -0.3 * L, laps * L + 0.15 * L
    s = np.arange(s_from, s_to, DS)
    u = np.mod(s, L)
    kap = np.interp(u, c.s, c.kappa)
    with np.errstate(divide="ignore"):
        cap = np.minimum(V_TOP, np.sqrt(MU * G / np.maximum(np.abs(kap), 1e-9)))
    hold = np.zeros_like(s, dtype=bool)       # late-throttle holds
    under = np.zeros_like(s)

    for lap in range(-1, laps + 1):
        for n, (a, b, r) in enumerate(c.corners, start=1):
            a_abs, b_abs = lap * L + a, lap * L + b
            if b_abs < s_from or a_abs > s_to:
                continue
            v_c = math.sqrt(MU * G * r) * (1.0 + rng.normal(0.0, style.noise_v))
            v_c -= style.slow_kph.get(n, 0.0) / 3.6
            v_c = min(v_c, math.sqrt(MU * G * r))
            early = max(style.base_m + style.brake_early_m.get(n, 0.0)
                        + rng.normal(0.0, style.noise_m), 0.0)
            late = max(style.base_m + style.late_throttle_m.get(n, 0.0)
                       + rng.normal(0.0, style.noise_m), 0.0)
            m = (s >= a_abs - early) & (s <= b_abs + late)
            cap[m] = np.minimum(cap[m], v_c)
            hold |= (s > b_abs) & (s <= b_abs + late)
            under[(s >= a_abs) & (s <= b_abs)] = style.understeer_deg.get(n, 0.0)

    v = cap.copy()
    v[0] = min(v[0], 100.0 / 3.6)
    for i in range(len(v) - 2, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2.0 * _a_brk(v[i + 1]) * DS))
    for i in range(len(v) - 1):
        v[i + 1] = min(v[i + 1], math.sqrt(v[i] ** 2 + 2.0 * float(_a_acc(v[i])) * DS))

    a = np.gradient(v * v, DS) / 2.0
    drag = 0.5 * RHO * CDA * v * v / MASS_KG
    braking = a < -(drag + 0.5)
    brake = np.where(braking, (-a - drag) / G * 80.0, 0.0)
    full = (a >= 0.9 * _a_acc(v)) | (v >= V_TOP - 0.5)
    throttle = np.where(braking, 0.0, np.where(full, 100.0, 15.0))
    throttle = np.where(hold & ~braking, 12.0, throttle)
    return s, u, v, a, brake, throttle, kap, under


def write_session(path: str | Path, style: Style, laps: int = 6, hz: float = 10.0,
                  start_utc: str = "10:00:00", day: str = "09/10/2026") -> Path:
    """Write one driver's session as a `.vbo`. Returns the path."""
    rng = np.random.default_rng(style.seed)
    c = circuit()
    s, u, v, a, brake, throttle, kap, under = drive(c, style, laps, rng)

    t_grid = np.concatenate(([0.0], np.cumsum(DS / np.maximum(0.5 * (v[1:] + v[:-1]), 0.5))))
    t = np.arange(0.0, t_grid[-1], 1.0 / hz)
    at = lambda arr: np.interp(t, t_grid, arr)
    ss, uu = at(s), np.mod(at(s), c.length)
    vv = at(v)
    x = np.interp(uu, c.s, c.x) + rng.normal(0.0, 0.3, len(t))
    y = np.interp(uu, c.s, c.y) + rng.normal(0.0, 0.3, len(t))
    head = np.interp(uu, c.s, np.unwrap(c.heading))
    kk = at(kap)
    ay_g = np.clip(vv * vv * kk / G, -1.8, 1.8)
    steer = (kk * WHEELBASE * 57.29578 + np.sign(kk) * at(under)) * STEER_RATIO
    steer = steer + rng.normal(0.0, 0.3, len(t))
    pbrk = np.clip(at(brake), 0.0, None)
    thr = at(throttle)
    along = at(a)

    lat0, lon0 = ORIGIN
    lat = lat0 + y / 111132.0
    lon = lon0 + x / (111320.0 * math.cos(math.radians(lat0)))
    crossings = np.floor(ss / c.length).astype(int) + 1        # lap 1 = the out-lap
    t_cross = np.interp(np.arange(0, crossings.max() + 1) * c.length, ss, t)
    lag = np.searchsorted(t_cross, t - 0.6, side="right")      # the lap counter steps late
    lap_number = 1 + lag

    h0, m0, s0 = (int(p) for p in start_utc.split(":"))
    clock = h0 * 3600 + m0 * 60 + s0 + t
    hh = np.floor(clock / 3600) % 24
    mm = np.floor((clock % 3600) / 60)
    sec = clock % 60
    hhmmss = hh * 10000 + mm * 100 + sec

    names = ["satellites", "time", "latitude", "longitude", "velocity kmh", "heading",
             "height", "vertical velocity m/s", "sampleperiod", "solution type",
             "lap_number", "throttle_pct", "brake_bar", "steering_deg",
             "accel_long_ms2", "accel_lat_g", "pit_limiter", "full_course_yellow"]
    units = ["s", "(null)", "(null)", "%", "bar", "°", "m/s²", "G", "(null)", "(null)"]
    gx = np.interp(0.0, c.s, c.x)
    gy = np.interp(0.0, c.s, c.y)
    def to_min(xm, ym):
        la = lat0 + ym / 111132.0
        lo = lon0 + xm / (111320.0 * math.cos(math.radians(lat0)))
        return -lo * 60.0, la * 60.0
    g1 = to_min(gx, gy - 4.0)
    g2 = to_min(gx, gy + 4.0)

    lines = [f"File created on {day} @ {start_utc}", "[header]", *names,
             "[channel units]", *units,
             "[comments]", "Synthetic session written by claimcheck.synth — not real data.",
             f"Driver style: {style.name}", "<Unit Info>", "Type : SYNTH", "Serial : 000000", "",
             "[laptiming]",
             f"Start        {g1[0]:+.6f} {g1[1]:+.6f} {g2[0]:+.6f} {g2[1]:+.6f} ¬ Start / Finish", "",
             "[column names]",
             "sats time lat long velocity heading height vert-vel Tsample solution_type "
             "lap_number throttle_pct brake_bar steering_deg accel_long_ms2 accel_lat_g "
             "pit_limiter full_course_yellow",
             "", "[data]"]
    compass = np.mod(90.0 - np.degrees(head), 360.0)
    for i in range(len(t)):
        lines.append(
            f"014 {hhmmss[i]:010.3f} {lat[i] * 60:+014.8f} {-lon[i] * 60:+014.8f} "
            f"{vv[i] * 3.6:07.3f} {compass[i]:07.3f} +00010.00 +0000.00 {1.0 / hz:.3f} 02 "
            f"{lap_number[i]:+.6E} {thr[i]:+.6E} {pbrk[i]:+.6E} {-steer[i]:+.6E} "
            f"{along[i]:+.6E} {ay_g[i]:+.6E} +0.000000E+00 +0.000000E+00")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


#: The demo pair. BB's two mistakes are the known answers the tests check for.
#: Their noise is small on purpose: in a hairpin, 2 m of throttle pick-up is
#: a tenth of a second, so a corner meant to show *no* difference needs a
#: driver more consistent than any real one.
AA = Style("AA", seed=11)
BB = Style("BB", brake_early_m={2: 15.0}, late_throttle_m={5: 15.0}, seed=23)


def demo(directory: str | Path, laps: int = 6, hz: float = 10.0) -> List[Path]:
    d = Path(directory)
    return [write_session(d / "AA.vbo", AA, laps, hz, start_utc="10:00:00"),
            write_session(d / "BB.vbo", BB, laps, hz, start_utc="10:20:00")]


if __name__ == "__main__":  # pragma: no cover
    import sys
    out = demo(sys.argv[1] if len(sys.argv) > 1 else "synthetic")
    print("\n".join(str(p) for p in out))

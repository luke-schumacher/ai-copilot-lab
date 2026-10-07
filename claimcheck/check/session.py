"""
From logger files to laps with a driver's name on them.

The `.vbo` carries no driver channel, so who drove is given from outside:
per file (`AA`) or per lap range within a file (`AA=1-6,BB=7-12`). Without
it, a lap belongs to the car number in the file name (`#31`), which is enough
to use the tool and honest about what it knows.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from claimcheck.check import thresholds as th
from claimcheck.ingest.vbo import VboSession, read_vbo

G = 9.80665

#: `100-GT-31-0001.vbo` -> car 31
_CAR = re.compile(r"^\d+-[A-Za-z0-9]+-(\d+)-")


@dataclass
class LapTrace:
    """One timed lap, its channels re-zeroed at the start/finish line."""

    driver: str
    source: str
    number: int
    stint: int
    age: int                 # laps since the stint began: a tyre-age proxy
    time_s: float
    valid: bool = True
    why_invalid: str = ""
    t: np.ndarray = field(repr=False, default=None)        # s since the line
    x: np.ndarray = field(repr=False, default=None)        # m, local frame
    y: np.ndarray = field(repr=False, default=None)
    v_kph: np.ndarray = field(repr=False, default=None)
    throttle: np.ndarray = field(repr=False, default=None)  # %
    brake: np.ndarray = field(repr=False, default=None)     # bar
    steer: np.ndarray = field(repr=False, default=None)     # steering-wheel deg
    ay_g: np.ndarray = field(repr=False, default=None)
    s: Optional[np.ndarray] = field(repr=False, default=None)  # set by projection

    @property
    def key(self) -> str:
        return f"{self.driver}:{self.source}:{self.number}"

    @property
    def label(self) -> str:
        return f"{self.driver} lap {self.number}"


@dataclass
class Dataset:
    """Everything loaded: laps, the files they came from, the local frame."""

    laps: List[LapTrace]
    files: List[dict]
    origin: Tuple[float, float]           # lat, lon in degrees
    channels_missing: Dict[str, List[str]]

    @property
    def drivers(self) -> List[str]:
        out: List[str] = []
        for lp in self.laps:
            if lp.driver not in out:
                out.append(lp.driver)
        return out

    def valid(self, driver: Optional[str] = None) -> List[LapTrace]:
        return [lp for lp in self.laps
                if lp.valid and (driver is None or lp.driver == driver)]

    def best(self, driver: Optional[str] = None) -> Optional[LapTrace]:
        laps = self.valid(driver)
        return min(laps, key=lambda lp: lp.time_s) if laps else None

    def has_channel(self, name: str) -> bool:
        return not any(name in miss for miss in self.channels_missing.values())


# ---- driver assignment ------------------------------------------------

def default_driver(path: Path) -> str:
    m = _CAR.match(path.name)
    return f"#{m.group(1)}" if m else path.stem


def parse_driver_spec(spec: Optional[str], path: Path) -> List[Tuple[str, Optional[Tuple[int, int]]]]:
    """
    `None` -> the car number. `AA` -> the whole file. `AA=1-6,BB=7-12` -> by
    `lap_number` range, inclusive. A bare number range on one name also works:
    `AA=3-9` drops everything else in the file.
    """
    if not spec:
        return [(default_driver(path), None)]
    out: List[Tuple[str, Optional[Tuple[int, int]]]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            out.append((part, None))
            continue
        name, rng = (p.strip() for p in part.split("=", 1))
        if "-" in rng:
            a, b = (int(v) for v in rng.split("-", 1))
        else:
            a = b = int(rng)
        out.append((name, (min(a, b), max(a, b))))
    return out


def _driver_for(lap_number: int, spec) -> Optional[str]:
    for name, rng in spec:
        if rng is None or rng[0] <= lap_number <= rng[1]:
            return name
    return None


# ---- loading -------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def to_local(lat_deg: np.ndarray, lon_deg: np.ndarray, origin) -> Tuple[np.ndarray, np.ndarray]:
    """Equirectangular metres about `origin`. Exact enough over a circuit."""
    lat0, lon0 = origin
    m_lat = 111132.0
    m_lon = 111320.0 * math.cos(math.radians(lat0))
    return (lon_deg - lon0) * m_lon, (lat_deg - lat0) * m_lat


def from_local(x: float, y: float, origin) -> Tuple[float, float]:
    """Inverse of `to_local`: (lat, lon) in degrees."""
    lat0, lon0 = origin
    return (lat0 + y / 111132.0, lon0 + x / (111320.0 * math.cos(math.radians(lat0))))


_NEEDED = {
    "velocity kmh": "speed",
    "throttle_pct": "throttle",
    "brake_bar": "brake pressure",
    "accel_lat_g": "lateral acceleration",
    "steering_deg": "steering angle",
}


def load(paths: Sequence[str | Path], drivers: Optional[Sequence[Optional[str]]] = None) -> Dataset:
    """
    Read every file, cut it into start/finish-timed laps, name the drivers
    and mark which laps count.

    `drivers[i]` is the driver spec for `paths[i]`; missing entries default to
    the car number.
    """
    paths = [Path(p).expanduser() for p in paths]
    expanded: List[Path] = []
    for p in paths:
        expanded.extend(sorted(p.glob("*.vbo")) if p.is_dir() else [p])
    drivers = list(drivers or [])

    laps: List[LapTrace] = []
    files: List[dict] = []
    missing: Dict[str, List[str]] = {}
    origin = None

    for i, path in enumerate(expanded):
        session = read_vbo(path)
        spec = parse_driver_spec(drivers[i] if i < len(drivers) else None, path)
        if origin is None:
            if session.gates:
                g = session.gates[0]
                origin = ((g.lat1 + g.lat2) / 2.0, (g.lon1 + g.lon2) / 2.0)
            else:
                origin = (float(session.latitude_deg[0]), float(session.longitude_deg[0]))
        missing[path.name] = [label for ch, label in _NEEDED.items() if ch not in session]
        file_laps = _laps_from(session, path, spec, origin)
        laps.extend(file_laps)
        files.append({
            "name": path.name,
            "path": str(path),
            "sha256": _sha256(path),
            "hz": round(session.sample_hz, 1),
            "recorded": str(session.created) if session.created else None,
            "drivers": [name for name, _ in spec],
            "laps": len(file_laps),
        })

    _mark_validity(laps)
    return Dataset(laps=laps, files=files, origin=origin or (0.0, 0.0),
                   channels_missing=missing)


def _col(session: VboSession, name: str, n: int) -> np.ndarray:
    v = session.get(name)
    return np.asarray(v, float) if v is not None else np.full(n, np.nan)


def _laps_from(session: VboSession, path: Path, spec, origin) -> List[LapTrace]:
    n = session.n_samples
    t_all = session.elapsed_s
    x_all, y_all = to_local(session.latitude_deg, session.longitude_deg, origin)
    v = _col(session, "velocity kmh", n)
    thr = _col(session, "throttle_pct", n)
    brk = _col(session, "brake_bar", n)
    steer = _col(session, "steering_deg", n)
    ay = _col(session, "accel_lat_g", n)
    pit = _col(session, "pit_limiter", n)
    fcy = _col(session, "full_course_yellow", n)

    out: List[LapTrace] = []
    stint, age = 0, 0
    prev: Optional[Tuple[str, int]] = None
    pitted = False
    for lap in session.timed_laps():
        driver = _driver_for(lap.number, spec)
        if driver is None:
            continue
        # One sample either side, so interpolation reaches the line.
        a = max(lap.start - 1, 0)
        b = min(lap.stop + 1, n)
        sl = slice(a, b)
        # A new stint: another driver, a gap in the lap count, or a pit visit.
        if prev is not None and (driver != prev[0] or lap.number != prev[1] + 1 or pitted):
            stint, age = stint + 1, 0
        trace = LapTrace(
            driver=driver, source=path.name, number=lap.number, stint=stint,
            age=age, time_s=float(lap.duration_s),
            t=t_all[sl] - t_all[lap.start],
            x=x_all[sl], y=y_all[sl], v_kph=v[sl], throttle=thr[sl],
            brake=brk[sl], steer=steer[sl], ay_g=ay[sl],
        )
        in_lap = slice(lap.start, lap.stop)
        pitted = bool(np.nanmax(np.nan_to_num(pit[in_lap])) > 0.5)
        if pitted:
            trace.valid, trace.why_invalid = False, "pit-speed limiter on"
        elif np.nanmax(np.nan_to_num(fcy[in_lap])) > 0.5:
            trace.valid, trace.why_invalid = False, "full-course yellow"
        out.append(trace)
        prev = (driver, lap.number)
        age += 1
    return out


def _mark_validity(laps: List[LapTrace]) -> None:
    by_driver: Dict[str, List[LapTrace]] = {}
    for lp in laps:
        by_driver.setdefault(lp.driver, []).append(lp)
    for driver_laps in by_driver.values():
        clean = [lp.time_s for lp in driver_laps if lp.valid]
        if not clean:
            continue
        best = min(clean)
        for lp in driver_laps:
            if not lp.valid:
                continue
            if lp.time_s > th.VALID_LAP_FACTOR * best:
                lp.valid = False
                lp.why_invalid = f"+{lp.time_s - best:.1f} s off best (over {th.VALID_LAP_FACTOR:.0%})"

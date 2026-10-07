#!/usr/bin/env python3
"""
Racelogic VBOX `.vbo` session logs.

The format is plain ASCII with CRLF line endings and `[section]` headers, which
makes it look easier than it is. Five things bite:

**Units are offset from channels, not parallel to them.** `[header]` lists every
channel; `[channel units]` lists fewer, because the leading GPS channels carry
their units in their names (`velocity kmh`, `vertical velocity m/s`). The unit
list aligns with the *tail* of the channel list, so it is indexed from
`len(channels) - len(units)`. Zipping the two from the front silently mislabels
everything.

**Latitude and longitude are in minutes, and longitude is positive WEST.** A file
that opens at `+3000.000000, -360.000000` is at 50.0 N, 6.0 E: divide by 60 and
flip the longitude sign. This is the Racelogic convention, not a bug in the file,
and it is the easiest way to silently ruin a track map.

**`time` is a clock reading, not an elapsed time.** `103531.600` is 10:35:31.600
UTC, packed as HHMMSS.sss. Read as a float it is a number near a hundred
thousand that increases in jumps of 40 at every minute boundary.

**Lap numbers are not lap boundaries.** `lap_number` is a counter stepped by the
logger's own trigger, and it can lag the real crossing of the line by a good
fraction of a second. Use `timed_laps()`, which finds the crossing itself.

**The start/finish line in `[laptiming]` is a point, not an orientation.** Some
files write it as a short segment lying along the track, so a which-side-of-the-
line test can miss laps. `crossings()` uses closest approach to the midpoint
instead, which is what a transponder measures.

Run it:  python -m claimcheck.ingest.vbo <session.vbo>
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

__all__ = ["Channel", "Gate", "Lap", "VboSession", "read_vbo"]

#: Channels whose unit is carried in the name rather than in `[channel units]`.
#: Their count is how far the unit list is offset; it is derived per file rather
#: than hard-coded, because a different VBOX configuration leads with a
#: different set.
_SECTION = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_CREATED = re.compile(r"created on (\d{2})/(\d{2})/(\d{4})")
_UNIT_INFO = re.compile(r"^\s*(?P<key>[A-Za-z][A-Za-z ]*?)\s*:\s*(?P<value>.+?)\s*$")

#: Columns needing a decode rather than a plain float cast.
LATITUDE = "latitude"
LONGITUDE = "longitude"
TIME = "time"


@dataclass(frozen=True)
class Channel:
    """One logged channel: the name as `[header]` spells it, plus its unit."""

    name: str
    unit: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.name} ({self.unit})" if self.unit else self.name


@dataclass(frozen=True)
class Gate:
    """
    A timing line from `[laptiming]`, as two points in decimal degrees.

    The file gives them in minutes with longitude positive-west, the same
    convention as the position columns.
    """

    name: str
    label: str
    lon1: float
    lat1: float
    lon2: float
    lat2: float


@dataclass(frozen=True)
class Lap:
    """
    One lap, located by `lap_number` transitions.

    `duration_s` is **approximate** — it is the span of samples carrying this
    lap number, so it is right to within one sample period at each end. Use the
    beacon or the start/finish line for a timing reference.
    """

    number: int
    start: int
    stop: int  # exclusive
    duration_s: float

    @property
    def n_samples(self) -> int:
        return self.stop - self.start


@dataclass
class VboSession:
    """A parsed `.vbo`. Channel data is held column-wise as float arrays."""

    path: Path
    channels: List[Channel]
    columns: Dict[str, np.ndarray]
    created: Optional[date] = None
    #: `<Unit Info>` from `[comments]` — logger type, serial, firmware.
    unit_info: Dict[str, str] = field(default_factory=dict)
    #: Timing lines from `[laptiming]`, the first of which is start/finish.
    gates: List[Gate] = field(default_factory=list)
    #: Video files named in `[AVI]`, if the session was recorded with cameras.
    avi: List[str] = field(default_factory=list)

    # ---- basics -------------------------------------------------------

    @property
    def names(self) -> List[str]:
        return [c.name for c in self.channels]

    @property
    def n_samples(self) -> int:
        return len(next(iter(self.columns.values()))) if self.columns else 0

    def __contains__(self, name: str) -> bool:
        return name in self.columns

    def __getitem__(self, name: str) -> np.ndarray:
        try:
            return self.columns[name]
        except KeyError:
            raise KeyError(
                f"{name!r} is not in this log. Available: {', '.join(self.names)}"
            ) from None

    def get(self, name: str, default=None):
        return self.columns.get(name, default)

    def unit(self, name: str) -> str:
        for c in self.channels:
            if c.name == name:
                return c.unit
        raise KeyError(name)

    # ---- decoded views ------------------------------------------------

    @property
    def utc_seconds(self) -> np.ndarray:
        """`time` (HHMMSS.sss) as seconds since midnight UTC, midnight-safe."""
        raw = self[TIME]
        hh = np.floor(raw / 10000.0)
        mm = np.floor((raw - hh * 10000.0) / 100.0)
        ss = raw - hh * 10000.0 - mm * 100.0
        secs = hh * 3600.0 + mm * 60.0 + ss
        # A session running through midnight wraps; unwrap it forward.
        wraps = np.concatenate(([0.0], np.cumsum(np.diff(secs) < -43200.0) * 86400.0))
        return secs + wraps

    @property
    def elapsed_s(self) -> np.ndarray:
        """Seconds from the first sample. The time base for everything else."""
        t = self.utc_seconds
        return t - t[0]

    @property
    def sample_hz(self) -> float:
        """Median logging rate, measured rather than taken from `sampleperiod`."""
        dt = np.diff(self.utc_seconds)
        dt = dt[dt > 0]
        return float(1.0 / np.median(dt)) if dt.size else float("nan")

    @property
    def latitude_deg(self) -> np.ndarray:
        """Decimal degrees north. The file stores minutes."""
        return self[LATITUDE] / 60.0

    @property
    def longitude_deg(self) -> np.ndarray:
        """Decimal degrees **east**. The file stores minutes, positive west."""
        return -self[LONGITUDE] / 60.0

    # ---- laps ---------------------------------------------------------

    def laps(self, channel: str = "lap_number") -> List[Lap]:
        """
        Slice the session on `lap_number` transitions.

        Returns laps in the order they were driven. See `Lap.duration_s` for why
        the durations are approximate.
        """
        if channel not in self:
            return []
        nums = self[channel].astype(int)
        t = self.utc_seconds
        edges = np.flatnonzero(np.diff(nums)) + 1
        bounds = np.concatenate(([0], edges, [len(nums)]))
        out: List[Lap] = []
        for start, stop in zip(bounds[:-1], bounds[1:]):
            if stop <= start:
                continue
            out.append(
                Lap(
                    number=int(nums[start]),
                    start=int(start),
                    stop=int(stop),
                    duration_s=float(t[stop - 1] - t[start]),
                )
            )
        return out

    def lap(self, number: int) -> Optional[Lap]:
        return next((lp for lp in self.laps() if lp.number == number), None)

    def slice(self, lap: Lap) -> Dict[str, np.ndarray]:
        """The columns of one lap, as a fresh dict of views."""
        return {k: v[lap.start : lap.stop] for k, v in self.columns.items()}

    # ---- laps, properly ------------------------------------------------

    def crossings(self, gate: Optional[Gate] = None, min_gap_s: float = 20.0,
                  radius_m: float = 30.0) -> List[float]:
        """
        Times, in `elapsed_s`, at which the car passed the timing line.

        Detected as **closest approach to the line's midpoint**, not as a
        side-of-line crossing. Two properties of real files force that choice:

        *The line can be shorter than the car's stride.* At 200 kph a 10 Hz
        logger moves 5.6 m between samples, so a 6 m gate can be stepped clean
        over.

        *The line can be drawn along the track, not across it.* Extending it and
        testing which side the car is on then puts the intersection far from the
        midpoint and rejects laps. The gate marks **where** the line is, not its
        orientation.

        Closest approach has neither problem and is what a transponder beacon
        measures anyway. Sub-sample precision comes from fitting a parabola to
        squared distance through the three samples around the minimum.

        `radius_m` is the capture radius. `min_gap_s` suppresses a second
        trigger from a car sitting near the line in the pit lane, and must be
        shorter than the shortest lap the circuit can produce — the default
        20 s is safe for any real one.
        """
        if gate is None:
            if not self.gates:
                return []
            gate = self.gates[0]

        cy, cx = (gate.lat1 + gate.lat2) / 2.0, (gate.lon1 + gate.lon2) / 2.0
        m_lat = 111132.0
        m_lon = 111320.0 * math.cos(math.radians(cy))
        dx = (self.longitude_deg - cx) * m_lon
        dy = (self.latitude_deg - cy) * m_lat
        d2 = dx * dx + dy * dy
        t = self.elapsed_s

        inside = d2 < radius_m * radius_m
        if not inside.any():
            return []

        # contiguous runs of samples inside the capture radius = one pass each
        edges = np.flatnonzero(np.diff(inside.astype(np.int8))) + 1
        bounds = edges.tolist()
        if inside[0]:
            bounds.insert(0, 0)
        if inside[-1]:
            bounds.append(len(inside))
        out: List[float] = []
        for a, b in zip(bounds[::2], bounds[1::2]):
            k = int(a + np.argmin(d2[a:b]))
            when = float(t[k])
            # parabola through (t, d2) at k-1, k, k+1; vertex is the true pass
            if 0 < k < len(t) - 1:
                y0, y1, y2 = d2[k - 1], d2[k], d2[k + 1]
                denom = y0 - 2.0 * y1 + y2
                if denom > 0:
                    shift = 0.5 * (y0 - y2) / denom          # in samples
                    if abs(shift) <= 1.0:
                        step = t[k + 1] - t[k - 1]
                        when = float(t[k] + shift * step / 2.0)
            if out and when - out[-1] < min_gap_s:
                continue
            out.append(when)
        return out

    def timed_laps(self, min_gap_s: float = 20.0) -> List[Lap]:
        """
        Laps bounded by start/finish crossings — the timing reference.

        Prefer this to `laps()`. `lap_number` is stepped by the logger's own
        trigger and can lag the line. A consistent lag mostly cancels out of lap
        *durations*, which is why `laps()` looks fine; it does not cancel out of
        lap *boundaries*, and half a second at 200 kph is about 28 m of track.
        That is the difference between attributing a mistake to the right corner
        and the one before it.

        Laps are numbered from the `lap_number` value at their start where that
        channel exists, so the numbering matches what the engineers see.
        """
        marks = self.crossings(min_gap_s=min_gap_s)
        if len(marks) < 2:
            return []
        t = self.elapsed_s
        nums = self["lap_number"].astype(int) if "lap_number" in self else None
        out: List[Lap] = []
        for a, b in zip(marks[:-1], marks[1:]):
            start = int(np.searchsorted(t, a, side="left"))
            stop = int(np.searchsorted(t, b, side="left"))
            if stop <= start:
                continue
            number = int(nums[start]) if nums is not None else len(out) + 1
            out.append(Lap(number=number, start=start, stop=stop,
                           duration_s=float(b - a)))
        return out


def _split_sections(text: str) -> Dict[str, List[str]]:
    """`[name]`-delimited sections. Text before the first header is `""`."""
    sections: Dict[str, List[str]] = {"": []}
    current = ""
    for line in text.splitlines():
        m = _SECTION.match(line.strip())
        if m:
            current = m.group("name").strip().lower()
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def _unit_info(comment_lines: Sequence[str]) -> Dict[str, str]:
    info: Dict[str, str] = {}
    for line in comment_lines:
        line = line.strip()
        if not line or line.startswith("<") or line.startswith("("):
            continue
        m = _UNIT_INFO.match(line)
        if m:
            info[m.group("key").strip()] = m.group("value").strip()
    return info


def _gates(lines: Sequence[str]) -> List[Gate]:
    """`<name> <lon1> <lat1> <lon2> <lat2> ¬ <label>`, in minutes, west-positive."""
    out: List[Gate] = []
    for line in lines:
        head, _, label = line.partition("\u00ac")
        parts = head.split()
        if len(parts) < 5:
            continue
        try:
            lon1, lat1, lon2, lat2 = (float(p) for p in parts[-4:])
        except ValueError:
            continue
        out.append(Gate(name=" ".join(parts[:-4]) or "gate",
                        label=label.strip() or "gate",
                        lon1=-lon1 / 60.0, lat1=lat1 / 60.0,
                        lon2=-lon2 / 60.0, lat2=lat2 / 60.0))
    return out


def read_vbo(path: str | Path) -> VboSession:
    """
    Parse a `.vbo` into a `VboSession`.

    Rows whose column count does not match the header are skipped rather than
    guessed at — a truncated final row is normal when a logger loses power.
    """
    path = Path(path).expanduser()
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
    sections = _split_sections(text)

    names = [ln.strip() for ln in sections.get("header", []) if ln.strip()]
    if not names:
        raise ValueError(f"{path}: no [header] section — is this a .vbo?")

    units = [ln.strip() for ln in sections.get("channel units", []) if ln.strip()]
    # The unit list aligns with the tail of the channel list, never the head.
    offset = len(names) - len(units)
    if offset < 0:
        raise ValueError(f"{path}: {len(units)} units for {len(names)} channels")
    padded = [""] * offset + units
    channels = [Channel(n, u) for n, u in zip(names, padded)]

    rows: List[List[float]] = []
    width = len(names)
    for line in sections.get("data", []):
        parts = line.split()
        if len(parts) != width:
            continue
        try:
            rows.append([float(p) for p in parts])
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"{path}: [data] holds no rows of {width} columns")

    table = np.asarray(rows, dtype=float)
    columns = {c.name: np.ascontiguousarray(table[:, i]) for i, c in enumerate(channels)}

    created = None
    m = _CREATED.search("\n".join(sections.get("", [])))
    if m:
        d, mo, y = (int(g) for g in m.groups())
        created = date(y, mo, d)

    return VboSession(
        path=path,
        channels=channels,
        columns=columns,
        created=created,
        unit_info=_unit_info(sections.get("comments", [])),
        gates=_gates(sections.get("laptiming", [])),
        avi=[ln.strip() for ln in sections.get("avi", []) if ln.strip()],
    )


def main(argv: Optional[Sequence[str]] = None) -> int:  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(description="Summarise a VBOX .vbo session log.")
    ap.add_argument("vbo")
    args = ap.parse_args(argv)

    s = read_vbo(args.vbo)
    print(f"{s.path.name}")
    print(f"  recorded   {s.created}  {s.unit_info.get('Type', '?')} "
          f"serial {s.unit_info.get('Serial', '?')}")
    print(f"  channels   {len(s.channels)}")
    print(f"  samples    {s.n_samples:,} at {s.sample_hz:.1f} Hz "
          f"({s.elapsed_s[-1] / 60:.1f} min)")
    print(f"  position   {s.latitude_deg[0]:.5f} N, {s.longitude_deg[0]:.5f} E")
    timed = s.timed_laps()
    print(f"  laps       {len(timed)} timed on the start/finish line")
    if timed:
        best = min(timed, key=lambda lp: lp.duration_s)
        for lp in timed:
            mins, secs = divmod(lp.duration_s, 60)
            mark = "  <- fastest" if lp is best else ""
            print(f"    {lp.number:>3}  {int(mins)}:{secs:06.3f}{mark}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

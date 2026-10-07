"""
Does this file honour the lap format? A skeleton for T8.

    python -m claimcheck.validate session.vbo

It reports `Issue`s; an `error` means the checker cannot use the file or would give
wrong answers, a `warning` means it can but you should look. Exit code 1 if there is
any error. This is the contract Group 1's recorder has to pass, so T8 extends it as
the contract in docs/LAP-FORMAT.md is agreed.

Done here: required channels present, time strictly increasing, a start/finish gate
present, the sampling rate stated and steady.
TODO (T8): units per channel, plausible value ranges, lap count, duplicate and
out-of-order rows, timestamps that carry both source time and receive time.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from claimcheck.ingest.vbo import read_vbo

#: Channels the checker needs (docs/LAP-FORMAT.md).
REQUIRED = ["time", "latitude", "longitude", "velocity kmh",
            "throttle_pct", "brake_bar", "steering_deg", "accel_lat_g"]
#: How far the sampling period may wander before it is worth a warning.
RATE_JITTER = 0.2


@dataclass(frozen=True)
class Issue:
    level: str        # "error" | "warning"
    code: str
    message: str


def validate(path: str | Path) -> List[Issue]:
    issues: List[Issue] = []
    try:
        s = read_vbo(path)
    except (ValueError, OSError) as exc:
        return [Issue("error", "unreadable", str(exc))]

    for name in REQUIRED:
        if name not in s:
            issues.append(Issue("error", "missing-channel", f"channel {name!r} is missing"))

    if "time" in s:
        t = s.utc_seconds
        dt = np.diff(t)
        bad = int((dt <= 0).sum())
        if bad:
            issues.append(Issue("error", "time-not-increasing",
                                f"time does not strictly increase at {bad} sample(s)"))
        good = dt[dt > 0]
        if good.size:
            med = float(np.median(good))
            spread = float(np.percentile(good, 95) - np.percentile(good, 5)) / med
            if spread > RATE_JITTER:
                issues.append(Issue("warning", "uneven-sampling",
                                    f"sampling period varies by {spread:.0%} (5th to 95th percentile)"))

    if not s.gates:
        issues.append(Issue("warning", "no-gate", "no start/finish line in [laptiming]"))
    return issues


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 1:
        print("usage: python -m claimcheck.validate session.vbo", file=sys.stderr)
        return 2
    issues = validate(argv[0])
    for i in issues:
        print(f"{i.level.upper():8} {i.code:22} {i.message}")
    if not issues:
        print("ok: no issues")
    return 1 if any(i.level == "error" for i in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())

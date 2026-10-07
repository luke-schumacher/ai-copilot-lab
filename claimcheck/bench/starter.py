"""
A minimal known-answer benchmark: the place to start for T1 and T2.

Each `Scenario` plants a mistake in one synthetic driver (BB), types a claim, and
says which answer is correct. `run` generates two sessions, asks the checker, and
returns the stamp it gave. `main` runs every scenario over several seeds and prints
how often the checker was right, wrong, or said "Can't tell yet".

This is deliberately small. T1 grows the scenario list (and moves it out of the
code into a file), T2 makes the run reproducible, parallel and tested in CI,
T3 replaces the counting here with proper metrics and intervals.

    python -m claimcheck.bench.starter            # 10 seeds
    python -m claimcheck.bench.starter 30         # 30 seeds
"""
from __future__ import annotations

import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from claimcheck import synth
from claimcheck.check.checker import Checker
from claimcheck.check.stats import CANT_TELL, CONTRADICTED, SUPPORTED


@dataclass(frozen=True)
class Scenario:
    name: str
    #: keyword arguments for `synth.Style` (the mistakes planted in BB)
    mistakes: Dict = field(default_factory=dict)
    claim: str = ""
    expected: str = SUPPORTED


SCENARIOS: List[Scenario] = [
    Scenario("brake-early-T2", {"brake_early_m": {2: 15.0}},
             "BB loses time in T2 because he brakes early", SUPPORTED),
    Scenario("wrong-cause-T5", {"late_throttle_m": {5: 15.0}},
             "BB loses time in T5 because he brakes early", CONTRADICTED),
    Scenario("no-mistake-T1", {},
             "BB loses time in T1", CONTRADICTED),
]


def run(scenario: Scenario, seed: int, laps: int = 6, hz: float = 10.0,
        workdir: Optional[Path] = None) -> str:
    """Generate AA (clean) and BB (with the mistakes), check the claim, return the stamp."""
    d = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="bench-"))
    a = synth.write_session(d / "AA.vbo", synth.Style("AA", seed=seed), laps, hz)
    b = synth.write_session(d / "BB.vbo",
                            synth.Style("BB", seed=seed + 1000, **scenario.mistakes),
                            laps, hz, start_utc="10:20:00")
    checker = Checker([a, b], ["AA", "BB"])
    return checker.check(scenario.claim).stamp


def run_all(seeds: List[int]) -> Dict[str, Counter]:
    """Per scenario: how often each stamp came out."""
    out: Dict[str, Counter] = {}
    for sc in SCENARIOS:
        out[sc.name] = Counter(run(sc, s) for s in seeds)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    n = int(argv[0]) if argv else 10
    seeds = list(range(1, n + 1))
    print(f"{n} seeds per scenario\n")
    print(f"{'scenario':18} {'expected':13} {'right':>6} {'wrong':>6} {'cant tell':>10}")
    for sc in SCENARIOS:
        counts = run_all_one(sc, seeds)
        right = counts[sc.expected]
        cant = counts[CANT_TELL] if sc.expected != CANT_TELL else 0
        wrong = n - right - cant
        print(f"{sc.name:18} {sc.expected:13} {right:>6} {wrong:>6} {cant:>10}")
    return 0


def run_all_one(sc: Scenario, seeds: List[int]) -> Counter:
    return Counter(run(sc, s) for s in seeds)


if __name__ == "__main__":
    raise SystemExit(main())

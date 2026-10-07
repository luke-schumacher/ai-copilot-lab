"""
The whole check, in one object: load once, then check as many claims as the
engineers want to type.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from claimcheck.check import claim as claim_mod
from claimcheck.check import track as track_mod
from claimcheck.check.claim import ClaimSpec
from claimcheck.check.measure import Measurements
from claimcheck.check.session import Dataset, load
from claimcheck.check.verdict import Verdict, judge


class Checker:
    def __init__(self, paths: Sequence[str | Path], drivers: Optional[Sequence[Optional[str]]] = None,
                 aliases: Optional[Dict[str, str]] = None, translator=None,
                 profile: Optional[dict] = None):
        t0 = time.perf_counter()
        self.paths = [str(p) for p in paths]
        self.driver_specs = list(drivers or [])
        self.data: Dataset = load(paths, drivers)
        if not self.data.valid():
            raise ValueError("no valid lap in the loaded files")
        self.profile = profile
        self.track = track_mod.build(self.data, profile=profile)
        self.aliases = dict(aliases or {})
        track_mod.alias(self.track, self.aliases)
        self.measurements = Measurements(self.data, self.track)
        self.translator = translator
        self.load_s = time.perf_counter() - t0

    @property
    def corner_names(self) -> List[str]:
        return [c.name for c in self.track.corners]

    def parse(self, text: str) -> tuple:
        """
        Read the sentence. Returns (spec used, rule spec, translator spec or None,
        note). The rule parser always runs; the translator, when there is one,
        takes precedence, and any disagreement between the two is reported.
        """
        rules = claim_mod.parse(text, self.data.drivers, self.corner_names, self._alias_map())
        if self.translator is None:
            return rules, rules, None, ""
        try:
            llm = self.translator(text, self.data.drivers, self.track.corners, self._alias_map())
        except Exception as exc:  # anything at all: the rules carry on alone
            return rules, rules, None, f"Claude translator off ({type(exc).__name__}); rule parser used"
        if llm is None:
            why = getattr(self.translator, "last_error", None) or "no answer"
            return rules, rules, None, f"Claude translator off ({why}); rule parser used"
        note = ""
        if rules.key() != llm.key() and (rules.effect or rules.causes):
            note = (f"The two readings differ — rule parser: \"{claim_mod.describe(rules)}\". "
                    f"Using Claude's reading.")
        return llm, rules, llm, note

    def _alias_map(self) -> Dict[str, str]:
        out = dict(self.aliases)
        for c in self.track.corners:
            for n in c.names:
                out.setdefault(n, c.name)
        return out

    def check(self, text: str) -> Verdict:
        t0 = time.perf_counter()
        spec, rules, llm, note = self.parse(text)
        verdict = judge(spec, self.measurements)
        if note:
            verdict.caveats.insert(0, note)
        verdict.parse_s = time.perf_counter() - t0  # type: ignore[attr-defined]
        verdict.rule_spec = rules                     # type: ignore[attr-defined]
        verdict.llm_spec = llm                        # type: ignore[attr-defined]
        return verdict

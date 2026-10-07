"""
A sentence becomes a test.

`ClaimSpec` is the one interface between reading a claim and judging it.
Two things produce it: the rule parser here, which needs no network and
always runs, and the Claude translator in `translate.py`, which reads freer
phrasing. The judge in `verdict.py` never sees the sentence, only the spec.

The rule parser reads English and German, because the engineers speak both.
Anything it recognises but cannot judge (oversteer, the racing line, setup)
is kept and reported with the reason, rather than dropped.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

OWN_BEST = "own-best"

#: cause -> (label, metric, direction). Direction is the sign of
#: (driver - reference) the claim asserts: an early brake point is a
#: *smaller* distance, so -1.
CAUSES: Dict[str, Tuple[str, str, int]] = {
    "brake_early": ("brakes early", "brake_point_m", -1),
    "brake_late": ("brakes late", "brake_point_m", +1),
    "brake_soft": ("brakes too softly", "peak_brake_bar", -1),
    "low_min_speed": ("too slow at the apex", "v_min_kph", -1),
    "late_throttle": ("late on the throttle", "throttle_on_m", +1),
    "late_full_throttle": ("late to full throttle", "full_throttle_m", +1),
    "coasting": ("coasts", "coasting_s", +1),
    "lifts": ("lifts / not committed", "full_throttle_share", -1),
    "understeer": ("understeers", "understeer_deg", +1),
}

#: Recognised, but not judged in this version, and why.
UNSUPPORTED: Dict[str, str] = {
    "oversteer": "Oversteer needs yaw rate, which is not in the channel set "
                 "this version reads.",
    "line": "The racing line and apex position need more position accuracy than "
            "a 10 Hz GPS gives.",
    "car": "This version checks the driver's inputs, not the car: setup, tyres "
           "and pressures are out of scope.",
}

EFFECTS = {"loses": "loses time", "gains": "gains time"}


@dataclass
class ClaimSpec:
    text: str
    driver: Optional[str] = None
    versus: Optional[str] = None      # a driver, OWN_BEST, or None (default)
    corner: Optional[str] = None      # "T1"
    effect: Optional[str] = None      # "loses" | "gains" | None
    causes: List[str] = field(default_factory=list)
    unsupported: List[str] = field(default_factory=list)
    unread: List[str] = field(default_factory=list)
    parser: str = "rules"

    def to_dict(self) -> dict:
        return asdict(self)

    def key(self) -> tuple:
        """What has to agree between two parsers for them to agree."""
        return (self.driver, self.versus, self.corner, self.effect,
                tuple(sorted(self.causes)))


# ---- vocabulary -----------------------------------------------------------

# A word that is not itself part of another claim: lets "brakes a bit early"
# through without letting "brakes early and late on the throttle" read as
# "brakes ... late".
_W = r"(?:(?!early|late|früh|spät|and|but|or|und|aber|then|dann)[\w']+\s+)"

_CAUSE_PATTERNS: List[Tuple[str, List[str]]] = [
    # Most specific first: matched text is blanked before the next looks.
    ("late_full_throttle", [
        r"late\s+(?:to|on|onto)\s+(?:the\s+)?full\s+(?:throttle|gas|power)",
        r"full\s+(?:throttle|gas)\s+" + _W + r"{0,2}(?:too\s+)?late",
        r"not\s+flat\s+(?:early|soon)\s+enough",
        r"(?:zu\s+)?spät\s+(?:auf\s+|am\s+)?vollgas",
        r"vollgas\s+" + _W + r"{0,2}(?:zu\s+)?spät",
    ]),
    ("brake_soft", [
        r"(?:not|n't|never)\s+brak\w*\s+(?:hard|firm)",
        r"brak\w*\s+" + _W + r"{0,2}(?:too\s+)?(?:soft|gentl|light|timid|lazy)",
        r"(?:low|little|not\s+enough)\s+brake\s+pressure",
        r"(?:zu\s+)?wenig\s+bremsdruck",
        r"brems\w*\s+" + _W + r"{0,2}(?:zu\s+)?(?:weich|zaghaft|vorsichtig|schwach)",
    ]),
    ("brake_early", [
        r"\bbrak\w*\s+" + _W + r"{0,2}(?:too\s+|much\s+too\s+)?early",
        r"\bearl(?:y|ier)\s+(?:on\s+the\s+)?brak",
        r"brake\s*points?\s+(?:is\s+|are\s+)?(?:too\s+)?early",
        r"on\s+the\s+brakes?\s+(?:\w+\s+){0,2}?(?:before|earlier\s+than|ahead\s+of)",
        r"\bvor\s+\S+\s+(?:auf\s+der\s+|auf\s+die\s+)?bremse",
        r"\bbrems\w*\s+" + _W + r"{0,2}(?:zu\s+|viel\s+zu\s+)?früh",
        r"\bfrüh\w*\s+(?:ge)?brems",
        r"bremspunkt\w*\s+(?:ist\s+)?(?:zu\s+)?früh",
    ]),
    ("brake_late", [
        r"\bbrak\w*\s+" + _W + r"{0,2}(?:too\s+|much\s+too\s+)?late",
        r"\blat(?:e|er)\s+brak",
        r"brake\s*points?\s+(?:is\s+|are\s+)?(?:too\s+)?late",
        r"\bbrems\w*\s+" + _W + r"{0,2}(?:zu\s+|viel\s+zu\s+)?spät",
        r"\bspät\w*\s+(?:ge)?brems",
        r"bremspunkt\w*\s+(?:ist\s+)?(?:zu\s+)?spät",
        r"overshoot",
    ]),
    ("late_throttle", [
        r"\blate\s+(?:on|to|onto|back\s+on)\s+(?:the\s+)?(?:throttle|gas|power)",
        r"(?:throttle|gas|power)\s+" + _W + r"{0,2}(?:too\s+)?late",
        r"(?:gets?|getting|goes|going|picks?|picking)\s+(?:back\s+)?(?:on(?:to)?\s+)?(?:the\s+)?"
        r"(?:throttle|gas|power)\s+" + _W + r"{0,2}late",
        r"(?:zu\s+)?spät\s+(?:am|ans|aufs|aufm|auf\s+dem|auf\s+das)\s+gas",
        r"gas\w*\s+" + _W + r"{0,2}(?:zu\s+)?spät",
    ]),
    ("low_min_speed", [
        r"too\s+slow\s+(?:in|through|at|mid|on)",
        r"slow\s+(?:at|in)\s+the\s+apex",
        r"(?:low|lower)\s+(?:minimum|min|apex|mid[- ]?corner|corner)\s+speed",
        r"apex\s+speed\s+(?:is\s+)?(?:too\s+)?low",
        r"over-?slow",
        r"carr(?:y|ies|ying)\s+(?:too\s+)?little\s+speed",
        r"not\s+enough\s+(?:corner\s+|mid[- ]?corner\s+|apex\s+|minimum\s+)?speed",
        r"(?:zu\s+)?wenig\s+(?:speed|geschwindigkeit|kurvengeschwindigkeit|tempo)",
        r"zu\s+langsam\s+(?:in|durch|im|am)",
        r"minimal\w*\s+" + _W + r"{0,2}(?:zu\s+)?(?:niedrig|gering)",
    ]),
    ("coasting", [
        r"\bcoast",
        r"\brollt\b", r"\brollen\b", r"ausroll", r"\bsegel",
        r"neither\s+(?:on\s+)?(?:the\s+)?throttle\s+nor\s+(?:the\s+)?brake",
    ]),
    ("lifts", [
        r"\blift(?:s|ing|ed)?\b",
        r"not\s+(?:going\s+)?flat\b",
        r"(?:doesn't|does\s+not|isn't|not)\s+commit",
        r"\blupft", r"gas\s+weg", r"nicht\s+voll\b",
    ]),
    ("understeer", [
        r"under-?steer", r"untersteuer", r"push(?:es|ing)?\s+wide", r"\bschiebt",
    ]),
]

_UNSUPPORTED_PATTERNS: List[Tuple[str, List[str]]] = [
    ("oversteer", [r"over-?steer", r"übersteuer", r"loose\s+rear", r"\bsnap",
                   r"rear\s+steps?\s+out", r"heck\s+kommt"]),
    ("line", [r"\bline\b", r"\blinie", r"apex\w*\s+(?:too\s+)?(?:early|late)",
              r"turn(?:s|ing)?[- ]in\s+(?:too\s+)?(?:early|late)", r"einlenk",
              r"scheitelpunkt", r"runs?\s+wide", r"track\s+limits"]),
    ("car", [r"damper", r"dämpfer", r"\barb\b", r"anti[- ]?roll", r"\bstabi",
             r"\bset-?up\b", r"\bwing\b", r"flügel", r"tyre\s+pressure",
             r"tire\s+pressure", r"reifendruck", r"ride\s+height", r"camber",
             r"\bsturz\b", r"\bspring", r"\bfeder", r"differential",
             r"\btyres?\b", r"\btires?\b", r"\breifen\b", r"\bgrip\b"]),
]

_LOSES = [r"\blos(?:e|es|ing|t)\b", r"\blost\b", r"time\s+loss", r"\bslower\b",
          r"\bslow\b", r"drops?\s+time", r"bleeds?\s+time", r"verlier\w*",
          r"\bverliert\b", r"langsamer", r"zeitverlust", r"büßt"]
_GAINS = [r"\bgain(?:s|ing|ed)?\b", r"\bfaster\b", r"\bquicker\b", r"gewinnt",
          r"schneller", r"picks?\s+up\s+time", r"makes?\s+up\s+time"]

_CORNER = re.compile(r"\b(?:t|turn|corner|kurve|c)\s*\.?\s*(\d{1,2})\b", re.I)
_OWN_BEST = re.compile(r"(?:his|her|their|own|seine[mnrs]?|ihre[mnrs]?|eigene[mnrs]?)\s+"
                       r"(?:own\s+)?(?:best|fastest|quickest|bestzeit|schnellste)", re.I)
_NEGATION = re.compile(r"(?:\bnot|n't|\bnever|\bnicht|\bkein\w*)\s+(?:[\w']+\s+){0,2}$", re.I)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFC", text).replace("’", "'").replace("`", "'")
    return " " + re.sub(r"\s+", " ", t.lower()).strip() + " "


def _blank(text: str, a: int, b: int) -> str:
    return text[:a] + " " * (b - a) + text[b:]


def _driver_pattern(name: str) -> re.Pattern:
    m = re.fullmatch(r"#\s*(\d+)", name)
    if m:
        n = m.group(1)
        return re.compile(rf"(?:#\s*{n}\b|\b(?:car|auto|nr\.?|no\.?|startnummer|der|die|the)\s*#?\s*{n}\b"
                          rf"|\b{n}(?:er|s)\b)", re.I)
    return re.compile(rf"(?<![\w#]){re.escape(name)}(?!\w)", re.I)


def parse(text: str, drivers: Sequence[str] = (), corners: Sequence[str] = (),
          aliases: Optional[Dict[str, str]] = None) -> ClaimSpec:
    """
    Rule parser. `drivers` and `corners` are what the loaded session holds;
    `aliases` maps a corner nickname to its T-number.
    """
    spec = ClaimSpec(text=text)
    t = _norm(text)

    # Drivers, in order of appearance: the first is the subject.
    found: List[Tuple[int, int, str]] = []
    for name in drivers:
        for m in _driver_pattern(name).finditer(t):
            found.append((m.start(), m.end(), name))
    found.sort()
    seen: List[Tuple[int, int, str]] = []
    for f in found:
        if f[2] not in (s[2] for s in seen):
            seen.append(f)
    if seen:
        spec.driver = seen[0][2]
        for a, b, name in seen[1:]:
            spec.versus = name
            break
    for a, b, _ in seen:
        t = _blank(t, a, b)
    if _OWN_BEST.search(t):
        spec.versus = OWN_BEST
    unknown = re.findall(r"(?<![\w#])([A-ZÄÖÜ]{2,3})(?![\w])", text)
    stray = [u for u in unknown if u not in drivers and not _CORNER.fullmatch(u)
             and u not in ("ARB", "FCY", "TC", "ABS")]
    if spec.driver is None and stray:
        spec.unread.append(f"'{stray[0]}' is not a driver in the loaded session")

    # Corner: explicit T-number first, then an alias.
    m = _CORNER.search(t)
    if m:
        spec.corner = f"T{int(m.group(1))}"
        t = _blank(t, m.start(), m.end())
        more = _CORNER.search(t)
        if more:
            spec.unread.append(f"one corner per check: used {spec.corner}")
    elif aliases:
        for alias, target in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
            am = re.search(rf"(?<!\w){re.escape(alias.lower())}(?!\w)", t)
            if am:
                spec.corner = target
                t = _blank(t, am.start(), am.end())
                break

    # Causes, most specific first, each match blanked so it is read once.
    for key, patterns in _CAUSE_PATTERNS + _UNSUPPORTED_PATTERNS:
        for p in patterns:
            mm = re.search(p, t)
            if not mm:
                continue
            if _NEGATION.search(t[:mm.start()]) and key in CAUSES and key not in ("brake_soft", "lifts"):
                spec.unread.append("negated causes are not checked; state the claim positively")
            elif key in CAUSES:
                if key not in spec.causes:
                    spec.causes.append(key)
            elif key not in spec.unsupported:
                spec.unsupported.append(key)
            t = _blank(t, mm.start(), mm.end())
            break

    # Effect: whichever of loses / gains appears first in what is left.
    hits = []
    for eff, patterns in (("loses", _LOSES), ("gains", _GAINS)):
        for p in patterns:
            mm = re.search(p, t)
            if mm:
                hits.append((mm.start(), eff))
    if hits:
        spec.effect = min(hits)[1]

    if not (spec.effect or spec.causes or spec.unsupported):
        spec.unread.append("no claim I can test: say who, which corner, and what — "
                           "e.g. 'AA loses time in T1 because he brakes early'")
    return spec


def describe(spec: ClaimSpec) -> str:
    """The claim back in plain words: what the engineer sees as 'understood'."""
    parts = [spec.driver or "?"]
    if spec.effect:
        parts.append(EFFECTS[spec.effect])
    if spec.corner:
        parts.append(f"in {spec.corner}")
    if spec.causes:
        joined = " and ".join(CAUSES[c][0] for c in spec.causes)
        parts.append(("because " if spec.effect else "") + joined)
    for key in spec.unsupported:
        parts.append({"oversteer": "oversteers", "line": "(the line)",
                      "car": "(the car / setup)"}[key] + " — not checkable")
    if spec.versus == OWN_BEST:
        parts.append("(against their own best lap)")
    elif spec.versus:
        parts.append(f"(against {spec.versus})")
    return " ".join(parts)

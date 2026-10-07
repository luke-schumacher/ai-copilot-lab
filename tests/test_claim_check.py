"""
The claim check against sessions whose answers are planted.

`claimcheck.synth` writes two drivers through the real `.vbo` format. BB brakes
15 m early at T2 and is 15 m late on the throttle at T5; everywhere else BB
drives like AA, give or take a little noise. A checker worth trusting finds
exactly that: it supports the two true claims, contradicts the false ones,
points at the right cause when the engineer names the wrong one, and says
"can't tell yet" when it has too little to go on.

No real data, no network, no model.
"""
from __future__ import annotations

import json

import pytest

from claimcheck import synth
from claimcheck.check import thresholds as th
from claimcheck.check.checker import Checker
from claimcheck.check.claim import parse
from claimcheck.check.stats import CANT_TELL, CONTRADICTED, SUPPORTED, compare, t95


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    return synth.demo(tmp_path_factory.mktemp("synth"))


@pytest.fixture(scope="module")
def checker(files):
    return Checker(files, ["AA", "BB"])


def stamp(checker, text):
    return checker.check(text).stamp


# ---- the circuit, as the tool sees it ------------------------------------

def test_six_corners_in_order_with_the_chicane_split(checker):
    corners = checker.track.corners
    assert [c.name for c in corners] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    # T3/T4 is the chicane: right then left.
    assert [c.direction for c in corners] == ["left", "left", "right", "left", "left", "left"]
    # Minimum speeds follow the radii: hairpin slowest, R120 fastest.
    v = [c.v_min_kph for c in corners]
    assert v[0] < v[4] < v[1] < v[2] < v[5]


def test_every_lap_is_timed_and_valid(checker):
    assert len(checker.data.valid("AA")) == 6
    assert len(checker.data.valid("BB")) == 6


# ---- the planted answers ---------------------------------------------------

@pytest.mark.parametrize("claim, expected", [
    ("BB loses time in T2 because he brakes early", SUPPORTED),
    ("BB brakes early in T2", SUPPORTED),
    ("BB brakes late in T2", CONTRADICTED),
    ("BB loses time in T5 because he is late on the throttle", SUPPORTED),
    ("BB loses time in T5 because he brakes early", CONTRADICTED),
    ("BB loses time in T1", CONTRADICTED),
    ("BB loses time in T6 because he coasts", CONTRADICTED),
    ("BB verliert Zeit in Kurve 2, weil er zu früh bremst", SUPPORTED),
    ("BB ist in T5 zu spät am Gas", SUPPORTED),
    ("AA gains time on BB in T2", SUPPORTED),
])
def test_known_answers(checker, claim, expected):
    v = checker.check(claim)
    assert v.stamp == expected, v.headline


def test_the_wrong_cause_points_at_the_right_one(checker):
    v = checker.check("BB loses time in T5 because he brakes early")
    assert v.stamp == CONTRADICTED
    assert v.pointers and v.pointers[0].name in ("late_throttle", "late_full_throttle")


def test_the_measured_mistakes_are_the_planted_size(checker):
    """
    BB reaches corner speed 15 m early at T2. The brake *onset* moves by less:
    the earlier braking curve meets a car that is still accelerating, so the
    onset shifts by 15 m x a_brake / (a_brake + a_accel), about 11 m on this
    straight. The throttle pick-up at T5 moves by the full 15 m.
    """
    early = checker.check("BB brakes early in T2").tests[-1].comparison
    late = checker.check("BB is late on the throttle in T5").tests[-1].comparison
    assert 8.0 <= early.mean_ref - early.mean_driver <= 16.0
    assert late.mean_driver - late.mean_ref == pytest.approx(15.0, abs=3.0)


def test_the_time_goes_where_the_cause_says(checker):
    v = checker.check("BB loses time in T2 because he brakes early")
    assert v.where["entry"] > 0.5 * sum(v.where.values())
    v = checker.check("BB loses time in T5 because he is late on the throttle")
    assert v.where["exit"] > 0.5 * sum(v.where.values())


# ---- can't tell yet, and why ---------------------------------------------

def test_too_few_laps(files):
    few = Checker(files, ["AA=1-2", "BB=1-2"])
    v = few.check("BB loses time in T2 because he brakes early")
    assert v.stamp == CANT_TELL and "clean lap" in v.headline


@pytest.mark.parametrize("claim, fragment", [
    ("BB loses time in T9", "no T9"),
    ("XY loses time in T1", "driver"),
    ("BB oversteers in T2", "yaw rate"),
    ("BB loses time", "Which corner"),
    ("BB is a bit off in T2", "no claim"),
    ("BB loses time in T2 because of the dampers", "setup"),
])
def test_cant_tell_says_why(checker, claim, fragment):
    v = checker.check(claim)
    assert v.stamp == CANT_TELL
    text = (v.headline + " " + " ".join(v.caveats)).lower()
    assert fragment.lower() in text, text


def test_a_flat_corner_has_no_brake_point_to_compare(checker):
    # T4, the second half of the chicane, is taken without braking.
    v = checker.check("BB brakes early in T4")
    assert v.stamp == CANT_TELL


# ---- the decision itself ---------------------------------------------------

def test_supported_and_contradicted_cannot_both_hold():
    for diff, half in [(0.2, 0.05), (0.06, 0.01), (0.0, 0.01), (-0.1, 0.02), (0.04, 0.1)]:
        c = compare([diff + x for x in (-half, 0, half)], [0.0, 0.0, 0.0], 0.05)
        assert c.stamp in (SUPPORTED, CONTRADICTED, CANT_TELL)


def test_t_quantiles():
    assert t95(1) == pytest.approx(6.314)
    assert t95(10) == pytest.approx(1.812)
    assert 1.725 > t95(22) > 1.708
    assert t95(1e6) == pytest.approx(1.645)


def test_contradicted_is_earned_not_defaulted():
    # A big, noisy difference is not "contradicted": it is "can't tell".
    c = compare([0.0, 0.6, -0.3], [0.0, 0.0], 0.05)
    assert c.stamp == CANT_TELL
    # A consistently tiny difference is.
    c = compare([0.01, 0.0, 0.02, 0.01], [0.0, 0.01, 0.0, 0.01], 0.05)
    assert c.stamp == CONTRADICTED


# ---- reading the sentence --------------------------------------------------

@pytest.mark.parametrize("text, driver, corner, effect, causes", [
    ("AA loses time in T1 because he brakes early", "AA", "T1", "loses", ["brake_early"]),
    ("AA brakes too early into turn 3", "AA", "T3", None, ["brake_early"]),
    ("BB is late on the throttle out of corner 12", "BB", "T12", None, ["late_throttle"]),
    ("BB is late to full throttle in T12", "BB", "T12", None, ["late_full_throttle"]),
    ("AA verliert in Kurve 6 Zeit, weil er zu früh bremst", "AA", "T6", "loses", ["brake_early"]),
    ("AA rollt zu lange in T2", "AA", "T2", None, ["coasting"]),
    ("AA untersteuert in T9", "AA", "T9", None, ["understeer"]),
    ("AA brakes early and is late on the throttle in T4", "AA", "T4", None,
     ["brake_early", "late_throttle"]),
    ("AA loses time to BB in T1", "AA", "T1", "loses", []),
])
def test_rule_parser(text, driver, corner, effect, causes):
    spec = parse(text, ["AA", "BB"], [f"T{i}" for i in range(1, 15)])
    assert (spec.driver, spec.corner, spec.effect) == (driver, corner, effect)
    assert sorted(spec.causes) == sorted(causes)


def test_versus_and_own_best():
    assert parse("AA loses time to BB in T1", ["AA", "BB"]).versus == "BB"
    assert parse("AA loses time in T1 against his own best", ["AA", "BB"]).versus == "own-best"


def test_car_number_names():
    spec = parse("car 31 brakes early in T1", ["#31"])
    assert spec.driver == "#31"


def test_alias():
    spec = parse("AA brakes early into the hairpin", ["AA"], aliases={"hairpin": "T6"})
    assert spec.corner == "T6"


def test_negation_is_not_silently_flipped():
    spec = parse("AA doesn't brake early in T1", ["AA"])
    assert "brake_early" not in spec.causes
    assert any("negated" in u for u in spec.unread)


# ---- same input, same output -------------------------------------------------

def test_deterministic(files):
    a = Checker(files, ["AA", "BB"]).check("BB loses time in T2 because he brakes early").to_dict()
    b = Checker(files, ["AA", "BB"]).check("BB loses time in T2 because he brakes early").to_dict()
    a.pop("checked_at"); b.pop("checked_at")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_rate_independent(tmp_path):
    files = [synth.write_session(tmp_path / "AA25.vbo", synth.AA, hz=25.0),
             synth.write_session(tmp_path / "BB25.vbo", synth.BB, hz=25.0)]
    ck = Checker(files, ["AA", "BB"])
    assert ck.check("BB loses time in T2 because he brakes early").stamp == SUPPORTED
    assert ck.check("BB loses time in T5 because he is late on the throttle").stamp == SUPPORTED


def test_thresholds_are_versioned():
    assert th.VERSION and set(th.TOL) >= {"corner_time_s", "brake_point_m"}


# ---- track profiles ------------------------------------------------------------

def test_profile_round_trip_keeps_names_and_aliases(files, tmp_path):
    from claimcheck.check.track import save_profile
    only_bb = Checker([files[1]], ["BB"])
    only_bb.track.corners[1].names.append("Bergkurve")
    save_profile(only_bb.track, only_bb.data.origin, tmp_path / "t.json", "synthetic")
    profile = json.loads((tmp_path / "t.json").read_text())
    profile["corners"][5]["name"] = "T6"          # an engineer's rename survives
    both = Checker(files, ["AA", "BB"], profile=profile)
    assert [c.name for c in both.track.corners] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert both.check("BB loses time in the Bergkurve because he brakes early").stamp == SUPPORTED


# ---- the translator, without a network -------------------------------------------

class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, payload, stop="end_turn"):
        self.content = [_FakeBlock(json.dumps(payload))]
        self.stop_reason = stop


def _fake_translator(payload=None, exc=None, stop="end_turn"):
    from claimcheck.check.translate import ClaudeTranslator
    pytest.importorskip("anthropic")
    tr = ClaudeTranslator.__new__(ClaudeTranslator)
    import anthropic
    tr._anthropic = anthropic
    tr.model, tr.last_error = "test", None

    class Messages:
        def create(self, **kw):
            Messages.kw = kw
            if exc is not None:
                raise exc
            return _FakeResponse(payload, stop)

    class Beta:
        messages = Messages()

    class Client:
        beta = Beta()

    tr.client = Client()
    return tr, Messages


def test_translator_reading_is_used_and_disagreement_reported(files):
    payload = {"driver": "BB", "versus": "none", "corner": "T2", "effect": "loses",
               "causes": ["brake_early"], "unsupported": [], "unread": []}
    tr, msgs = _fake_translator(payload)
    ck = Checker(files, ["AA", "BB"], translator=tr)
    v = ck.check("BB is way too careful into the second corner, on the brakes forever")
    assert v.spec.parser == "claude" and v.stamp == SUPPORTED
    schema = msgs.kw["output_config"]["format"]["schema"]
    assert schema["properties"]["corner"]["enum"][:2] == ["T1", "T2"]
    assert "BB" in schema["properties"]["driver"]["enum"]
    # The rules read nothing here, so there is nothing to disagree with.
    assert not any("readings differ" in c for c in v.caveats)

    # Where both read something and differ, the page says so.
    v = ck.check("BB loses time in T2 because he is late on the throttle")
    assert v.spec.causes == ["brake_early"]
    assert any("readings differ" in c and "late on the throttle" in c for c in v.caveats)


def test_translator_cannot_invent_a_corner(files):
    payload = {"driver": "BB", "versus": "none", "corner": "T99", "effect": "loses",
               "causes": ["teleports"], "unsupported": [], "unread": []}
    tr, _ = _fake_translator(payload)
    v = Checker(files, ["AA", "BB"], translator=tr).check("BB loses time in T99")
    assert v.spec.corner is None and v.spec.causes == [] and v.stamp == CANT_TELL


def test_translator_failure_falls_back_to_the_rules(files):
    anthropic = pytest.importorskip("anthropic")
    import httpx2 as httpx
    exc = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    tr, _ = _fake_translator(exc=exc)
    v = Checker(files, ["AA", "BB"], translator=tr).check("BB loses time in T2 because he brakes early")
    assert v.stamp == SUPPORTED and v.spec.parser == "rules"
    assert any("rule parser used" in c for c in v.caveats)


def test_translator_refusal_falls_back(files):
    tr, _ = _fake_translator({"driver": "BB"}, stop="refusal")
    v = Checker(files, ["AA", "BB"], translator=tr).check("BB loses time in T2 because he brakes early")
    assert v.spec.parser == "rules" and v.stamp == SUPPORTED

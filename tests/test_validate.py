"""The validator accepts a generated session and rejects the two obvious breakages."""
from claimcheck import synth
from claimcheck.validate import validate


def _session(tmp_path):
    return synth.write_session(tmp_path / "AA.vbo", synth.Style("AA", seed=1), laps=2)


def _codes(path):
    return {i.code for i in validate(path) if i.level == "error"}


def test_a_generated_session_has_no_errors(tmp_path):
    assert _codes(_session(tmp_path)) == set()


def test_a_missing_channel_is_an_error(tmp_path):
    p = _session(tmp_path)
    p.write_text(p.read_text().replace("brake_bar", "brake_x"))
    assert "missing-channel" in _codes(p)


def test_time_going_backwards_is_an_error(tmp_path):
    p = _session(tmp_path)
    lines = p.read_text().split("\n")
    i = lines.index("[data]") + 10
    lines[i], lines[i + 1] = lines[i + 1], lines[i]
    p.write_text("\n".join(lines))
    assert "time-not-increasing" in _codes(p)

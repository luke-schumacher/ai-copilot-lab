"""
The VBOX `.vbo` reader, against a log whose answers are known in advance.

Everything here is built from a fixture written in the test itself, small
enough to check on paper, and shaped to contain every trap the format sets:

* more channels than units, so the unit list has to align to the tail
* latitude and longitude in minutes, longitude positive-west
* `time` as HHMMSS.sss rather than elapsed seconds
* a ragged final row, as a logger losing power produces
* a start/finish line written as a short segment lying *along* the track

The car runs due north past the timing line at a known speed and loops, so
crossing times, lap durations and the decoded position are all arithmetic.

No simulator, no database, no real data.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from claimcheck.ingest.vbo import read_vbo

# A made-up start/finish line (50.05 N, 6.0 E), as the format writes it.
GATE_LAT_MIN = 3003.000000     # minutes north
GATE_LON_MIN = -360.000000     # minutes, positive west
M_PER_DEG_LAT = 111132.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(GATE_LAT_MIN / 60.0))

HZ = 10.0
LAP_S = 20.0                    # a short lap, so the fixture stays small
N_LAPS = 3
SPEED_KPH = 180.0
#: Must sit below the shortest lap. The fixture's 20 s lap is far shorter than
#: any real one, so the 20 s default would treat consecutive passes as one.
GAP_S = 5.0


#: Half the gate's span, in minutes. Some files write the line as a short
#: segment lying along the track; the fixture does the same, but places it
#: symmetrically about (GATE_LAT_MIN, GATE_LON_MIN) so the midpoint the reader
#: measures against is a round number the test can predict.
HALF_LON_MIN = 0.00095
HALF_LAT_MIN = -0.001445


def _fixture(tmp_path, ragged_tail=True, phase_s=0.0):
    """
    A car running `N_LAPS` past the gate, one sample every 1/HZ seconds.

    `phase_s` slides the car along its path so the true pass can be placed
    between two samples rather than on one.
    """
    n = int(LAP_S * N_LAPS * HZ) + 1
    t = np.arange(n) / HZ

    # Straight-line run north through the gate, looping every LAP_S seconds.
    # Position along the loop, in metres, zero exactly at the gate midpoint.
    along = (((t + phase_s) % LAP_S) - LAP_S / 2.0) * (SPEED_KPH / 3.6)
    lat_deg = GATE_LAT_MIN / 60.0 + along / M_PER_DEG_LAT
    lon_deg = -GATE_LON_MIN / 60.0                      # due north: longitude fixed

    start_utc = 10 * 3600 + 35 * 60 + 31.6              # 10:35:31.600
    utc = start_utc + t
    hh = np.floor(utc / 3600)
    mm = np.floor((utc - hh * 3600) / 60)
    ss = utc - hh * 3600 - mm * 60
    time_col = hh * 10000 + mm * 100 + ss

    lap_number = np.floor(t / LAP_S) + 1

    lines = [
        "File created on 18/09/2026 @ 11:35:31",
        "",
        "[header]",
        "satellites", "time", "latitude", "longitude", "velocity kmh",
        "lap_number", "engine_temp",
        "",
        "[channel units]",
        # only two units for seven channels: they align to the TAIL
        "(null)", "°C",
        "",
        "[comments]",
        "(c) Racelogic",
        "<Unit Info>",
        "Type   : VBVDHD2-V5 2cam",
        "Serial : 003871",
        "",
        "[laptiming]",
        f"Start        {GATE_LON_MIN - HALF_LON_MIN:.6f} "
        f"{GATE_LAT_MIN - HALF_LAT_MIN:.6f} "
        f"{GATE_LON_MIN + HALF_LON_MIN:.6f} "
        f"{GATE_LAT_MIN + HALF_LAT_MIN:.6f} ¬ Start / Finish",
        "",
        "[column names]",
        "sats time lat long velocity lap_number engine_temp",
        "",
        "[data]",
    ]
    for i in range(n):
        lines.append(
            f"012 {time_col[i]:013.3f} {lat_deg[i] * 60:+015.8f} "
            f"{-lon_deg * 60:+015.8f} {SPEED_KPH:07.3f} "
            f"{lap_number[i]:+.6E} {90.0:+.6E}"
        )
    if ragged_tail:
        lines.append("012 103551.000 +3000.0")        # logger lost power

    p = tmp_path / "fixture.vbo"
    p.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------- parsing


def test_units_align_to_the_tail_of_the_channel_list(tmp_path):
    """Seven channels, two units. Zipping from the front mislabels everything."""
    s = read_vbo(_fixture(tmp_path))
    assert len(s.channels) == 7
    assert s.unit("engine_temp") == "°C"
    assert s.unit("lap_number") == "(null)"
    # the leading GPS channels carry their unit in the name, so they get none
    assert s.unit("satellites") == ""
    assert s.unit("velocity kmh") == ""


def test_a_ragged_row_is_skipped_not_guessed_at(tmp_path):
    expected = int(LAP_S * N_LAPS * HZ) + 1
    assert read_vbo(_fixture(tmp_path, ragged_tail=True)).n_samples == expected
    assert read_vbo(_fixture(tmp_path, ragged_tail=False)).n_samples == expected


def test_header_metadata_is_read(tmp_path):
    s = read_vbo(_fixture(tmp_path))
    assert s.created.isoformat() == "2026-09-18"
    assert s.unit_info["Type"] == "VBVDHD2-V5 2cam"
    assert s.unit_info["Serial"] == "003871"


def test_missing_channel_names_itself_and_the_alternatives(tmp_path):
    s = read_vbo(_fixture(tmp_path))
    with pytest.raises(KeyError, match="brake_bar"):
        s["brake_bar"]


# ------------------------------------------------------------- conversions


def test_position_is_minutes_and_longitude_is_positive_west(tmp_path):
    """
    The raw columns are minutes; longitude counts west. Read naively, this
    fixture's car is six degrees west of the circuit.

    Checked at the gate, where the true position is known exactly.
    """
    s = read_vbo(_fixture(tmp_path))
    at_gate = int(LAP_S / 2.0 * HZ)
    assert s["longitude"][at_gate] < 0                 # raw is west-positive
    assert s["latitude"][at_gate] > 3000               # raw is minutes, not degrees
    assert s.longitude_deg[at_gate] == pytest.approx(6.0, abs=1e-3)  # east
    assert s.latitude_deg[at_gate] == pytest.approx(50.05, abs=1e-3)


def test_time_is_a_clock_reading_not_an_elapsed_time(tmp_path):
    s = read_vbo(_fixture(tmp_path))
    assert s["time"][0] == pytest.approx(103531.600)               # HHMMSS.sss
    assert s.utc_seconds[0] == pytest.approx(10 * 3600 + 35 * 60 + 31.6)
    assert s.elapsed_s[0] == 0.0
    assert s.elapsed_s[-1] == pytest.approx(LAP_S * N_LAPS, abs=1e-6)


def test_sample_rate_is_measured_from_the_clock(tmp_path):
    assert read_vbo(_fixture(tmp_path)).sample_hz == pytest.approx(HZ, rel=1e-6)


# ------------------------------------------------------------------- laps


def test_the_gate_is_found_once_per_lap(tmp_path):
    """
    The line is written 5.8 m long and lying along the track, exactly as the
    real file writes it. Closest approach has to find all three passes anyway.
    """
    marks = read_vbo(_fixture(tmp_path)).crossings(min_gap_s=GAP_S)
    assert len(marks) == N_LAPS
    for i, m in enumerate(marks):
        assert m == pytest.approx(LAP_S / 2.0 + i * LAP_S, abs=0.02)


def test_crossing_time_beats_the_sample_period(tmp_path):
    """
    Put the true pass exactly half a sample away from any sample. Snapping to
    the nearest one would be 0.05 s out; the interpolation has to do better.
    """
    half = 0.5 / HZ
    first = read_vbo(_fixture(tmp_path, phase_s=half)).crossings(min_gap_s=GAP_S)[0]
    assert first == pytest.approx(LAP_S / 2.0 - half, abs=0.005)
    # and it is genuinely between samples, not snapped to one
    assert min(abs(first - k / HZ) for k in range(int(LAP_S * HZ))) > 0.04


def test_timed_laps_are_gate_to_gate(tmp_path):
    laps = read_vbo(_fixture(tmp_path)).timed_laps(min_gap_s=GAP_S)
    assert len(laps) == N_LAPS - 1
    for lap in laps:
        assert lap.duration_s == pytest.approx(LAP_S, abs=0.02)


def test_lap_number_slicing_covers_every_sample(tmp_path):
    s = read_vbo(_fixture(tmp_path))
    laps = s.laps()
    assert [lp.number for lp in laps] == [1, 2, 3, 4]      # 4th is the final instant
    assert sum(lp.n_samples for lp in laps) == s.n_samples


def test_slice_returns_only_that_lap(tmp_path):
    s = read_vbo(_fixture(tmp_path))
    lap = s.timed_laps(min_gap_s=GAP_S)[0]
    cut = s.slice(lap)
    assert len(cut["velocity kmh"]) == lap.n_samples
    assert np.allclose(cut["velocity kmh"], SPEED_KPH)


# ------------------------------------------------------------------ errors


def test_a_file_without_a_header_is_rejected(tmp_path):
    p = tmp_path / "not.vbo"
    p.write_text("just some text\r\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no \\[header\\]"):
        read_vbo(p)


def test_more_units_than_channels_is_rejected(tmp_path):
    p = tmp_path / "bad.vbo"
    p.write_text("\r\n".join([
        "[header]", "time", "",
        "[channel units]", "s", "°C", "",
        "[data]", "1.0",
    ]) + "\r\n", encoding="utf-8")
    with pytest.raises(ValueError, match="units for"):
        read_vbo(p)

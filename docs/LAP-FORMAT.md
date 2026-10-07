# Lap format (v0, draft)

This is the interface between the groups. **Group 1 delivers** files in this layout
(their task 7 turns the simulator recordings into it). **Group 2 owns the contract**
and the validator (task 6): `python -m claimcheck.validate file.vbo`. A recorder is
done when its files pass the validator and the checker reads them.
**It is a draft: task 6 agrees changes with Group 1, by 13 November.**

## File layout

Plain ASCII, CRLF line endings, `[section]` headers: the Racelogic VBOX `.vbo`
layout. `claimcheck.synth` writes it, `claimcheck.ingest.vbo` reads it. Sections:
`[header]` (channel names), `[channel units]`, `[comments]`, `[laptiming]` (the
start/finish line), `[column names]`, `[data]`.

Quirks the reader handles (and the generator reproduces):

- the unit list is shorter than the channel list and aligns with its **tail**
- latitude and longitude are in **minutes**, longitude **positive west**
- `time` is a clock reading packed as `HHMMSS.sss`, not elapsed seconds
- `lap_number` can lag the real crossing of the line
- the start/finish line is a point, not an orientation

## Channels

| channel | unit | needed by the checker |
|---|---|---|
| `time` | HHMMSS.sss | yes |
| `latitude`, `longitude` | minutes (longitude positive west) | yes |
| `velocity kmh` | km/h | yes |
| `throttle_pct` | % | yes |
| `brake_bar` | bar | yes |
| `steering_deg` | degrees at the steering wheel | yes (understeer) |
| `accel_lat_g` | G | yes |
| `accel_long_ms2` | m/s² | no |
| `lap_number` | counter | no (laps are timed on the line) |
| `pit_limiter`, `full_course_yellow` | 0 / 1 | no; a lap with either set is not valid |
| `heading`, `height`, `vertical velocity m/s`, `satellites`, `sampleperiod`, `solution type` | | no |

A missing needed channel does not crash the check: the answer becomes "Can't tell
yet" and says which channel is missing.

## To agree between the groups (task 6, with Group 1's tasks 5 and 7)

- the channels the simulator can really supply, and their units
- **timestamps**: keep the source time and the receive time; time must be
  monotonic; state the sampling rate. Honest timestamps matter more than clean ones.
- file, or a ROS 2 topic: the message definition
- which car constants (wheelbase, steering ratio) the simulator uses

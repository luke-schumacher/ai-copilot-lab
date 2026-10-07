# How the claim check works

```
sentence --> claim --> laps --> one distance axis --> corners --> per-lap metrics --> stamp
 (typed)   (parser or   (timed     (every lap on       (found from   (brake point,      (statistics,
            translator)  on the     the same metre      lateral        min speed, ...)    not opinion)
                         line)      axis, 2 m grid)     acceleration)
```

1. **Claim.** `check/claim.py` turns the sentence into a structured test: who, which
   corner, loses or gains time, and which cause (`brake_early`, `late_throttle`,
   `coasting`, ...). A rule parser does it by default; an optional language-model
   translator does the same job. Neither decides the answer.
2. **Laps.** `ingest/vbo.py` reads the file; `check/session.py` cuts it into laps
   timed on the start/finish line. A lap is *valid* if it is within 104 % of that
   driver's best and the pit limiter and yellow flag were off. A driver needs at
   least 3 valid laps, otherwise the answer is "Can't tell yet".
3. **Distance axis and corners.** `check/track.py` puts every lap on one distance axis
   (2 m grid) and finds corners from smoothed lateral acceleration.
4. **Metrics.** `check/measure.py` measures, per lap and corner: corner time, brake
   point, peak brake pressure, minimum speed, throttle pick-up, full-throttle point,
   coasting, understeer angle.
5. **The decision.** `check/stats.py` compares the driver's laps with the reference
   laps (Welch t interval, 90 % two-sided) and the tolerance for that metric
   (`check/thresholds.py`, `TOL`):

   | stamp | when |
   |---|---|
   | Supported | the whole interval is above 0 and the difference is at least the tolerance |
   | Contradicted | the whole interval is below the tolerance |
   | Can't tell yet | otherwise |

6. **Log.** Every check, and the engineer's agree or disagree, is appended to
   `claimcheck-checks.jsonl`.

## Why the thresholds matter

Every number that decides a stamp is in `check/thresholds.py`, hand-set, versioned
and logged with each check. They are a first guess. Calibrating them against known
answers is what Group 2 does (see `docs/TASKS.md`).

## The generator

`claimcheck/synth.py` lays out a made-up circuit with six corners and solves speed
with a friction-limited forward-backward solver. It is not a vehicle model; it only
needs to produce traces with the shape of real ones. Mistakes are planted through
a `Style`: `brake_early_m`, `late_throttle_m`, `slow_kph`, `understeer_deg` per
corner, plus noise. It writes real `.vbo` layout, including the quirks the reader
must handle (see `docs/LAP-FORMAT.md`).

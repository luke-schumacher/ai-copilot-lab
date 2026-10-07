"""
Every number that decides a stamp, in one place.

These are hand-set. That is a known weakness and a deliberate one: calibrating
them against outcomes is the point of the project, and it can only be done if
they are named, versioned and logged with every check. Change a value here, bump `VERSION`.
"""

VERSION = "lab-0.1"

# ---- which laps count -------------------------------------------------
#: A lap counts if it is within this factor of the same driver's best.
VALID_LAP_FACTOR = 1.04
#: Fewer valid laps than this for the claimed driver -> "Can't tell yet".
MIN_LAPS = 3
#: Robust outlier rule inside one corner: |x - median| > K * 1.4826 * MAD.
OUTLIER_K = 3.5
#: The outlier rule needs at least this many laps to mean anything.
OUTLIER_MIN_LAPS = 4

# ---- the statistical decision -----------------------------------------
#: Two-sided interval used for every comparison. 90 % two-sided is a 95 %
#: one-sided bound in the claimed direction.
INTERVAL = 0.90

# ---- corner detection on the reference lap ----------------------------
GRID_M = 2.0               # resampling step along the lap
AY_SMOOTH_M = 20.0         # lateral-g smoothing window
AY_CORNER_G = 0.6          # a corner is where |ay| stays above this
AY_PEAK_G = 0.9            # ... and peaks at least here
CORNER_MIN_LEN_M = 25.0
CORNER_MERGE_GAP_M = 30.0  # same-direction parts closer than this merge

# ---- the window each corner is measured over --------------------------
BRAKE_ON_BAR = 10.0        # brake point = first crossing of this
BRAKE_SEARCH_M = 300.0     # look this far before the apex for the brake point
ENTRY_MARGIN_M = 60.0      # window opens this far before the reference brake point
EXIT_MARGIN_M = 100.0      # ... and closes this far after full throttle
MID_SPEED_FACTOR = 1.05    # "mid" = where reference speed is within 5 % of its minimum

# ---- pedal thresholds -------------------------------------------------
THROTTLE_ON_PCT = 20.0     # throttle pick-up
THROTTLE_FULL_PCT = 95.0   # full throttle
PEDAL_OFF_PCT = 2.0        # throttle below this counts as off
BRAKE_OFF_BAR = 3.0        # brake pressure below this counts as off
UNDERSTEER_MIN_STEER_DEG = 10.0  # understeer is only measured above this steering angle

# ---- how big a difference has to be to matter -------------------------
TOL = {
    "corner_time_s": 0.05,
    "brake_point_m": 5.0,
    "peak_brake_bar": 5.0,
    "v_min_kph": 2.0,
    "throttle_on_m": 5.0,
    "full_throttle_m": 5.0,
    "coasting_s": 0.10,
    "full_throttle_share": 0.05,
    "understeer_deg": 0.3,
}

# ---- "because": is the time lost where the cause would lose it? ------
SHARE_SUPPORTS = 0.50      # cause's phase holds at least this much of the loss
SHARE_CONTRADICTS = 0.25   # ... or less than this

#: Where in the corner each cause costs time.
CAUSE_PHASES = {
    "brake_early": ("entry",),
    "brake_late": ("mid", "exit"),
    "brake_soft": ("entry",),
    "low_min_speed": ("mid", "exit"),
    "late_throttle": ("exit",),
    "late_full_throttle": ("exit",),
    "coasting": ("entry", "mid"),
    "lifts": (),            # whole corner, no localisation
    "understeer": ("mid", "exit"),
}

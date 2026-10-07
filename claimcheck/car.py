"""
Generic car constants.

Round numbers chosen for the synthetic generator and the understeer metric.
They describe no real car. A real car would have its own; the simulator
sessions will bring theirs through the interface (see docs/LAP-FORMAT.md).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Car:
    wheelbase_m: float
    steering_ratio: float      # steering-wheel angle / road-wheel angle


GENERIC = Car(wheelbase_m=2.50, steering_ratio=15.0)

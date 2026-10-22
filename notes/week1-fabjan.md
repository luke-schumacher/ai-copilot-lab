# Week 1: Fabjan (Group 2, Claims squad)

START-HERE step 7: BB's `brake_early_m` at T2 lowered from 15 m to 5 m (seed 23, claim "BB loses time in T2 because he brakes early").

- 15, 10 and 7 m: Supported. 6 and 5 m: Can't tell yet. So it flips between 7 and 6 m.
- The measured shift is always smaller than planted (15 m gave 12.5, 7 m gave 5.1, 6 m gave 4.2), so a real 5 or 6 m mistake lands under the 5 m tolerance (`stats.py`: low > 0 and diff >= tol).
- The time loss in T2 was Supported every time, only the cause was unclear. Question for task 5: is 5 m the right tolerance, and why is the measured shift smaller than planted?

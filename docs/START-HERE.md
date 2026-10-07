# Start here: Group 2, first week

Goal of the week: everyone has run the tool, understood one answer end to end, and
proposed scenarios for the benchmark. No task needs hardware.

## Wednesday 7 October (kickoff day)

1. Read [DATA-RULE.md](DATA-RULE.md). Everyone agrees to it in the room.
2. Choose roles and squads (below) and a weekly meeting slot.
3. One person forks the repository and adds the group; everyone clones the fork and sets it up
   (README, "Set up"). `uv run pytest` must pass.
4. `uv run claimcheck demo`. Type: *BB loses time in T2 because he brakes early*.
   Then: *BB brakes late in T2*. Read both answers completely.

## Squads

Each Master leads a squad of three. The squads share tasks; each task has a named
lead (see TASKS.md).

| squad | members | focus |
|---|---|---|
| A: Benchmark | M1 (lead), B1, B2 | scenarios, harness, metrics, calibration, noise and lap-count sweeps |
| B: Realism and transfer | M2 (lead), B3, B4 | generator realism, fidelity metric, interface contract and validator, sampling-rate and GPS sweeps, timing faults |

T8 (interface contract and validator) belongs to squad B. T10 (transfer) needs both squads.

## Thursday to Friday

5. Run the starter benchmark and look at its output:
   `uv run python -m claimcheck.bench.starter 10`
   One scenario is not always answered "right". Find out why (it is a real finding).
6. Read `tests/test_claim_check.py` and `docs/HOW-IT-WORKS.md`.
7. Open `claimcheck/synth.py`, find `Style`. Change BB's `brake_early_m` at T2 from
   15 m to 5 m and re-run. At what size does *Supported* turn into *Can't tell yet*?
   Write what you found in five lines in `notes/week1-<your name>.md` and open a
   pull request. This is your first merged pull request.

## By the first weekly meeting

8. Each person adds three scenario ideas for T1 as a comment on the "T1 scenarios"
   issue (what mistake, which corner, which claim, what the right answer is).
9. Squad B: list the three realism effects (tyre wear, traffic, driver variability)
   and what each should do to a lap, in plain words. Do not code yet.
10. Squad B: read [LAP-FORMAT.md](LAP-FORMAT.md) and write down five questions for
    Group 1 about what their simulator can really supply.

## How the weeks run

Read [WORKFLOW.md](WORKFLOW.md) today: set up your group's fork, a team meeting among yourselves
every week, a pull request to me every Friday, a call with me every second week.

## If you are stuck

Ask in the group channel before spending more than 30 minutes. Ask Luke for anything
about data. Never try to find or request real team data to "make it more realistic".

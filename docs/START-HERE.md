# Start here: Group 2, first week

Goal of the week: everyone has run the tool, understood one answer end to end, and
proposed scenarios for the benchmark. No task needs hardware.

## Wednesday 7 October (kickoff day)

1. Read [DATA-RULE.md](DATA-RULE.md). Everyone agrees to it in the room.
2. Choose the squads (below) and a weekly meeting slot.
3. One person forks the repository and adds the group; everyone clones the fork and sets it up
   (README, "Set up"). `uv run pytest` must pass.
4. `uv run claimcheck demo`. Type: *BB loses time in T2 because he brakes early*.
   Then: *BB brakes late in T2*. Read both answers completely.

## Squads

Two squads of two. Each squad names a lead, who chairs the weekly meeting and makes sure the weekly note is written.
The hours per person are in TASKS.md.

| squad | members | focus |
|---|---|---|
| 1: Benchmark | Master 1 (lead), Master 2 | scenarios, test runner and measures, threshold calibration, noise and lap-count tests |
| 2: Claims and interface | Master 3 (lead), Master 4 | interface and validator, claim reading, sampling-rate, GPS and timing tests, fidelity and transfer |

Task 4 (break the data) and task 8 (fidelity and transfer) need both squads.

## Thursday to Friday

5. Run the starter benchmark and look at its output:
   `uv run python -m claimcheck.bench.starter 10`
   One scenario is not always answered "right". Find out why (it is a real finding).
6. Read `tests/test_claim_check.py` and `docs/HOW-IT-WORKS.md`.
7. Open `claimcheck/synth.py`, find `Style`. Change BB's `brake_early_m` at T2 from
   15 m to 5 m and re-run. At what size does *Supported* turn into *Can't tell yet*?
   Write what you found in five lines in `notes/week1-<your name>.md` and open a
   merge request. This is your first merged merge request.

## By the first weekly meeting

8. Each person adds three scenario ideas for task 2 as a comment on the "Scenarios"
   issue (what mistake, which corner, which claim, what the right answer is).
9. Squad 2: list the three realism effects (tyre wear, traffic, driver variability)
   and what each should do to a lap, in plain words. Do not code yet; task 8 uses them.
10. Squad 2: read [LAP-FORMAT.md](LAP-FORMAT.md) and write down five questions for
    Group 1 about what their simulator can really supply.

## How the weeks run

Read [WORKFLOW.md](WORKFLOW.md) today: set up your group's fork, a team meeting among yourselves
every week, a merge request to me every Friday, a call with me every second week.

## If you are stuck

Ask in the project chat before spending more than 30 minutes. Ask Luke for anything
about data. Never try to find or request real team data to "make it more realistic".

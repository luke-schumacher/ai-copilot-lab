# AI Copilot for Racesimulation: the claim checker lab (Group 2)

This is the repository for **Group 2** of the student project, winter semester 2026/27, FH Aachen.
It runs on a normal laptop, needs no network and contains no real racing data.

If you read only one thing: **Group 2 finds out how often the claim checker is right, and what makes it
wrong.** Everything below explains how.

## 1. The project in plain words

A race engineer has a belief about a driver, for example "AA loses time in corner 2 because he brakes
early". The **claim checker** tests that belief against the lap data and answers one of three ways:

- **Supported**: the numbers back the claim.
- **Contradicted**: the numbers say otherwise.
- **Can't tell yet**: there is not enough evidence. This is an honest answer, not a failure.

An AI model may read the sentence, but **statistics decide the answer**. The checker is written and works.
What nobody knows yet is **how often it is right**, and where it starts to fail when the data gets worse.
That is your job. To do it you need data where the right answer is known, so this repository contains a
**generator** that writes fake logger files with mistakes planted on purpose.

Group 1 works in a second repository (`ai-copilot-sim`). They turn a racing-simulator rig into a second
source of data. At the end you test whether what you found on fake data also holds on their simulator data.
The two groups meet at the **lap-file format** (`docs/LAP-FORMAT.md`).

## 2. Terms used in this repository

- **Telemetry:** measurements recorded while driving: speed, throttle, brake pressure, steering angle, position.
- **Lap file / `.vbo`:** a text file of telemetry in the layout of a GPS data logger. The generator writes
  these, and the checker reads them.
- **Claim:** the sentence an engineer types.
- **Tolerance:** the smallest difference that matters. A brake point 1 m earlier does not matter; 5 m does.
- **90 % interval:** the range in which the true difference lies with 90 % confidence. If the whole range is
  above zero and the difference is at least the tolerance, the claim is Supported.
- **Synthetic data:** fake sessions made by code.
- **Scenario:** one planted mistake, the claim to test, and the right answer. "AA is fine, BB brakes 15 m early
  in corner 2; claim: BB brakes early in corner 2; right answer: Supported."
- **Ground truth:** the known right answer in a scenario.
- **Seed:** a number that fixes the random choices of the generator, so a run can be repeated exactly.
- **Confusion matrix:** a table of the right answer against the checker's answer. It shows how often each
  kind of mistake happens.
- **Calibration:** tuning the checker's thresholds against known outcomes. **Held-out set:** scenarios kept
  aside and not used for tuning, so that you can test honestly.
- **Fidelity:** how closely a test environment behaves like the real thing, expressed as a number.
- **Transfer:** whether a result found on fake data still holds on simulator data.
- **Interface (German: Schnittstelle):** the place where one part hands data to the next. The lap-file layout is the interface between the two groups.
- **Validator:** a program that checks whether a lap file follows the agreed layout.
- **Fork, branch, pull request:** your own copy of a repository on GitHub; a line of work inside it; a
  request to merge that work back. See `docs/WORKFLOW.md`.

## 3. Set up (once, needs internet)

You need **git** and **Python 3.10 or newer**. This README uses **uv**, a fast tool that creates the Python
environment and installs the packages; plain `python -m venv` and `pip` work too.

1. One person per group **forks** this repository on GitHub (the Fork button) and adds the other group
   members as collaborators on the fork (Settings, Collaborators). The repository is public, so nobody needs
   an invitation from Luke.
2. Everyone clones the fork and opens a terminal in the folder:

```bash
uv venv
uv pip install -e ".[dev]"      # without uv: python -m venv .venv, activate it, then pip install -e ".[dev]"
uv run pytest                    # every test should pass
```

If `pytest` ends with "passed", you are set up. A few tests are skipped on purpose.

## 4. Try it

**The page.** `uv run claimcheck demo` writes two fake sessions (drivers AA and BB) and opens a local page.
BB has two planted mistakes: **brakes 15 m early in corner 2** and **is 15 m late on the throttle in
corner 5**. Type these claims and read each answer completely:

- `BB loses time in T2 because he brakes early`: Supported.
- `BB brakes late in T2`: Contradicted.
- `BB loses time in T1`: BB did nothing wrong in corner 1, so the right answer is Contradicted.

("T2" means turn 2, the second corner of the made-up circuit.)

**The terminal.** The same check without the page:

```bash
uv run python -m claimcheck.synth out            # writes out/AA.vbo and out/BB.vbo
uv run claimcheck check out --driver AA --driver BB --no-claude -c "BB loses time in T2 because he brakes early"
uv run claimcheck laps out --driver AA --driver BB     # every lap and whether it counts
uv run claimcheck corners out --driver AA --driver BB  # the corners the tool found
```

**The starter benchmark.** `uv run python -m claimcheck.bench.starter 10` runs three scenarios over 10
random seeds and prints how often the checker was right, wrong, or said "can't tell". One scenario is not
answered "right" every time. Finding out why is your first real result.

**The validator.** `uv run python -m claimcheck.validate out/AA.vbo` checks a lap file against the layout.
It is a skeleton: task 7 completes it.

**Tests for the interface and the reporting.** The code is already here: `tests/test_validate.py` tests the lap-file
interface, `tests/test_web.py` and `claimcheck/check/log.py` cover the reporting (the page and the log). Run them
with `uv run pytest tests/test_validate.py tests/test_web.py`, read them, and extend them in task 7. Group 1 builds a
dashboard that pulls data through this interface and evaluates it with the checker; it is what they present at the end.

## 5. How the code is organised

```
claimcheck/
  synth.py            the generator: fake sessions with planted mistakes (task 6 extends it)
  ingest/vbo.py       reads a lap file (.vbo) into Python
  check/
    session.py        cuts a file into laps and names the drivers
    track.py          finds the corners and puts every lap on one distance axis
    measure.py        per lap and corner: brake point, minimum speed, throttle pick-up, coasting ...
    stats.py          the decision: Supported, Contradicted or Can't tell yet
    thresholds.py     every number that decides an answer, in one place (task 5 tunes them)
    claim.py          reads a sentence with simple rules, English and German
    translate.py      the optional AI-model reader (task 8 compares it with the rules)
    verdict.py        puts the answer and the numbers behind it into words
    log.py            appends every check to a log file
  web/                the local page
  bench/starter.py    the starter benchmark (tasks 2 and 3 start here)
  validate.py         the lap-file validator skeleton (task 7 starts here)
  car.py              generic car constants
tests/                known-answer tests: read them first, they show what "correct" means
docs/                 how it works, the lap format, tasks, workflow, data rule
notes/                the weekly note template
```

## 6. What happens when you type a claim

1. The sentence is turned into a structured test: who, which corner, loses or gains time, which cause.
2. The files are cut into laps, timed on the start/finish line. A lap counts if it is within 4 % of that
   driver's best and the pit limiter and yellow flag were off.
3. Every lap is put on one distance axis, and the corners are found from sideways acceleration.
4. For every lap and corner the numbers are measured: brake point, minimum speed, throttle pick-up and so on.
5. The driver's laps are compared with the reference laps. The difference, with a 90 % interval, is held
   against the tolerance in `thresholds.py`. That gives one of the three answers.
6. The check, the numbers and the engineer's agree or disagree are appended to a log file.

`docs/HOW-IT-WORKS.md` has the same in more detail.

## 7. Your tasks

The full list, with hours, squads and what each task needs, is in **`docs/TASKS.md`**. In one line each:

1. Onboarding: run everything above.
2. Scenario catalogue: the answer key, with driving cards for Group 1.
3. Test runner and measures: run all scenarios over many seeds and count the answers.
4. Break the data: noise, fewer laps, lower rate, GPS error, timing faults; see where it fails.
5. Calibrate the thresholds: tune on one set of scenarios, test on another.
6. More realistic fake data: tyre wear, traffic, driver variability.
7. Interface and validator: agree the lap file format with Group 1, check their files, and test the interface and the reporting.
8. Claim reading: compare the rule parser with AI models on 100 claims.
9. Fidelity and transfer: compare fake and simulator sessions; rerun the benchmark on both.
10. Meetings, report and final talk.

Start here: **`docs/START-HERE.md`** (your first week).

## 8. How we work

- Your group works in its **fork**: one branch per task (`calibrate-thresholds`), a teammate reviews,
  tests are green, then merge into the fork's `main`.
- You meet **at least once a week** without Luke, open **one pull request to Luke every Friday**, and have
  an **online call every second week**. Details: `docs/WORKFLOW.md`.
- **Done** means: merged by a reviewed pull request, tests pass, one command reproduces the result, a README
  or docstring says how to run it, and the task's "done when" is met with the numbers in the repository.

## 9. The data rule

Work only with data you create yourselves. Read `docs/DATA-RULE.md` before you do anything else.

## 10. Optional: the AI-model reader

The checker can use an AI model to read the sentence. It is optional; the rule parser works without it.
Put `ANTHROPIC_API_KEY=...` in a `.env` file (it is git-ignored) and run `uv pip install -e ".[llm]"`.
You do not need it for any task except task 8, where the local models from Group 1 are the main candidates.

## 11. If something goes wrong

- **`pytest` fails straight after a fresh clone:** check that the Python version is 3.10 or newer and that you
  ran the install command inside the activated environment (`uv run` does this for you).
- **The page does not open:** open `http://127.0.0.1:8765/` yourself.
- **A command says "no valid lap":** the files have too few clean laps; the generator writes six by default.
- **You are not sure whether something is allowed:** ask before you open it.

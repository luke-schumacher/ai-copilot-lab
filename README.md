# AI Copilot for Racesimulation: claim checker lab

Code for the student project, WS 2026/27, FH Aachen. This is the code **Group 2**
works on. It runs on your laptop, needs no network, and contains no data from any
real car or team.

An engineer types a belief:

> **AA loses time in T2 because he brakes early**

and the tool answers **Supported**, **Contradicted** or **Can't tell yet**, with
the laps and the numbers behind it. A language model may read the sentence; the
answer itself is statistics on lap telemetry.

## Set up (needs internet, once)

One person per group forks this repository (public, no invitation needed) and adds the
group as collaborators; everyone clones the fork. See [docs/WORKFLOW.md](docs/WORKFLOW.md).

```bash
uv venv && uv pip install -e ".[dev]"      # or: python -m venv .venv && pip install -e ".[dev]"
uv run pytest                               # all tests should pass
uv run claimcheck demo                      # opens the page on synthetic sessions
```

Two synthetic drivers, AA and BB. BB has two planted mistakes, so the right answers
are known: **brakes 15 m early at T2** and **15 m late on the throttle at T5**.
Try the claim above, then a wrong one ("BB brakes early in T1").

## What is in here

| package | what |
|---|---|
| `claimcheck.synth` | synthetic `.vbo` sessions with mistakes planted where we choose |
| `claimcheck.ingest` | reads VBOX `.vbo` logger files |
| `claimcheck.check` | the claim check: laps, distance axis, corners, per-lap metrics, three stamps |
| `claimcheck.web` | the local page |
| `claimcheck.car` | generic car constants |
| `claimcheck.bench.starter` | a minimal known-answer benchmark: where T1 and T2 start |
| `claimcheck.validate` | a skeleton lap-file validator: where T8 starts |
| `tests/` | known-answer tests; read them first |

**Start here: [docs/START-HERE.md](docs/START-HERE.md)** (your first week). Then
[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) and [docs/TASKS.md](docs/TASKS.md). The
file layout Group 1's simulator delivers is in [docs/LAP-FORMAT.md](docs/LAP-FORMAT.md).

Group 1 works in a second repository, `ai-copilot-sim`. The two groups meet at the
lap format.

## The data rule

Work only with data you create yourselves. Read [docs/DATA-RULE.md](docs/DATA-RULE.md)
before you do anything else.

## How we work

- `main` here is protected and changes only through your weekly pull request to Luke. Day to
  day you work in your group's fork: one branch per task (`t5-calibration`), a teammate reviews,
  tests are green.
- **Done** means: merged by a reviewed pull request; tests pass and one command
  reproduces the result; the README or a docstring says how to run it; the
  "done when" of the task is met, with the numbers in the repository.
- Rhythm: you meet at least once a week without me, open one pull request to me every
  Friday, and we have an online call every second week. Details: [docs/WORKFLOW.md](docs/WORKFLOW.md).

## Optional: the language-model translator

Put `ANTHROPIC_API_KEY=...` in a `.env` file here (it is git-ignored) and install
the extra: `uv pip install -e ".[llm]"`. Without it the rule parser reads the
sentence, in English and German. You do not need it for any task.

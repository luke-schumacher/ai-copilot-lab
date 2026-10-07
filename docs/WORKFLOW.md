# How we work

Three rhythms. You run the first two yourselves; I (Luke) join the third.

## Set up once per group: your fork

This repository is public and **nobody needs an invitation**. One person per group:

1. Forks this repository on GitHub.
2. Adds the rest of the group as collaborators on the fork (Settings, Collaborators).

Everyone clones the **fork**. Your day-to-day work happens there, without me.

## 1. Team meeting: at least once a week, students only

- 45 minutes, a fixed slot, the Masters chair it. No one from the project team attends.
- Agenda: **done, next, blocked**. Decide who does what this week, and write five lines
  into `notes/week-NN.md` (copy `notes/WEEK-TEMPLATE.md`).
- Decisions inside your tasks are yours. Do not wait for me to approve them.

## 2. Day to day: pull requests inside your fork

- One branch per task, named `t5-calibration` or `s5-ros2-bridge`.
- A teammate reviews, tests must be green, then you merge into your fork's `main`.

## 3. Every Friday: the weekly pull request to Luke

- **By 18:00** one person opens a pull request from your fork's `main` into this repository's
  `main`, titled `Week NN: <group>`. First press "Sync fork" so it applies cleanly.
- It contains that week's note and the work done. I review it by **Monday evening**: comments in
  the pull request, an approval when the note is complete. My feedback is about direction and
  results, not style.
- This repository's `main` is protected: it changes only through these pull requests.
- Rotate who opens it.

## 4. Direction call: every second week, online, 30 to 45 minutes per group

- The first call is in the week of 19 October. The time is agreed in the room.
- You bring: what you did, what you found, and one to three decisions you need from me.
- I bring: direction, and answers about hardware and licences.

## When you are stuck

- Blocked for more than **two working days**? Message me. Do not wait for the next call.
- Unsure whether something counts under the data rule? Ask first, open later.

## What I will not do

Tell you each week what to work on. The plan is in `docs/TASKS.md`. If it is unclear or wrong,
change it in a pull request and say why.

## Done means

Merged by a reviewed pull request; tests pass and one command reproduces the result; the
README or a docstring says how to run it; the task's "done when" is met, with the numbers in
the repository.

# How we work

Three rhythms. You run the first two yourselves; I (Luke) join the third.

## Where the repositories are

Both repositories are on the FH Aachen GitLab, https://git.fh-aachen.de. Sign in with your FH account.
I give every student read access (role Reporter) to both repositories. If you do not see them, click
**Request access** on the project page and I approve it. Reporter is enough to read and to fork; your work
reaches the original only through merge requests from your fork.

- Group 1 (simulator rig): https://git.fh-aachen.de/ls9392e/ai-copilot-sim
- Group 2 (claim checker): https://git.fh-aachen.de/ls9392e/ai-copilot-lab

## Set up once per group: your fork

One person per group:

1. Opens this repository on GitLab and clicks **Fork** (keep the name, choose your own namespace).
2. Invites the rest of the group to the fork: **Manage, Members, Invite members**, role **Developer**.

Everyone clones the **fork**. Your day-to-day work happens there, without me.

## 1. Team meeting: at least once a week, students only

- 45 minutes, a fixed slot, the squad lead chairs it. No one from the project team attends.
- Agenda: **done, next, blocked**. Decide who does what this week, and write five lines
  into `notes/week-NN.md` (copy `notes/WEEK-TEMPLATE.md`).
- Decisions inside your tasks are yours. Do not wait for me to approve them.

## 2. Day to day: merge requests inside your fork

A **merge request** is GitLab's name for a pull request: you ask to merge one branch into another.

- One branch per task, named `calibrate-thresholds` or `ros2-bridge`.
- A teammate reviews the merge request, the tests must be green, then you merge into your fork's `main`.

## 3. Every Friday: the weekly merge request to Luke

- **By 18:00** one person opens a merge request from your fork's `main` into this repository's
  `main` (the target project is the original, not your fork), titled `Week NN: <group>`. If GitLab
  offers **Update fork** on your fork, click it first so the request applies cleanly.
- It contains that week's note and the work done. I review it by **Monday evening**: comments in
  the merge request, an approval when the note is complete. My feedback is about direction and
  results, not style.
- This repository's `main` is protected: it changes only through these merge requests.
- Rotate who opens it. The first one is due **Friday 16 October**.

## 4. Direction call: every second week, online, 30 to 45 minutes per group

- The first call is **Thursday 22 October**; the invitation follows.
- You bring: what you did, what you found, and one to three decisions you need from me.
- I bring: direction, and answers about hardware and licences.

## Where we talk

One project chat for everyone, with a channel for each group. I send the link after the kickoff.
Use it for questions and quick coordination. Decisions and results go into the weekly note, not only the chat.

## When you are stuck

- Blocked for more than **two working days**? Message me. Do not wait for the next call.
- Unsure whether something counts under the data rule? Ask first, open later.

## What I will not do

Tell you each week what to work on. The plan is in `docs/TASKS.md`. If it is unclear or wrong,
change it in a merge request and say why.

## Done means

Merged by a reviewed merge request; tests pass and one command reproduces the result; the
README or a docstring says how to run it; the task's "done when" is met, with the numbers in
the repository.

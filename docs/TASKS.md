# Group 2 tasks

Hours are for the whole group. Level: Bachelor = for Bachelor students, Master = led by a Master student, Shared = Bachelors and Masters together.
Every student: 10 hours onboarding, 75 hours on the tasks below, 35 hours meetings, report and talk: 120 hours.
Start in week 1: tasks 1, 2, 6 and 7.
Group 1's tasks are in the `ai-copilot-sim` repository.

| # | task | what you do | in → out | done when | hours | level | depends on |
|---|---|---|---|---|---|---|---|
| 1 | **Onboarding** | Set up the repository, run the demo and the tests, and read how the checker reaches its answers. | In: repository. Out: everyone runs the demo. | Everyone has run the demo and the tests and passes a short quiz on the data rule. | 60 (6×10) | Shared | none |
| 2 | **Scenario catalogue** | List the mistakes we plant and the right answer for each, for example 'driver brakes 15 m early in corner 2: Supported'. Include cases with no mistake at all. Write a one-line driving card for each, so Group 1 can drive it in the simulator. | In: the generator. Out: scenario file, answer key, one driving card per scenario. | At least 24 scenarios, each with a known answer and a driving card. A fixed seed regenerates identical files. | 30 | Shared | task 1 |
| 3 | **Test runner and measures** | Run the checker over all scenarios and many random seeds automatically. Count how often it is right, wrong or says 'can't tell yet', with intervals showing how sure each count is. Make the whole run repeatable with one command. | In: scenarios. Out: results table and a measures module. | One command reproduces the results table exactly. Tests check the measures against hand calculations. | 70 | Shared | task 2 (start from the starter benchmark) |
| 4 | **Break the data** | Make the data worse in controlled steps: more noise, fewer laps, a lower sampling rate, GPS error, and timing faults (delayed, dropped or duplicated samples). For each, plot how the share of right answers falls. | In: clean files, Group 1's delay ranges. Out: curves of right-answer rate against fault level. | Each fault is tested at 6 or more levels with 30 or more random seeds. The curves, with intervals, are saved in the repository. | 80 | Bachelor | task 3; Group 1's task 8 for delay ranges |
| 5 | **Calibrate the thresholds** | The checker's tolerances are hand-set guesses. Tune them on one set of scenarios and test them on another, to cut wrong answers while keeping 'can't tell yet' at an acceptable rate. | In: results of tasks 3 and 4. Out: new thresholds and a short write-up. | The new thresholds beat the old ones on unseen scenarios by a criterion written down before the run. | 60 | Master | tasks 3 and 4 |
| 6 | **More realistic fake data** | Extend the generator with tyre wear, traffic and driver variability as switchable levels, so the fake data behaves more like real driving. Document what each level does to the checker's answers. | In: the generator. Out: switchable effects. | Each effect is off by default, tested, and its effect on the checker is documented. | 55 | Shared | task 1 |
| 7 | **Interface and validator** | Agree with Group 1 exactly what a lap file must contain, and write the program that checks a file against that. Group 1's recorder counts as finished only when its files pass this check. | In: draft lap format, Group 1's channel list. Out: agreed format and a validator. | Format agreed with Group 1 by 13 November. The validator rejects missing channels, time running backwards and missing timestamps, and Group 1's files pass. | 40 | Shared | task 1 (start from the validator skeleton) |
| 8 | **Claim reading: rules versus AI models** | Before the checker can test a claim, the sentence has to be turned into a structured test. Compare the built-in rule parser with AI models on 100 realistic claims in English and German: the local models Group 1 serves, and a cloud model if a key is available. Measure how often each reads a claim correctly. | In: scenarios, the rule parser, Group 1's local models. Out: claim test set and an accuracy table. | A test set of 100 claims with correct readings, and an accuracy table for the parser and at least three models. | 40 | Shared | task 2; Group 1's task 10 for local models |
| 9 | **Fidelity and transfer** | Measure how far the fake sessions are from Group 1's simulator sessions, then run the same benchmark on both. How much of what held on fake data still holds on the simulator? Report the answer, including where it does not. | In: tasks 3 to 6, Group 1's labelled sessions. Out: one figure and a conclusion. | A result with intervals, including the cases where it does not transfer. | 75 | Master | tasks 3 to 6; Group 1's task 7 |
| 10 | **Meetings, report and final talk** | Weekly team meetings, the weekly pull request, a short report and the final presentation. | In: all results. Out: report of at most 12 pages and a talk. | The report is reviewed by Luke and the talk has been rehearsed once. | 210 (6×35) | Shared | all |

## Squads and hours per person

Squad 1 (Benchmark): Master 1, Bachelor 1, Bachelor 2. The first named is the Master and leads the squad.
Squad 2 (Realism and transfer): Master 2, Bachelor 3, Bachelor 4. The first named is the Master and leads the squad.

| | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Master 1 (squad 1) | 10 | 10 | 15 |  | 30 |  |  | 20 |  | 35 | 120 |
| Bachelor 1 (squad 1) | 10 | 10 | 30 | 10 | 15 |  |  | 10 |  | 35 | 120 |
| Bachelor 2 (squad 1) | 10 | 10 | 25 | 15 | 15 |  |  | 10 |  | 35 | 120 |
| Master 2 (squad 2) | 10 |  |  |  |  | 15 | 15 |  | 45 | 35 | 120 |
| Bachelor 3 (squad 2) | 10 |  |  | 25 |  | 20 | 15 |  | 15 | 35 | 120 |
| Bachelor 4 (squad 2) | 10 |  |  | 30 |  | 20 | 10 |  | 15 | 35 | 120 |
| group | 60 | 30 | 70 | 80 | 60 | 55 | 40 | 40 | 75 | 210 | 720 |

Milestones: 30 Oct first result; 13 Nov interface v0 agreed; 4 Dec core working; 11 Dec rig decision; 22 Dec to 6 Jan nothing due; 25 Jan evaluation done; 12 Feb report draft; week of 22 Feb final presentation.

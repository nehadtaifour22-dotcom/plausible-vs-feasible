# Plausible vs Feasible

**Do AI chatbots produce factory schedules that are merely convincing, or actually possible?**

This is a small, fully reproducible benchmark. It gives chatbots the same production-scheduling problem, then checks each answer against every hard rule and compares its cost with the provably optimal solution (found by exhaustive search).

Pure Python 3, no dependencies for the benchmark itself (`matplotlib` is only needed for the charts).

## The problem

A small food factory with two machines:

| | Machine A | Machine B |
|---|---|---|
| Speed | slower | faster (about 50-80% of A's time) |
| Running cost | 1 per minute | 3 per minute |

Hard rules (all must hold):

1. Every job runs once, on one machine, without interruption.
2. One job at a time per machine.
3. **Changeover:** a cleaning time depends on which job follows which.
4. **Deadlines:** each job has a finish-by minute.
5. **Allergens:** on each machine, nut-containing jobs come after all non-nut jobs.
6. **Shutdown window:** machine B must be idle during a fixed 30-minute window (power saving).

Objective: minimize `makespan + running cost`.

Ten instances, from 4 to 7 jobs, from loose to very tight deadlines. Instances are feasible by construction. The number of feasible orderings is printed by `generate` (about 20% of all orderings for the easiest, 0.005% for the hardest), so you can report results by difficulty.

## Run it

```bash
python tests.py                 # 8 sanity tests, under a second
python cli.py generate          # writes data/ and prompts/
```

Then, for each model you want to test:

1. Open a **fresh chat** per instance (no system prompt, default settings).
2. Paste `prompts/chat/instance_XX.txt` (no tools allowed) and/or `prompts/tools/instance_XX.txt` (code execution allowed).
3. Save the model's **entire reply** unchanged to
   `answers/<model-name-and-version>__chat/instance_XX.txt` (or `__tools`).

```bash
python cli.py evaluate                              # results/results.csv, summary.md, feasible_rate.png
python cli.py gantt --label <model>__chat --instance 05   # your answer vs the optimum, violations in red
python cli.py demo                                  # end-to-end smoke run with fake (non-AI) answers
```

## How the checking works

- `pvf/model.py` is the whole definition of the problem and the checker. It ignores any end times a model writes and recomputes them from the processing-time table.
- `pvf/solver.py` tries every order of jobs on both machines (`(n+1)*n!` candidates) and keeps the cheapest valid one. Starting each job as early as allowed is never worse (tested in `tests.py` by inserting random delays), so only orders need to be searched.
- `pvf/report.py` takes the last JSON object containing a `"schedule"` list from each reply.

Why not OR-Tools / a MIP solver? At this size, exhaustive search is exact, needs no dependencies and is easy to audit. For larger instances, swap `solver.py` for CP-SAT.

## Reporting honestly

- Record model name, **exact version**, date, and whether tools were allowed.
- Report feasibility **by difficulty**, not just one average.
- Publish raw answers (`answers/`) next to the results so anyone can re-check.
- A schedule that is infeasible is still scored on how many rules it breaks; cost gap is only computed for feasible schedules.
- Limits: one small problem family, a handful of runs per model, one prompt wording, models change often. Treat results as a snapshot, not a ranking.

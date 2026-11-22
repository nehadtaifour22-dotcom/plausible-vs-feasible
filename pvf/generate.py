"""Random instance generator and prompt writer.

Instances are always feasible by construction: we first build one random valid schedule
and then set each deadline at (or a little after) that schedule's finishing time.
`slack_max` controls how much room the deadlines leave: small slack = hard instance.
"""
import json
import random
from pathlib import Path

from .model import Instance, run_sequence
from .solver import solve

# (number of jobs, maximum deadline slack in minutes): easy -> hard
SUITE = [(4, 300), (4, 200), (5, 300), (5, 200), (5, 100),
         (6, 200), (6, 100), (7, 200), (7, 100), (7, 40)]


def make_instance(idx, n, slack_max, seed):
    rng = random.Random(seed)
    jobs = [f"P{i + 1}" for i in range(n)]
    family = {j: rng.randint(0, 2) for j in jobs}

    time = {}
    for j in jobs:
        a = rng.randrange(20, 61, 5)
        b = max(10, round(a * rng.uniform(0.5, 0.8) / 5) * 5)
        time[j] = {"A": a, "B": b}

    changeover = {
        a: {b: (5 if family[a] == family[b] else 15) + rng.choice([0, 5, 10])
            for b in jobs if b != a}
        for a in jobs
    }
    nuts = rng.sample(jobs, max(1, n // 3))
    w0 = rng.randrange(40, 91, 10)

    inst = Instance(id=f"{idx:02d}", jobs=jobs, time=time, deadline={}, nuts=nuts,
                    changeover=changeover, blocked=[w0, w0 + 30])

    # One random valid schedule: non-nut jobs first, nut jobs last, on each machine.
    plain = [j for j in jobs if j not in nuts]
    nutty = list(nuts)
    rng.shuffle(plain)
    rng.shuffle(nutty)
    seqs = {"A": [], "B": []}
    for j in plain + nutty:
        seqs[rng.choice("AB")].append(j)
    placed = run_sequence(inst, "A", seqs["A"]) + run_sequence(inst, "B", seqs["B"])
    inst.deadline = {j: e + rng.randrange(0, slack_max + 1, 5) for j, _, e in placed}
    return inst


def render_prompt(inst, mode):
    w0, w1 = inst.blocked
    nuts = set(inst.nuts)
    lines = [
        "You are the production planner of a small food factory. Build a schedule for the "
        f"{len(inst.jobs)} jobs below on two machines, A and B.",
        "",
        "HARD RULES (every one of them must hold):",
        "1. Each job runs exactly once, on exactly one machine (A or B), without interruption.",
        "2. A machine runs one job at a time. Processing times depend on the machine (table below).",
        "3. Changeover: if job Y runs right after job X on the same machine, Y may not start "
        "until at least the changeover time from X to Y (table below) has passed since X "
        "finished. The first job on a machine needs no changeover. The two machines are "
        "independent of each other.",
        "4. Deadline: every job must finish at or before its deadline.",
        "5. Allergens: on each machine, every job that contains nuts must come after all "
        "jobs that do not contain nuts.",
        f"6. Machine B is shut down for power saving from minute {w0} to minute {w1}. No job "
        f"may be running on B during that window (a job may finish exactly at minute {w0} "
        f"or start exactly at minute {w1}).",
        "7. Time starts at minute 0. All times are whole minutes.",
        "",
        "OBJECTIVE: minimize  cost = makespan + running cost.",
        "Makespan is the minute at which the last job finishes. Running cost is 1 per minute "
        "of processing on machine A plus 3 per minute of processing on machine B.",
        "",
        "JOBS:",
        "job | minutes on A | minutes on B | deadline | contains nuts",
    ]
    for j in inst.jobs:
        t = inst.time[j]
        lines.append(f"{j} | {t['A']} | {t['B']} | {inst.deadline[j]} | "
                     f"{'yes' if j in nuts else 'no'}")
    lines += ["", "CHANGEOVER MINUTES (row = job that just finished, column = job that starts next):",
              "     | " + " | ".join(inst.jobs)]
    for a in inst.jobs:
        cells = ["-" if a == b else str(inst.changeover[a][b]) for b in inst.jobs]
        lines.append(f"{a} | " + " | ".join(cells))
    lines.append("")
    if mode == "chat":
        lines.append("Solve this by reasoning only. Do not use code execution or any external tool.")
    else:
        lines.append("You may use code execution or any tool you have to solve the problem "
                     "and to verify your answer.")
    lines += [
        "",
        "OUTPUT: finish your answer with one JSON object in exactly this shape, with nothing "
        "after it:",
        '{"schedule": [{"job": "P1", "machine": "A", "start": 0}, {"job": "P2", "machine": "B", "start": 0}]}',
        'List every job exactly once. "start" is the start minute (a whole number).',
    ]
    return "\n".join(lines) + "\n"


def generate(out_dir="data", prompts_dir="prompts"):
    out, prompts = Path(out_dir), Path(prompts_dir)
    out.mkdir(parents=True, exist_ok=True)
    for mode in ("chat", "tools"):
        (prompts / mode).mkdir(parents=True, exist_ok=True)

    summary = []
    for idx, (n, slack) in enumerate(SUITE, start=1):
        inst = make_instance(idx, n, slack, seed=1000 + idx)
        sol = solve(inst)
        assert sol is not None, "instances are feasible by construction"
        (out / f"instance_{inst.id}.json").write_text(
            json.dumps(inst.to_dict(), indent=2), encoding="utf-8")
        (out / f"solution_{inst.id}.json").write_text(
            json.dumps({"cost": sol.cost, "makespan": sol.makespan, "schedule": sol.rows,
                        "feasible_orders": sol.n_feasible, "total_orders": sol.n_total},
                       indent=2), encoding="utf-8")
        for mode in ("chat", "tools"):
            (prompts / mode / f"instance_{inst.id}.txt").write_text(
                render_prompt(inst, mode), encoding="utf-8")
        summary.append((inst.id, n, slack, sol.cost, sol.n_feasible, sol.n_total))
    return summary

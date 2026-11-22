"""The factory scheduling problem: data model, schedule builder and checker.

Everything the experiment relies on is in this file, so it can be read in one sitting.

The factory has two machines, A (slow, cheap) and B (fast, expensive). A schedule says,
for every job, which machine runs it and at which minute it starts.
"""
from collections import Counter
from dataclasses import dataclass, asdict

MACHINES = ("A", "B")
RUN_COST = {"A": 1, "B": 3}  # cost of one processing minute on each machine

# Violations that mean the answer is not even a complete, well-formed schedule.
STRUCTURAL = ("unknown_job", "missing_job", "duplicate_job", "bad_machine", "bad_start")


@dataclass
class Instance:
    id: str
    jobs: list         # job names, e.g. ["P1", "P2", ...]
    time: dict         # time[job][machine] -> processing minutes
    deadline: dict     # deadline[job] -> minute by which the job must be finished
    nuts: list         # jobs that contain nuts (must run after all non-nut jobs, per machine)
    changeover: dict   # changeover[a][b] -> cleaning minutes needed if b runs right after a
    blocked: list      # [start, end]: machine B must be idle during this window

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def nuts_last(seq, nuts):
    """True if, in this machine sequence, no non-nut job comes after a nut job."""
    seen_nut = False
    for job in seq:
        if job in nuts:
            seen_nut = True
        elif seen_nut:
            return False
    return True


def run_sequence(inst, machine, seq):
    """Place the jobs of one machine one after another, each as early as allowed.

    Returns a list of (job, start, end). Starting as early as possible is always the best
    choice here (it can only help deadlines and makespan), which is why the exhaustive
    solver only has to try orders, not start times.
    """
    placed, free_at, prev = [], 0, None
    for job in seq:
        start = free_at if prev is None else free_at + inst.changeover[prev][job]
        dur = inst.time[job][machine]
        if machine == "B":
            w0, w1 = inst.blocked
            if start < w1 and start + dur > w0:  # would touch the shutdown window
                start = w1
        placed.append((job, start, start + dur))
        free_at, prev = start + dur, job
    return placed


def placed_to_rows(placed_by_machine):
    """{"A": [(job, s, e)], "B": [...]} -> [{"job":..., "machine":..., "start":...}]"""
    rows = []
    for m, placed in placed_by_machine.items():
        for job, start, _ in placed:
            rows.append({"job": job, "machine": m, "start": start})
    return rows


@dataclass
class Report:
    counts: dict       # violation type -> how many times it happened
    bad_jobs: set      # jobs involved in at least one violation (for drawing)
    makespan: int      # None if the schedule is structurally broken
    cost: int          # makespan + running cost; None if structurally broken

    @property
    def total(self):
        return sum(self.counts.values())

    @property
    def feasible(self):
        return self.total == 0


def evaluate(inst, rows):
    """Check a proposed schedule against every hard rule and compute its cost.

    `rows` is a list of {"job": str, "machine": "A"|"B", "start": int}.
    The checker ignores any end times the model wrote: it recomputes them from the
    processing-time table, so a model cannot "agree with itself" by mislabelling times.
    """
    counts, bad = Counter(), set()
    seen, items = Counter(), []

    for r in rows:
        job, m, s = r.get("job"), r.get("machine"), r.get("start")
        if job not in inst.jobs:
            counts["unknown_job"] += 1
            continue
        seen[job] += 1
        if m not in MACHINES:
            counts["bad_machine"] += 1
            bad.add(job)
            continue
        if isinstance(s, bool) or not isinstance(s, int) or s < 0:
            counts["bad_start"] += 1
            bad.add(job)
            continue
        items.append((job, m, s, s + inst.time[job][m]))

    for j in inst.jobs:
        if seen[j] == 0:
            counts["missing_job"] += 1
        elif seen[j] > 1:
            counts["duplicate_job"] += seen[j] - 1
            bad.add(j)

    nuts = set(inst.nuts)
    w0, w1 = inst.blocked
    for m in MACHINES:
        seq = sorted((x for x in items if x[1] == m), key=lambda x: (x[2], x[3]))
        for (a, _, _, ea), (b, _, sb, _) in zip(seq, seq[1:]):
            if sb < ea:
                counts["overlap"] += 1
                bad |= {a, b}
            elif sb < ea + inst.changeover.get(a, {}).get(b, 0):
                counts["changeover"] += 1
                bad |= {a, b}
        seen_nut = False
        for job, _, _, _ in seq:
            if job in nuts:
                seen_nut = True
            elif seen_nut:
                counts["nut_order"] += 1
                bad.add(job)
        if m == "B":
            for job, _, s, e in seq:
                if s < w1 and e > w0:
                    counts["blocked_window"] += 1
                    bad.add(job)

    for job, _, _, e in items:
        if e > inst.deadline[job]:
            counts["deadline"] += 1
            bad.add(job)

    makespan = cost = None
    if not any(counts[k] for k in STRUCTURAL):
        makespan = max(e for _, _, _, e in items)
        cost = makespan + sum(RUN_COST[m] * (e - s) for _, m, s, e in items)
    return Report(dict(counts), bad, makespan, cost)

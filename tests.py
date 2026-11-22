"""Sanity tests. Run with:  python tests.py

They prove the three things the experiment depends on:
1. the checker flags every kind of broken schedule,
2. the solver's answer is valid and nothing valid beats it,
3. reply parsing is robust to messy model output.
"""
import random

from pvf.generate import SUITE, make_instance
from pvf.model import Instance, evaluate, nuts_last, run_sequence, RUN_COST
from pvf.report import extract_rows
from pvf.solver import solve


def tiny():
    """A hand-made instance where every answer can be checked by eye."""
    return Instance(
        id="t", jobs=["P1", "P2", "P3"],
        time={"P1": {"A": 30, "B": 20}, "P2": {"A": 30, "B": 20}, "P3": {"A": 30, "B": 20}},
        deadline={"P1": 100, "P2": 100, "P3": 100},
        nuts=["P3"],
        changeover={"P1": {"P2": 10, "P3": 10}, "P2": {"P1": 10, "P3": 10},
                    "P3": {"P1": 10, "P2": 10}},
        blocked=[50, 80],
    )


def rows(*items):
    return [{"job": j, "machine": m, "start": s} for j, m, s in items]


def test_valid_schedule_is_valid():
    r = evaluate(tiny(), rows(("P1", "A", 0), ("P2", "A", 40), ("P3", "B", 0)))
    assert r.feasible and r.makespan == 70
    assert r.cost == 70 + 30 + 30 + 3 * 20  # makespan + A minutes + B minutes * 3


def test_each_violation_is_detected():
    t = tiny()
    assert evaluate(t, rows(("P1", "A", 0), ("P2", "A", 20), ("P3", "B", 0))).counts == {"overlap": 1}
    assert evaluate(t, rows(("P1", "A", 0), ("P2", "A", 35), ("P3", "B", 0))).counts == {"changeover": 1}
    assert evaluate(t, rows(("P3", "A", 0), ("P1", "A", 40), ("P2", "B", 0))).counts == {"nut_order": 1}
    assert evaluate(t, rows(("P1", "A", 0), ("P2", "B", 40), ("P3", "A", 40))).counts == {"blocked_window": 1}
    late = rows(("P1", "A", 0), ("P2", "A", 40), ("P3", "A", 80))
    assert evaluate(t, late).counts == {"deadline": 1}
    assert evaluate(t, rows(("P1", "A", 0), ("P2", "B", 0))).counts == {"missing_job": 1}
    assert evaluate(t, rows(("P1", "A", 0), ("P1", "B", 0), ("P2", "A", 40), ("P3", "B", 60))
                    ).counts["duplicate_job"] == 1
    assert evaluate(t, rows(("P1", "C", 0), ("P2", "A", 0), ("P3", "B", 0))).counts == {"bad_machine": 1}
    assert evaluate(t, rows(("P1", "A", 1.5), ("P2", "B", 0), ("P3", "B", 30))).counts == {"bad_start": 1}


def test_window_edges_are_allowed():
    t = tiny()
    # P1 on B finishes exactly at 50 (start 30), P2 on B starts exactly at 80
    r = evaluate(t, rows(("P1", "B", 30), ("P2", "B", 80), ("P3", "A", 0)))
    assert "blocked_window" not in r.counts


def test_solver_is_valid_and_optimal_on_every_instance():
    rng = random.Random(7)
    for idx, (n, slack) in enumerate(SUITE[:7], start=1):  # n <= 6 keeps this fast
        inst = make_instance(idx, n, slack, seed=1000 + idx)
        sol = solve(inst)
        rep = evaluate(inst, sol.rows)
        assert rep.feasible, f"instance {idx}: solver answer fails the checker {rep.counts}"
        assert rep.cost == sol.cost
        # random valid-looking schedules must never beat the optimum
        for _ in range(1500):
            jobs = inst.jobs[:]
            rng.shuffle(jobs)
            k = rng.randint(0, n)
            pa, pb = run_sequence(inst, "A", jobs[:k]), run_sequence(inst, "B", jobs[k:])
            r = evaluate(inst, [{"job": j, "machine": "A", "start": s} for j, s, _ in pa]
                         + [{"job": j, "machine": "B", "start": s} for j, s, _ in pb])
            if r.feasible:
                assert r.cost >= sol.cost


def test_delaying_jobs_never_beats_the_optimum():
    """The solver assumes 'start as early as allowed' is always best. Try to break that:
    insert random idle time before jobs and check nothing valid is ever cheaper."""
    rng = random.Random(11)
    for idx, (n, slack) in enumerate(SUITE[:7], start=1):
        inst = make_instance(idx, n, slack, seed=1000 + idx)
        opt = solve(inst).cost
        for _ in range(3000):
            jobs = inst.jobs[:]
            rng.shuffle(jobs)
            k = rng.randint(0, n)
            rows_ = []
            for m, seq in (("A", jobs[:k]), ("B", jobs[k:])):
                extra = 0
                for j, s, _ in run_sequence(inst, m, seq):
                    extra += rng.choice([0, 0, 5, 10, 20, 40])
                    rows_.append({"job": j, "machine": m, "start": s + extra})
            r = evaluate(inst, rows_)
            if r.feasible:
                assert r.cost >= opt, (idx, r.cost, opt)


def test_exhaustive_matches_checker_count_on_tiny():
    # 3 jobs: (3+1)*3! = 24 candidates; count how many pass the checker independently
    t = tiny()
    sol = solve(t)
    from itertools import permutations
    ok = 0
    for perm in permutations(t.jobs):
        for k in range(4):
            pa, pb = run_sequence(t, "A", perm[:k]), run_sequence(t, "B", perm[k:])
            r = evaluate(t, [{"job": j, "machine": "A", "start": s} for j, s, _ in pa]
                         + [{"job": j, "machine": "B", "start": s} for j, s, _ in pb])
            ok += r.feasible
    assert ok == sol.n_feasible


def test_parser_handles_messy_replies():
    good = 'Reasoning...\n```json\n{"schedule": [{"Job": "p1", "Machine": "a", "start": 5.0}]}\n```'
    assert extract_rows(good) == [{"job": "P1", "machine": "A", "start": 5}]
    two = 'draft {"schedule": [{"job":"P1","machine":"A","start":0}]} final ' \
          '{"schedule": [{"job":"P2","machine":"B","start":9}]}'
    assert extract_rows(two)[0]["job"] == "P2"  # last JSON wins
    assert extract_rows("no json here") is None
    assert extract_rows('{"plan": []}') is None


def test_nuts_last():
    assert nuts_last(["P1", "P3"], {"P3"})
    assert not nuts_last(["P3", "P1"], {"P3"})


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"\n{len(tests)} tests passed")

"""Exact solver by exhaustive search.

Every schedule of this problem is "an order of jobs on machine A" plus "an order of jobs on
machine B". We list every permutation of the jobs and every place to cut it in two (first
part -> A, second part -> B). That covers every possible assignment exactly once.
For n jobs that is (n + 1) * n! candidates: 40,320 for n = 7, which takes a moment.

Because it looks at everything, the answer is provably optimal. The same loop also counts
how many candidates are feasible, which says how "narrow" the problem is.
"""
from dataclasses import dataclass
from itertools import permutations
from math import factorial

from .model import RUN_COST, nuts_last, placed_to_rows, run_sequence


@dataclass
class Solution:
    cost: int
    makespan: int
    rows: list
    n_feasible: int
    n_total: int


def solve(inst):
    nuts = set(inst.nuts)
    n = len(inst.jobs)
    best = None
    n_feasible = 0

    for perm in permutations(inst.jobs):
        for k in range(n + 1):
            seq_a, seq_b = perm[:k], perm[k:]
            if not (nuts_last(seq_a, nuts) and nuts_last(seq_b, nuts)):
                continue
            pa = run_sequence(inst, "A", seq_a)
            pb = run_sequence(inst, "B", seq_b)
            if any(e > inst.deadline[j] for j, _, e in pa + pb):
                continue
            n_feasible += 1
            makespan = max(e for _, _, e in pa + pb)
            run_cost = (RUN_COST["A"] * sum(e - s for _, s, e in pa)
                        + RUN_COST["B"] * sum(e - s for _, s, e in pb))
            cost = makespan + run_cost
            if best is None or cost < best[0]:
                best = (cost, makespan, {"A": pa, "B": pb})

    if best is None:
        return None
    cost, makespan, placed = best
    return Solution(cost, makespan, placed_to_rows(placed), n_feasible, (n + 1) * factorial(n))

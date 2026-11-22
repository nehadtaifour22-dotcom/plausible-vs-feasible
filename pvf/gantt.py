"""Draw a model's schedule next to the optimal one, with rule-breaking jobs in red."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .model import MACHINES


def _draw(ax, inst, rows, bad, title):
    ypos = {"A": 1, "B": 0}
    for r in rows:
        m, s = r["machine"], r["start"]
        if m not in ypos or not isinstance(s, int) or r["job"] not in inst.jobs:
            continue
        dur = inst.time[r["job"]][m]
        broken = r["job"] in bad
        ax.broken_barh([(s, dur)], (ypos[m] - 0.35, 0.7),
                       facecolors="#d9534f" if broken else "#5b7fa6",
                       edgecolors="white", alpha=0.9)
        ax.text(s + dur / 2, ypos[m], r["job"], ha="center", va="center", color="white",
                fontsize=9, fontweight="bold")
        d = inst.deadline[r["job"]]
        ax.plot([d, d], [ypos[m] - 0.42, ypos[m] + 0.42], color="black", lw=1, ls=":")
    w0, w1 = inst.blocked
    ax.axvspan(w0, w1, ymin=0.0, ymax=0.5, color="grey", alpha=0.25)
    ax.text((w0 + w1) / 2, -0.62, "B shut down", ha="center", fontsize=8, color="grey")
    ax.set_yticks([1, 0])
    ax.set_yticklabels(["Machine A", "Machine B"])
    ax.set_ylim(-0.8, 1.6)
    ax.set_title(title, loc="left", fontsize=11)
    ax.set_xlabel("minutes (dotted line = job deadline)")
    ax.grid(axis="x", alpha=0.2)


def draw(inst, rows, report, optimal_rows, optimal_cost, path):
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    if report.feasible:
        status = f"valid, cost {report.cost}"
    else:
        status = "BREAKS: " + ", ".join(f"{k} x{v}" for k, v in report.counts.items())
    _draw(axes[0], inst, rows, report.bad_jobs, f"Model's schedule ({status})")
    _draw(axes[1], inst, optimal_rows, set(), f"Optimal schedule (cost {optimal_cost})")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)

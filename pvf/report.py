"""Read the models' answers, check them, and produce results.csv, summary.md and a chart.

Folder layout expected for answers:
    answers/<model-name>__<mode>/instance_01.txt   (mode is "chat" or "tools")
Each .txt file is the model's full reply, pasted as-is. The script finds the last JSON
object that contains a "schedule" list and ignores everything else.
"""
import csv
import json
from pathlib import Path
from statistics import mean

from .model import Instance, evaluate

VIOLATIONS = ["unparseable", "unknown_job", "missing_job", "duplicate_job", "bad_machine",
              "bad_start", "overlap", "changeover", "nut_order", "blocked_window", "deadline"]


def _objects(text):
    """Yield every top-level JSON object found inside free text."""
    dec, i = json.JSONDecoder(), 0
    while True:
        i = text.find("{", i)
        if i == -1:
            return
        try:
            obj, end = dec.raw_decode(text, i)
            yield obj
            i = end
        except ValueError:
            i += 1


def _clean_start(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return v  # left as-is: the checker will flag non-integers as bad_start


def extract_rows(text):
    """Return the schedule rows from a model reply, or None if there is no usable JSON."""
    found = None
    for obj in _objects(text):
        if isinstance(obj, dict) and isinstance(obj.get("schedule"), list):
            found = obj["schedule"]  # the last one wins (the final answer)
    if found is None:
        return None
    rows = []
    for item in found:
        if not isinstance(item, dict):
            return None
        low = {str(k).lower(): v for k, v in item.items()}
        rows.append({
            "job": str(low.get("job", "")).strip().upper(),
            "machine": str(low.get("machine", "")).strip().upper(),
            "start": _clean_start(low.get("start")),
        })
    return rows


def load_data(data_dir):
    data_dir = Path(data_dir)
    instances, optima = {}, {}
    for p in sorted(data_dir.glob("instance_*.json")):
        inst = Instance.from_dict(json.loads(p.read_text(encoding="utf-8")))
        instances[inst.id] = inst
        sol = json.loads((data_dir / f"solution_{inst.id}.json").read_text(encoding="utf-8"))
        optima[inst.id] = sol
    return instances, optima


def evaluate_answers(answers_dir, data_dir):
    instances, optima = load_data(data_dir)
    results = []
    for folder in sorted(p for p in Path(answers_dir).iterdir() if p.is_dir()):
        model, _, mode = folder.name.partition("__")
        for f in sorted(folder.glob("instance_*.txt")):
            iid = f.stem.split("_")[1]
            if iid not in instances:
                continue
            rows = extract_rows(f.read_text(encoding="utf-8"))
            row = {"label": folder.name, "model": model, "mode": mode or "unknown",
                   "instance": iid, "parsed": rows is not None,
                   **{v: 0 for v in VIOLATIONS}, "violations": 0, "feasible": False,
                   "cost": "", "optimum": optima[iid]["cost"], "gap_pct": ""}
            if rows is None:
                row["unparseable"] = 1
                row["violations"] = 1
            else:
                rep = evaluate(instances[iid], rows)
                for k, v in rep.counts.items():
                    row[k] = v
                row["violations"] = rep.total
                row["feasible"] = rep.feasible
                if rep.cost is not None:
                    row["cost"] = rep.cost
                if rep.feasible:
                    row["gap_pct"] = round(100 * (rep.cost - row["optimum"]) / row["optimum"], 1)
            results.append(row)
    return results


def summarize(results):
    out = []
    for label in sorted({r["label"] for r in results}):
        rs = [r for r in results if r["label"] == label]
        feas = [r for r in rs if r["feasible"]]
        out.append({
            "label": label,
            "answered": len(rs),
            "parsed": sum(r["parsed"] for r in rs),
            "feasible": len(feas),
            "feasible_pct": round(100 * len(feas) / len(rs), 1),
            "avg_violations": round(mean(r["violations"] for r in rs), 2),
            "avg_gap_pct_when_feasible": round(mean(r["gap_pct"] for r in feas), 1) if feas else "",
        })
    return out


def write_outputs(results, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cols = (["label", "model", "mode", "instance", "parsed", "feasible", "violations"]
            + VIOLATIONS + ["cost", "optimum", "gap_pct"])
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(results)

    summ = summarize(results)
    lines = ["| model__mode | answered | feasible | feasible % | avg violations | avg cost gap % (feasible only) |",
             "|---|---|---|---|---|---|"]
    for s in summ:
        lines.append(f"| {s['label']} | {s['answered']} | {s['feasible']} | {s['feasible_pct']} | "
                     f"{s['avg_violations']} | {s['avg_gap_pct_when_feasible']} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 0.6 * len(summ) + 1.5))
        ax.barh([s["label"] for s in summ], [s["feasible_pct"] for s in summ])
        ax.set_xlim(0, 100)
        ax.set_xlabel("% of answers that satisfy every hard rule")
        ax.invert_yaxis()
        fig.tight_layout()
        fig.savefig(out / "feasible_rate.png", dpi=150)
        plt.close(fig)
    except ImportError:
        pass
    return summ

"""Command line entry point.

    python cli.py generate            build the 10 instances, exact solutions and prompts
    python cli.py evaluate            check everything in answers/ and write results/
    python cli.py gantt --label X --instance 03     draw one answer vs the optimum
    python cli.py demo                run the whole pipeline on fake answers (no real models)
"""
import argparse
import json
import shutil
from pathlib import Path

from pvf.generate import generate
from pvf.gantt import draw
from pvf.model import Instance, evaluate
from pvf.report import evaluate_answers, extract_rows, load_data, write_outputs


def cmd_generate(a):
    for iid, n, slack, cost, feas, total in generate(a.data, a.prompts):
        print(f"instance {iid}: {n} jobs, slack<={slack:>2}  optimum cost={cost:>4}  "
              f"feasible orders {feas}/{total}")
    print(f"\nPrompts written to {a.prompts}/chat and {a.prompts}/tools")


def cmd_evaluate(a):
    results = evaluate_answers(a.answers, a.data)
    if not results:
        print("No answers found. Put replies in answers/<model>__<chat|tools>/instance_01.txt")
        return
    summ = write_outputs(results, a.out)
    print((Path(a.out) / "summary.md").read_text(encoding="utf-8"))
    print(f"Wrote {a.out}/results.csv, summary.md, feasible_rate.png")
    return summ


def cmd_gantt(a):
    instances, optima = load_data(a.data)
    inst = instances[a.instance]
    text = (Path(a.answers) / a.label / f"instance_{a.instance}.txt").read_text(encoding="utf-8")
    rows = extract_rows(text)
    if rows is None:
        raise SystemExit("That answer has no parsable JSON schedule.")
    rep = evaluate(inst, rows)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"gantt_{a.label}_{a.instance}.png"
    draw(inst, rows, rep, optima[a.instance]["schedule"], optima[a.instance]["cost"], path)
    print(f"Wrote {path}")


def _fake_reply(rows, intro):
    return intro + "\n\n```json\n" + json.dumps({"schedule": rows}) + "\n```\n"


def cmd_demo(a):
    """End-to-end smoke run. The answers below are NOT from AI models: they are a perfect
    solver, a naive rule, and unusable text, used to prove the checker tells them apart."""
    root = Path("demo")
    if root.exists():
        shutil.rmtree(root)
    generate(root / "data", root / "prompts")
    instances, optima = load_data(root / "data")
    for iid, inst in instances.items():
        base = root / "answers"
        # 1) the exact optimum
        d = base / "DEMO-exact-solver__tools"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"instance_{iid}.txt").write_text(
            _fake_reply(optima[iid]["schedule"], "Here is the optimal schedule."), encoding="utf-8")
        # 2) a naive "sound reasonable" rule: earliest deadline first, all on A, back to back,
        #    ignoring changeovers and allergens
        order = sorted(inst.jobs, key=lambda j: inst.deadline[j])
        t, rows = 0, []
        for j in order:
            rows.append({"job": j, "machine": "A", "start": t})
            t += inst.time[j]["A"]
        d = base / "DEMO-naive-rule__chat"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"instance_{iid}.txt").write_text(
            _fake_reply(rows, "I scheduled by earliest deadline, which keeps customers happy."),
            encoding="utf-8")
        # 3) unusable text
        d = base / "DEMO-no-json__chat"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"instance_{iid}.txt").write_text(
            "A good plan is to start with P1 and finish the nut products last.", encoding="utf-8")

    results = evaluate_answers(root / "answers", root / "data")
    write_outputs(results, root / "results")
    print((root / "results" / "summary.md").read_text(encoding="utf-8"))
    text = (root / "answers" / "DEMO-naive-rule__chat" / "instance_05.txt").read_text(encoding="utf-8")
    inst = instances["05"]
    rep = evaluate(inst, extract_rows(text))
    draw(inst, extract_rows(text), rep, optima["05"]["schedule"], optima["05"]["cost"],
         root / "results" / "gantt_demo_05.png")
    print("Demo files are in ./demo (results/summary.md, results/gantt_demo_05.png)")


def main():
    p = argparse.ArgumentParser(description="Plausible vs Feasible benchmark")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--data", default="data")
    g.add_argument("--prompts", default="prompts")
    g.set_defaults(fn=cmd_generate)

    e = sub.add_parser("evaluate")
    e.add_argument("--answers", default="answers")
    e.add_argument("--data", default="data")
    e.add_argument("--out", default="results")
    e.set_defaults(fn=cmd_evaluate)

    v = sub.add_parser("gantt")
    v.add_argument("--label", required=True)
    v.add_argument("--instance", required=True)
    v.add_argument("--answers", default="answers")
    v.add_argument("--data", default="data")
    v.add_argument("--out", default="results")
    v.set_defaults(fn=cmd_gantt)

    d = sub.add_parser("demo")
    d.set_defaults(fn=cmd_demo)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

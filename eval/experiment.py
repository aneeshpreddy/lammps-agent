"""Experiment runner and results tables (plan Days 40-43).

  python -m eval.experiment run --split dev --systems baseline agent-nofeedback agent [agent-tiers01 agent-checked]
                                [--repeats 3] [--tasks ...] [--mock perfect] [--out runs/exp/<name>]
  python -m eval.experiment tables runs/exp/<name> [--write-doc docs/RESULTS_DEV.md]

run     one harness evaluation per system into <out>/<system>/ (same tasks, same repeats, eval/harness.py),
        then the tables. The test split runs only if scripts/freeze_config.py --check finds no change since
        the code freeze. A system folder that already holds results is reused, never overwritten, so an
        interrupted experiment continues with the systems still missing.
tables  from the result folders (plan Day 43):
          1. success per system: mean of per-task rates, spread across repeats, pass@k, validity
          2. success by domain, difficulty and force field
          3. ablation contrasts on the same tasks: per-task wins / ties / losses and an exact sign test
          4. failure categories per system
          5. baseline failures (A) and how often each other system succeeded on the same task and repeat
          6. recovery inside the loop: the first attempt's outcome -> final success
          7. attempts, tokens, cost, latency
        Figures (PNG, <out>/figures/): success per system with per-repeat points; success by domain.
Ablation labels (plan Day 42): A baseline, B agent-nofeedback, C agent, D agent-tiers01, E agent-checked.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import shutil
import sys
from collections import Counter, defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from eval.harness import evaluate, load_tasks  # noqa: E402

LABELS = {"baseline": "A", "agent-nofeedback": "B", "agent": "C", "agent-tiers01": "D", "agent-checked": "E"}
WHAT = {"A": "single call, no tools", "B": "loop, retries without feedback", "C": "loop + validator feedback",
        "D": "loop, Tier 0-1 feedback only", "E": "C + build summary + request check"}
CONTRASTS = [("B", "A", "tools and retries"), ("C", "B", "validator feedback"),
             ("C", "A", "the whole agent"), ("C", "D", "Tier 2-3 feedback"), ("E", "C", "request check")]
DOMAINS = ("mineral", "pce", "composite")
# reference palette (dataviz skill, references/palette.md), light mode, categorical slots 1-5 in fixed order;
# the colour follows the system (A..E), never its position in a given run
SERIES = dict(zip("ABCDE", ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]))
INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def base_name(meta_name: str) -> str:
    return meta_name.split("-mock-")[0]


# ---------------------------------------------------------------------------------------------
def mock_for(name: str, mocks) -> str:
    """--mock POLICY (every system) or SYSTEM=POLICY items."""
    plain = [m for m in mocks or [] if "=" not in m]
    named = dict(m.split("=", 1) for m in mocks or [] if "=" in m)
    return named.get(name, plain[0] if plain else None)


def run(systems, split, repeats, out, task_ids=None, mocks=None, log=print):
    from eval.systems import make_system
    if split == "test" and not any(mock_for(n, mocks) for n in systems):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from freeze_config import check
        diff = check()
        if diff:
            raise SystemExit("the test split runs only on the frozen configuration (plan Day 39):\n" + "\n".join(diff))
    tasks = load_tasks(split, task_ids)
    os.makedirs(out, exist_ok=True)
    for name in systems:
        sd = os.path.join(out, name)
        if os.path.exists(os.path.join(sd, "results.json")):
            log(f"{name}: results exist, kept")
            continue
        if os.path.isdir(sd):
            raise FileExistsError(f"{sd} holds an unfinished run: move it away and run again")
        system = make_system(name, mock=mock_for(name, mocks))
        log(f"{name} ({LABELS.get(name, '?')}): {len(tasks)} tasks x {repeats} repeats")
        evaluate(system, tasks, repeats, sd, log=lambda s: log(f"  {name}: {s}"))
    return out


# ---------------------------------------------------------------------------------------------
def load(exp_dir: str) -> list:
    """[{name, label, result, traces{(task, repeat): trace}}] for every system folder with results.json."""
    out = []
    for d in sorted(os.listdir(exp_dir)):
        p = os.path.join(exp_dir, d, "results.json")
        if not os.path.exists(p):
            continue
        res = json.load(open(p))
        name = base_name(res["fixed_conditions"]["system"].get("name", d))
        traces = {}
        for r in res["runs"]:
            tp = os.path.join(exp_dir, d, "runs", r["task"], f"r{r['repeat']}", "trace.json")
            if os.path.exists(tp):
                traces[(r["task"], r["repeat"])] = (json.load(open(tp)).get("trace") or {})
        out.append({"name": name, "label": LABELS.get(name, name), "dir": d, "result": res, "traces": traces})
    out.sort(key=lambda s: (s["label"] not in WHAT, s["label"]))
    return out


def sign_test(wins: int, losses: int) -> float:
    """Exact two-sided sign test on per-task differences (ties dropped)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def first_attempt(trace: dict) -> str:
    att = trace.get("attempts") or []
    if not att:
        return "no attempt"
    a = att[0]
    if a["verdict"] == "PASS" and not a["fingerprint"]:
        return "accepted in attempt 1"
    fp = a["fingerprint"]
    first = fp[0] if fp else "?"
    return first[0] if isinstance(first, list) else first


def tables(exp_dir: str) -> str:
    S = load(exp_dir)
    if not S:
        raise SystemExit(f"no results.json under {exp_dir}")
    r0 = S[0]["result"]
    fc = r0["fixed_conditions"]
    tasks = r0["tasks"]
    L = [f"# Results: {', '.join(s['label'] for s in S)} on {len(tasks)} tasks × {r0['repeats']} repeats\n",
         f"Generated by `python -m eval.experiment tables` on {_dt.date.today().isoformat()} from `{os.path.relpath(exp_dir, ROOT)}`. "
         f"git {fc['git_commit'][:7]}{' (dirty)' if fc['git_dirty'] else ''} · validator {fc['validator_version']} · "
         f"split {fc['split_sha256'][:12]}… · {fc['lammps']}. Success = every Tier 0–3 check PASS and TC.2 PASS "
         "(METRICS.md v1.2); rates are means of per-task rates.\n"]
    models = {s["result"]["fixed_conditions"]["system"].get("model") for s in S}
    L.append(f"Model: {', '.join(sorted(m or 'none (mock)' for m in models))}. Prices: "
             f"{fc.get('pricing', {}).get('source', 'eval/pricing.json')} ({fc.get('pricing', {}).get('date', '?')}).\n")
    for s in S:
        if s["result"]["tasks"] != tasks or s["result"]["repeats"] != r0["repeats"]:
            L.append(f"**Warning:** {s['label']} ran on different tasks or repeats; contrasts with it are not paired.\n")

    # 1. success per system
    L += ["## 1. Success per system", "", "| | System | Success | Spread across repeats (mean ± sd, min–max) | "
          f"pass@{r0['repeats']} | Validity |", "|---|---|---|---|---|---|"]
    for s in S:
        a = s["result"]["aggregate"]
        sp = a["spread_across_repeats"]
        L.append(f"| **{s['label']}** | {s['name']} ({WHAT.get(s['label'], '')}) | **{a['system_success_rate']:.3f}** | "
                 f"{sp['mean']:.3f} ± {sp['sd']:.3f} ({sp['min']:.3f}–{sp['max']:.3f}) | {a['pass_at_k']:.3f} | "
                 f"{a['validity_rate']:.3f} |")

    # 2. breakdowns
    L += ["", "## 2. Success by domain, difficulty and force field", ""]
    for key, title in (("by_domain", "Domain"), ("by_difficulty", "Difficulty"), ("by_force_field", "Force field")):
        groups = sorted({g for s in S for g in s["result"]["aggregate"][key]})
        L += [f"| {title} | " + " | ".join(f"{g} ({S[0]['result']['aggregate'][key].get(g, {}).get('tasks', 0)} tasks)"
                                           for g in groups) + " |", "|---|" + "---|" * len(groups)]
        for s in S:
            a = s["result"]["aggregate"][key]
            L.append(f"| {s['label']} | " + " | ".join(f"{a[g]['rate']:.3f}" if g in a else "—" for g in groups) + " |")
        L.append("")

    # 3. contrasts
    by = {s["label"]: s for s in S}
    rows = []
    for x, y, what in CONTRASTS:
        if x not in by or y not in by:
            continue
        px, py = by[x]["result"]["aggregate"]["per_task"], by[y]["result"]["aggregate"]["per_task"]
        common = [t for t in px if t in py]
        d = [px[t] - py[t] for t in common]
        w, l = sum(v > 0 for v in d), sum(v < 0 for v in d)
        rows.append(f"| {x} vs {y} | {what} | {np.mean(d):+.3f} | {w} / {len(d) - w - l} / {l} | {sign_test(w, l):.3f} |")
    if rows:
        L += ["## 3. Ablation contrasts (same tasks, same repeats)", "",
              "| Contrast | What it isolates | Δ success | Tasks better / same / worse | Sign test p |",
              "|---|---|---|---|---|"] + rows
        L += ["", f"Per-task rates over {len(tasks)} tasks; ties are dropped by the sign test, which reaches p < 0.05 only "
              "with at least 6 tasks better and none worse. Report the per-task counts, not only the mean.", ""]

    # 4. failure categories
    cats = sorted({c for s in S for c in s["result"]["aggregate"]["failure_categories"]})
    if cats:
        L += ["## 4. Failure categories (runs)", "", "| | " + " | ".join(cats) + " |", "|---|" + "---|" * len(cats)]
        for s in S:
            fc_ = s["result"]["aggregate"]["failure_categories"]
            L.append(f"| {s['label']} | " + " | ".join(str(fc_.get(c, 0)) for c in cats) + " |")
        L.append("")

    # 5. baseline failures and the others on the same (task, repeat)
    if "A" in by and len(S) > 1:
        base = {(r["task"], r["repeat"]): r for r in by["A"]["result"]["runs"]}
        others = [s for s in S if s["label"] != "A"]
        succ = {s["label"]: {(r["task"], r["repeat"]): r["success"] for r in s["result"]["runs"]} for s in others}
        groups = defaultdict(list)
        for k, r in base.items():
            if not r["success"]:
                groups[r["category"]].append(k)
        if groups:
            L += ["## 5. Baseline (A) failures: how often each system succeeded on the same task and repeat", "",
                  "| A's failure | Runs | " + " | ".join(s["label"] for s in others) + " |",
                  "|---|---|" + "---|" * len(others)]
            for cat, keys in sorted(groups.items(), key=lambda kv: -len(kv[1])):
                L.append(f"| {cat} | {len(keys)} | " + " | ".join(
                    f"{sum(succ[s['label']].get(k, False) for k in keys)}/{len(keys)}" for s in others) + " |")
            L.append("")

    # 6. recovery inside the loop
    loops = [s for s in S if s["traces"] and any(t.get("attempts") for t in s["traces"].values())]
    if loops:
        L += ["## 6. Inside the loop: first attempt -> final success", "",
              "The first attempt's outcome as the loop saw it (in-loop validation, request check for E); "
              "\"accepted in attempt 1\" runs can still fail TC.2 afterwards.", ""]
        for s in loops:
            fin = {(r["task"], r["repeat"]): r["success"] for r in s["result"]["runs"]}
            g = defaultdict(list)
            for k, tr in s["traces"].items():
                g[first_attempt(tr)].append(fin.get(k, False))
            L += [f"**{s['label']}** ({s['name']}): " + "; ".join(
                f"{k} → {sum(v)}/{len(v)} succeed" for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))), ""]

    # 7. cost
    L += ["## 7. Attempts, tokens, cost, latency (per task run)", "",
          "| | Mean attempts | Escalations | Input tokens | Output tokens | Cache read | Cost (USD) | Total (USD) | Latency mean / max (s) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s in S:
        a = s["result"]["aggregate"]
        tk = a["tokens_per_task"]
        L.append(f"| {s['label']} | {a['mean_attempts']} | {a.get('escalations', 0)} | {tk['input_tokens']:.0f} | "
                 f"{tk['output_tokens']:.0f} | {tk['cache_read_input_tokens']:.0f} | {a['cost_per_task_usd']} | "
                 f"{a['total_cost_usd']} | {a['latency_s']['mean']} / {a['latency_s']['max']} |")
    L += ["", "The validator's own results (948 corrupted files, 0 missed) are in docs/VALIDATOR_RESULTS.md.", ""]
    figs = figures(S, exp_dir)
    if figs:
        L += ["## Figures", ""] + [f"![{t}](figures/{os.path.basename(p)})" for t, p in figs] + [""]
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------
def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=INK2, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 1.05)


def figures(S, exp_dir) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fdir = os.path.join(exp_dir, "figures")
    os.makedirs(fdir, exist_ok=True)
    out = []

    # success per system, one series: bars + per-repeat points
    fig, ax = plt.subplots(figsize=(6.4, 3.6), facecolor=SURFACE)
    _style(ax)
    x = np.arange(len(S))
    for i, s in enumerate(S):
        a = s["result"]["aggregate"]
        ax.bar(i, a["system_success_rate"], width=0.56, color=SERIES["A"], zorder=2)
        pts = a["spread_across_repeats"]["per_repeat"]
        ax.scatter(i + np.linspace(-0.12, 0.12, len(pts)), pts, s=22, color=INK, zorder=3, linewidths=0)
        ax.text(i, a["system_success_rate"] + 0.03, f"{a['system_success_rate']:.2f}", ha="center", color=INK, fontsize=9)
    ax.set_xticks(x, [f"{s['label']}\n{s['name']}" for s in S], fontsize=8, color=INK2)
    ax.set_ylabel("success rate", color=INK2)
    ax.set_title("Task success per system (bar: mean; dots: each repeat)", color=INK, fontsize=10, loc="left")
    p = os.path.join(fdir, "success_per_system.png")
    fig.tight_layout()
    fig.savefig(p, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    out.append(("Task success per system", p))

    # success by domain: grouped bars, one series per system (fixed slot order), legend
    doms = [d for d in DOMAINS if any(d in s["result"]["aggregate"]["by_domain"] for s in S)]
    if doms and all(s["label"] in SERIES for s in S):
        fig, ax = plt.subplots(figsize=(6.4, 3.6), facecolor=SURFACE)
        _style(ax)
        w = 0.8 / len(S)
        for i, s in enumerate(S):
            bd = s["result"]["aggregate"]["by_domain"]
            vals = [bd.get(d, {}).get("rate", 0) for d in doms]
            xs = np.arange(len(doms)) - 0.4 + w * (i + 0.5)
            ax.bar(xs, vals, width=w, color=SERIES[s["label"]], edgecolor=SURFACE, linewidth=1.5,
                   label=f"{s['label']} {s['name']}", zorder=2)
            for xv, v in zip(xs, vals):
                if v == 0:                      # a zero bar is invisible: say so
                    ax.text(xv, 0.015, "0", ha="center", va="bottom", color=MUTED, fontsize=7)
        ax.set_xticks(np.arange(len(doms)), doms, color=INK2)
        ax.set_ylabel("success rate", color=INK2)
        ax.set_title("Task success by domain", color=INK, fontsize=10, loc="left")
        ax.legend(frameon=False, fontsize=7.5, labelcolor=INK2, ncol=len(S), loc="upper left",
                  bbox_to_anchor=(0, -0.1), handlelength=1.2, columnspacing=1.2)
        p = os.path.join(fdir, "success_by_domain.png")
        fig.tight_layout()
        fig.savefig(p, dpi=200, facecolor=SURFACE)
        plt.close(fig)
        out.append(("Task success by domain", p))
    return out


# ---------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m eval.experiment", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--systems", nargs="+", default=["baseline", "agent-nofeedback", "agent"])
    r.add_argument("--split", default="dev")
    r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--tasks", nargs="*")
    r.add_argument("--mock", nargs="*", help="scripted models (checks the pipeline, never a result): POLICY for every "
                   "system, or SYSTEM=POLICY, e.g. baseline=perfect agent=fix agent-checked=wrongvalid")
    r.add_argument("--out")
    r.add_argument("--write-doc")
    t = sub.add_parser("tables")
    t.add_argument("exp_dir")
    t.add_argument("--write-doc")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        out = a.out or os.path.join(ROOT, "runs", "exp", f"{a.split}_{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}")
        run(a.systems, a.split, a.repeats, out, a.tasks, a.mock)
        exp = out
    else:
        exp = a.exp_dir
    md = tables(exp)
    with open(os.path.join(exp, "results.md"), "w") as fh:
        fh.write(md)
    print(md)
    if a.write_doc:
        ddir = os.path.dirname(os.path.abspath(a.write_doc))
        fdir = os.path.join(ddir, "figures")
        os.makedirs(fdir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(a.write_doc))[0].lower()
        for f in os.listdir(os.path.join(exp, "figures")):
            shutil.copy(os.path.join(exp, "figures", f), os.path.join(fdir, f"{stem}_{f}"))
        with open(a.write_doc, "w") as fh:
            fh.write(md.replace("](figures/", f"](figures/{stem}_"))


if __name__ == "__main__":
    main()

"""Evaluation harness (plan Day 21; METRICS.md v1.1).

  python -m eval.harness --system oracle         --split dev --repeats 3   # must score 100 %
  python -m eval.harness --system corrupt-file   --split dev --repeats 3   # must score ~0 % (validity fails)
  python -m eval.harness --system corrupt-spec   --split dev --repeats 3   # must score ~0 % (valid, TC.2 fails)
  python -m eval.harness --system baseline       --split dev --repeats 3   # single-call baseline (needs an API key)

evaluate(system, tasks, repeats, outdir) runs every task `repeats` times, scores each output with the
validator (Tiers 0-3 under the task's declared configuration) and TC.2 against the task's reference, and
writes <outdir>/results.json (every run, the aggregate, the fixed conditions) and <outdir>/summary.md.

A system is a callable  system(task_view, workdir) -> dict  with keys
  data_file  path of the produced DATA FILE, or None (declined / failed: scored NO_OUTPUT)
  usage      {"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"}
  builder_refused, error, attempts, trace
and an attribute `meta` (name, model, settings). task_view is {"id", "input"} only — METRICS §1: the hidden
spec, reference and TC mode are never shown — unless the system sets `needs_hidden = True` (the oracle and
corrupters, which exist to check the harness itself).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from typing import Dict, List

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from validator import __version__ as VALIDATOR_VERSION, load_config, validate  # noqa: E402

TASKS_DIR = os.path.join(ROOT, "eval", "tasks")
SPLIT = os.path.join(ROOT, "eval", "split.json")
PRICING = os.path.join(ROOT, "eval", "pricing.json")
# METRICS.md v1.1 §5 / LOG.md 2026-10-26: the frozen split every scored run is tied to
SPLIT_SHA256 = "063c2ddad24be986bf16dd3b8a549c3681871837d133d20340416003d6cb5fe4"
TEST_OPENS = _dt.date(2026, 11, 16)          # METRICS.md §6
TIER_ORDER = {0: 0, 1: 1, 2: 2, 3: 3, "TC": 4}


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ---------------------------------------------------------------------------------------------
def load_tasks(split: str, ids: List[str] = None, today: _dt.date = None) -> List[dict]:
    """Tasks of a split, after checking the split file and every task file against the frozen hashes."""
    if _sha(SPLIT) != SPLIT_SHA256:
        raise RuntimeError(f"eval/split.json does not match the frozen hash {SPLIT_SHA256[:12]}… (METRICS §5); "
                           "a changed split needs a new METRICS version")
    sp = json.load(open(SPLIT))
    today = today or _dt.date.today()
    if split == "test" and today < TEST_OPENS:
        raise RuntimeError(f"the test split is closed until {TEST_OPENS} (METRICS §6)")
    if split not in ("dev", "test"):
        raise ValueError("split must be 'dev' or 'test'")
    chosen = sp[split] if not ids else [i for i in ids if i in sp[split]]
    if ids and set(ids) - set(chosen):
        raise ValueError(f"tasks {sorted(set(ids) - set(chosen))} are not in the {split} split")
    tasks = []
    for tid in chosen:
        t = json.load(open(os.path.join(TASKS_DIR, f"{tid}.json")))
        h = hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()
        if h != sp["tasks_sha256"][tid]:
            raise RuntimeError(f"task {tid} changed after the split was frozen")
        tasks.append(t)
    return tasks


def task_config(task: dict) -> dict:
    """Declared configuration + the reference's overrides (TC mode, cell comparison, density family)."""
    side = os.path.join(ROOT, os.path.splitext(task["reference"])[0] + ".json")
    overrides = json.load(open(side)).get("overrides", {})
    return load_config(declared=task["declared_config"], overrides={"declared": overrides})


def first_failing(res) -> str:
    fails = [c for c in res.checks if c.verdict == "FAIL"]
    if not fails:
        return ""
    return min(fails, key=lambda c: (TIER_ORDER.get(c.tier, 9), c.property)).property


def score(task: dict, out: dict) -> dict:
    row = {"valid": False, "tc2": None, "success": False, "verdict": None, "tier_reached": None,
           "failing": [], "not_pass": [], "first_failing": "", "category": ""}
    path = out.get("data_file")
    if not path or not os.path.exists(path):
        row["category"] = "NO_OUTPUT"
        return row
    res = validate(path, task_config(task), reference=os.path.join(ROOT, task["reference"]))
    tc2 = res.get("TC.2")
    row.update({"valid": bool(res.passed), "tc2": tc2.verdict if tc2 else None, "verdict": res.verdict,
                "tier_reached": res.tier_reached, "failing": sorted(c.property for c in res.failing()),
                "not_pass": sorted(f"{c.property}:{c.verdict}" for c in res.checks
                                   if c.verdict not in ("PASS", "NOT_APPLICABLE")),
                "first_failing": first_failing(res),
                "failing_details": [{"property": c.property, "tier": c.tier, "message": (c.message or "")[:300]}
                                    for c in res.checks if c.verdict == "FAIL"],
                "data_sha256": _sha(path),
                "validation_s": round(res.elapsed_s, 2)})
    row["success"] = row["valid"] and row["tc2"] == "PASS"
    if row["success"]:
        row["category"] = "SUCCESS"
    elif row["first_failing"] and row["first_failing"] != "TC.2":
        row["category"] = row["first_failing"]
    elif row["valid"]:
        row["category"] = "TC_ONLY"
    else:
        row["category"] = "INCOMPLETE"          # no FAIL, but some check NOT_CALIBRATED / NOT_EVALUATED
    return row


# ---------------------------------------------------------------------------------------------
def prices() -> dict:
    return json.load(open(PRICING)) if os.path.exists(PRICING) else {"models": {}}


def cost_usd(model: str, usage: dict, table: dict):
    p = table.get("models", {}).get(model)
    if not p or not usage:
        return 0.0 if not usage else None
    return round((usage.get("input_tokens", 0) * p["input"] + usage.get("output_tokens", 0) * p["output"]
                  + usage.get("cache_creation_input_tokens", 0) * p["cache_write_5m"]
                  + usage.get("cache_read_input_tokens", 0) * p["cache_read"]) / 1e6, 6)


def fm_map() -> Dict[str, List[str]]:
    """Property -> failure modes, from the corruption manifest (operators' expected failing properties)."""
    path = os.path.join(ROOT, "data", "corrupted", "manifest.json")
    out = defaultdict(set)
    if os.path.exists(path):
        for f in json.load(open(path))["files"]:
            for p in f["expected_failing_properties"]:
                out[p].add(f["failure_mode"])
    return {k: sorted(v) for k, v in out.items()}


def fixed_conditions(tasks: List[dict], system_meta: dict) -> dict:
    def git(*a):
        try:
            return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        except OSError:
            return ""
    configs = {}
    for t in tasks:
        d = task_config(t)["declared"]
        configs[t["declared_config"]] = {"config_id": d.get("config_id"), "config_version": d.get("config_version"),
                                         "calibration": d.get("calibration"),
                                         "calibration_sha256": _sha(os.path.join(ROOT, d["calibration"]))
                                         if d.get("calibration") else None}
    lmp = open(os.path.join(ROOT, "docs", "lammps_build.txt")).read().strip().splitlines()
    return {"date": _dt.datetime.now().isoformat(timespec="seconds"), "git_commit": git("rev-parse", "HEAD"),
            "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
            "validator_version": VALIDATOR_VERSION, "configs": configs,
            "lammps": next((l.strip() for l in lmp if "LAMMPS" in l or "Simulator" in l), lmp[0] if lmp else ""),
            "split_sha256": _sha(SPLIT), "python": platform.python_version(), "system": system_meta,
            "pricing": {k: v for k, v in prices().items() if k != "models"}}


# ---------------------------------------------------------------------------------------------
def aggregate(runs: List[dict], tasks: List[dict], repeats: int) -> dict:
    by_task = defaultdict(list)
    for r in runs:
        by_task[r["task"]].append(r)
    per_task = {t["id"]: float(np.mean([r["success"] for r in by_task[t["id"]]])) for t in tasks}
    per_repeat = [float(np.mean([r["success"] for r in runs if r["repeat"] == k])) for k in range(repeats)]

    def group(key):
        g = defaultdict(list)
        for t in tasks:
            g[t[key]].append(per_task[t["id"]])
        return {k: {"rate": round(float(np.mean(v)), 4), "tasks": len(v)} for k, v in sorted(g.items())}
    fmm = fm_map()
    fm_inc = Counter()
    for r in runs:
        for fm in sorted({fm for p in r["failing"] for fm in fmm.get(p, [])}):
            fm_inc[fm] += 1
    n = len(runs)
    costs = [r["cost_usd"] for r in runs if r["cost_usd"] is not None]
    agent = [r for r in runs if r.get("attempts", 1) > 1]
    return {
        "system_success_rate": round(float(np.mean(list(per_task.values()))), 4),
        "spread_across_repeats": {"per_repeat": [round(x, 4) for x in per_repeat],
                                  "mean": round(float(np.mean(per_repeat)), 4),
                                  "sd": round(float(np.std(per_repeat, ddof=1)), 4) if repeats > 1 else 0.0,
                                  "min": round(min(per_repeat), 4), "max": round(max(per_repeat), 4)},
        "per_task": {k: round(v, 4) for k, v in per_task.items()},
        "by_difficulty": group("difficulty"), "by_domain": group("domain"), "by_force_field": group("force_field"),
        "pass_at_k": round(float(np.mean([any(r["success"] for r in by_task[t["id"]]) for t in tasks])), 4),
        "validity_rate": round(sum(r["valid"] for r in runs) / n, 4),
        "tier_reached": dict(sorted(Counter(str(r["tier_reached"]) for r in runs).items())),
        "failure_categories": dict(Counter(r["category"] for r in runs if not r["success"]).most_common()),
        "failure_mode_incidence": {k: round(v / n, 4) for k, v in sorted(fm_inc.items())},
        "no_output": sum(r["category"] == "NO_OUTPUT" for r in runs),
        "builder_refusals": sum(bool(r.get("builder_refused")) for r in runs),
        "recovery_rate": (round(sum(r["success"] for r in agent) / len(agent), 4) if agent else None),
        "mean_attempts": round(float(np.mean([r.get("attempts", 1) for r in runs])), 3),
        "escalations": sum(bool(r.get("escalated")) for r in runs),
        "stop_reasons": dict(Counter((r.get("stop") or "").split(" (")[0] for r in runs if r.get("stop"))),
        "tokens_per_task": {k: round(float(np.mean([r["usage"].get(k, 0) for r in runs])), 1)
                            for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")},
        "cost_per_task_usd": round(float(np.mean(costs)), 5) if costs else None,
        "total_cost_usd": round(float(sum(costs)), 4) if costs else None,
        "latency_s": {"mean": round(float(np.mean([r["latency_s"] for r in runs])), 2),
                      "max": round(float(max(r["latency_s"] for r in runs)), 2)},
        "runs": n,
    }


def evaluate(system, tasks: List[dict], repeats: int, outdir: str, log=print) -> dict:
    os.makedirs(outdir, exist_ok=True)
    if isinstance(getattr(system, "system", None), str):    # the exact system prompt of this run (plan Day 24)
        with open(os.path.join(outdir, "system_prompt.txt"), "w") as fh:
            fh.write(system.system)
    table = prices()
    model = getattr(system, "meta", {}).get("model")
    runs = []
    for k in range(repeats):
        for t in tasks:
            wd = os.path.join(outdir, "runs", t["id"], f"r{k}")
            os.makedirs(wd, exist_ok=True)
            view = t if getattr(system, "needs_hidden", False) else {"id": t["id"], "input": t["input"]}
            t0 = time.time()
            try:
                out = system(view, wd, repeat=k)
            except Exception as e:      # a crashing system is a failed run, not a crashed harness
                out = {"data_file": None, "error": f"{type(e).__name__}: {e}", "trace": {"traceback": traceback.format_exc()}}
            gen_s = time.time() - t0
            row = score(t, out)
            usage = out.get("usage") or {}
            row.update({"task": t["id"], "repeat": k, "difficulty": t["difficulty"], "domain": t["domain"],
                        "force_field": t["force_field"], "usage": usage, "cost_usd": cost_usd(model, usage, table),
                        "latency_s": round(time.time() - t0, 2), "generation_s": round(gen_s, 2),
                        "builder_refused": bool(out.get("builder_refused")), "error": out.get("error"),
                        "attempts": out.get("attempts", 1), "stop": out.get("stop"),
                        "escalated": bool(out.get("escalated"))})
            with open(os.path.join(wd, "trace.json"), "w") as fh:
                json.dump({"output": {k2: v for k2, v in out.items() if k2 != "trace"}, "trace": out.get("trace"),
                           "score": row}, fh, indent=2, default=str)
            runs.append(row)
            log(f"[{k}] {t['id']}: {'SUCCESS' if row['success'] else row['category']}"
                f"{' (' + row['error'][:100] + ')' if row.get('error') else ''}  {row['latency_s']} s")
    result = {"fixed_conditions": fixed_conditions(tasks, getattr(system, "meta", {})), "repeats": repeats,
              "tasks": [t["id"] for t in tasks], "aggregate": aggregate(runs, tasks, repeats), "runs": runs}
    with open(os.path.join(outdir, "results.json"), "w") as fh:
        json.dump(result, fh, indent=2, default=str)
    with open(os.path.join(outdir, "summary.md"), "w") as fh:
        fh.write(summary_md(result))
    return result


def summary_md(result: dict) -> str:
    a, fc = result["aggregate"], result["fixed_conditions"]
    sp = a["spread_across_repeats"]
    L = [f"# {fc['system'].get('name', 'system')} — {len(result['tasks'])} tasks × {result['repeats']} repeats\n",
         f"{fc['date']} · git {fc['git_commit'][:7]}{' (dirty)' if fc['git_dirty'] else ''} · validator {fc['validator_version']} · "
         f"split {fc['split_sha256'][:12]}… · {fc['lammps']}\n",
         f"System: `{json.dumps(fc['system'], sort_keys=True)}`\n",
         "| Measure | Value |", "|---|---|",
         f"| **System success rate** (mean of per-task rates) | **{a['system_success_rate']:.3f}** |",
         f"| Spread across repeats (mean ± sd, min–max) | {sp['mean']:.3f} ± {sp['sd']:.3f} ({sp['min']:.3f}–{sp['max']:.3f}) |",
         f"| pass@{result['repeats']} | {a['pass_at_k']:.3f} |",
         f"| Validity rate (all tiers PASS) | {a['validity_rate']:.3f} |",
         f"| No output / builder refusals | {a['no_output']} / {a['builder_refusals']} |",
         f"| Mean attempts | {a['mean_attempts']} |",
         f"| Tokens per task (in / out / cache write / cache read) | {a['tokens_per_task']['input_tokens']} / "
         f"{a['tokens_per_task']['output_tokens']} / {a['tokens_per_task']['cache_creation_input_tokens']} / "
         f"{a['tokens_per_task']['cache_read_input_tokens']} |",
         f"| Cost per task / total (USD) | {a['cost_per_task_usd']} / {a['total_cost_usd']} |",
         f"| Latency mean / max (s) | {a['latency_s']['mean']} / {a['latency_s']['max']} |", ""]
    for key, title in (("by_difficulty", "Difficulty"), ("by_domain", "Domain"), ("by_force_field", "Force field")):
        L.append(f"**{title}:** " + "; ".join(f"{k} {v['rate']:.3f} ({v['tasks']} tasks)" for k, v in a[key].items()))
    L += ["", "| Task | Success rate |", "|---|---|"] + [f"| {k} | {v:.3f} |" for k, v in a["per_task"].items()]
    L += ["", f"**Failure categories** (first failing property, or NO_OUTPUT / TC_ONLY / INCOMPLETE): "
          f"{a['failure_categories'] or 'none'}",
          f"**Tier reached:** {a['tier_reached']}",
          f"**Failure-mode incidence** (fraction of runs): {a['failure_mode_incidence'] or 'none'}"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------
def main(argv=None):
    from eval.systems import make_system
    ap = argparse.ArgumentParser(prog="python -m eval.harness", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", required=True, help="oracle | corrupt-file | corrupt-spec | baseline | agent | agent-nofeedback | agent-tiers01")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--tasks", nargs="*", help="subset of task IDs (within the split)")
    ap.add_argument("--out", help="output directory (default runs/eval/<system>_<split>_<timestamp>)")
    ap.add_argument("--mock", help="'perfect' (baseline, agent) replaces the model with the hidden spec; agent also: fix | stubborn | runaway (agents/mock.py)")
    ap.add_argument("--write-doc", help="also write the summary to this Markdown file (e.g. docs/BASELINE_RESULTS.md)")
    a = ap.parse_args(argv)
    tasks = load_tasks(a.split, a.tasks)
    system = make_system(a.system, mock=a.mock)
    out = a.out or os.path.join(ROOT, "runs", "eval",
                                f"{system.meta['name']}_{a.split}_{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}")
    res = evaluate(system, tasks, a.repeats, out)
    print(summary_md(res))
    print("results:", os.path.join(out, "results.json"))
    if a.write_doc:
        with open(a.write_doc, "w") as fh:
            fh.write(summary_md(res) + f"\nFull results: `{os.path.relpath(out, ROOT)}/results.json` (gitignored; "
                     "regenerate with the command in docs/BASELINE.md).\n")


if __name__ == "__main__":
    main()

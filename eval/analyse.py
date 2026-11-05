"""Failure analysis of one harness run (plan Day 25) -> Markdown for docs/BASELINE_RESULTS.md and later runs.

  python -m eval.analyse runs/eval/<run>/ [--write-doc docs/BASELINE_RESULTS.md]

For every failed run: the category, the failing checks with their messages, and — when the system
recorded the builder spec it used (trace.builder_spec) — a field-by-field difference from the task's
hidden spec. Monomers are compared by chemistry, not by label, and the PCE convenience form is expanded
first, so "A"/"E" against "S"/"A" with the same units is no difference.

Each failure gets a SUGGESTED gap type (plan Day 25, step 2), for a human to confirm or change:
  formatting   no usable answer: unparseable, truncated, inconsistent spec
  knowledge    the wrong thing was named: builder, force field, model, monomer chemistry, a model the
               force field does not cover
  reasoning    the right things, wrong numbers: unit counts, EO units, supercell, sequence, chains
  pipeline     the spec was right but the file failed validation: a builder or validator problem
  validator    a check was NOT_CALIBRATED / NOT_EVALUATED (INCOMPLETE)
  infrastructure  API error
Hidden specs are read through eval.harness.load_tasks, which keeps the test split closed until its opening date (METRICS §6).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builders.pce import architecture_from_params  # noqa: E402
from eval.harness import load_tasks  # noqa: E402

PCE_DEFAULTS = {"sequence": "random", "end_groups": ["CH3", "CH3"], "n_chains": 1, "counterion": "Ca2+"}
COMPOSITE_DEFAULTS = {"height": 3.0, "orientation": "flat"}
KNOWLEDGE_FIELDS = {"builder", "force_field", "model", "surface.model", "pce.units:chemistry", "units:chemistry",
                    "pce.counterion", "counterion"}


# ---------------------------------------------------------------------------------------------
def _chem(u: dict) -> tuple:
    k = u["kind"]
    if k == "acid":
        return (k, bool(u.get("alpha_methyl")), None, None, None, int(bool(u.get("deprotonated"))))
    if k == "diacid":
        return (k, None, None, None, None, int(u.get("deprotonated") or 0))
    return (k, bool(u.get("alpha_methyl")), int(u.get("eo_units") or 0), u.get("end") or "OH",
            int(u.get("spacer") or 1) if k == "ether_peg" else None, None)


def _no_eo(units: Counter) -> Counter:
    out = Counter()
    for c, n in units.items():
        out[c[:2] + (None,) + c[3:]] += n
    return out


def chem_name(c: tuple) -> str:
    k, am, eo, end, spacer, dep = c
    if k == "acid":
        return f"{'methacrylic' if am else 'acrylic'} acid{' (COO-)' if dep else ' (COOH)'}"
    if k == "diacid":
        return f"maleic ({dep} COO-)"
    if k == "ester_peg":
        return f"{'methacrylate' if am else 'acrylate'} ester PEG EO{eo} {end}"
    anchor = {(False, 1): "APEG", (True, 1): "HPEG", (True, 2): "TPEG", (False, 2): "VPEG"}.get((am, spacer), f"ether s{spacer}")
    return f"{anchor} EO{eo} {end}"


def _pce(p: dict) -> dict:
    if "monomers" not in p:
        p = architecture_from_params(dict(p))
    chem = {lab: _chem(u) for lab, u in p["monomers"].items()}
    units = Counter()
    for lab, n in p["composition"].items():
        units[chem[lab]] += int(n)
    seq = p.get("sequence", PCE_DEFAULTS["sequence"])
    if isinstance(seq, list):
        seq = [chem_name(chem[lab]) for lab in seq]
    return {"units": units, "sequence": seq, "end_groups": list(p.get("end_groups", PCE_DEFAULTS["end_groups"])),
            "n_chains": int(p.get("n_chains", 1)), "counterion": p.get("counterion", PCE_DEFAULTS["counterion"])}


def canonical(spec: dict) -> dict:
    b = spec["builder"]
    out = {"builder": b, "force_field": spec["force_field"]}
    if b == "minerals":
        out.update(model=spec["model"], supercell=list(spec["supercell"]))
    elif b == "pce":
        out.update(_pce(spec))
    else:
        sc = spec["surface"]["supercell"]
        out.update({"surface.model": spec["surface"]["model"], "surface.supercell": sc if sc == "auto" else list(sc),
                    "height": float(spec.get("height", COMPOSITE_DEFAULTS["height"])),
                    "orientation": spec.get("orientation", COMPOSITE_DEFAULTS["orientation"])})
        out.update({f"pce.{k}": v for k, v in _pce(spec["pce"]).items()})
    return out


def spec_diff(got: dict, expected: dict) -> list:
    """[(field, text)] where the system's builder spec differs from the hidden spec."""
    if got["builder"] != expected["builder"]:
        return [("builder", f"builder {got['builder']!r}, expected {expected['builder']!r}")]
    g, e = canonical(got), canonical(expected)
    out = []
    for k in e:
        if k.endswith("units"):
            if g[k] == e[k]:
                continue
            if set(g[k]) == set(e[k]):
                field = k + ":counts"
            elif _no_eo(g[k]) == _no_eo(e[k]):
                field = k + ":eo_units"          # same units, only side-chain lengths differ: a numbers error
            else:
                field = k + ":chemistry"
            missing = [f"{chem_name(c)} ×{n}" for c, n in (e[k] - g[k]).items()]
            extra = [f"{chem_name(c)} ×{n}" for c, n in (g[k] - e[k]).items()]
            out.append((field, f"{k}: missing {', '.join(missing) or '—'}; unexpected {', '.join(extra) or '—'}"))
        elif g.get(k) != e[k]:
            if k == "surface.supercell" and "auto" in (g.get(k), e[k]):
                out.append((k, f"{k}: {g.get(k)} vs expected {e[k]} (\"auto\" is resolved at build time: may be equal)"))
            else:
                out.append((k, f"{k}: {g.get(k)}, expected {e[k]}"))
    return out


def suggest_gap(row: dict, diffs) -> str:
    cat, err = row["category"], (row.get("error") or "")
    if cat == "NO_OUTPUT":
        if err.startswith("API"):
            return "infrastructure"
        if row.get("builder_refused"):
            return "knowledge" if any(s in err for s in ("not available", "unknown", "defective", "not a slab",
                                                         "no such", "not covered")) else "reasoning"
        return "formatting"
    if cat == "INCOMPLETE":
        return "validator"
    if diffs:
        return "knowledge" if any(f in KNOWLEDGE_FIELDS for f, _ in diffs) else "reasoning"
    if diffs is None:
        return "unknown (no builder spec in the trace)"
    return "pipeline" if cat != "TC_ONLY" else "reasoning (spec equal; TC.2 still failed: investigate)"


# ---------------------------------------------------------------------------------------------
def analyse(run_dir: str) -> dict:
    res = json.load(open(os.path.join(run_dir, "results.json")))
    sp = json.load(open(os.path.join(ROOT, "eval", "split.json")))
    split = "dev" if set(res["tasks"]) <= set(sp["dev"]) else "test"
    hidden = {t["id"]: t["hidden_spec"] for t in load_tasks(split, res["tasks"])}
    failures = []
    for row in res["runs"]:
        if row["success"]:
            continue
        tr_path = os.path.join(run_dir, "runs", row["task"], f"r{row['repeat']}", "trace.json")
        trace = (json.load(open(tr_path)).get("trace") or {}) if os.path.exists(tr_path) else {}
        spec = trace.get("builder_spec")
        diffs = None
        if spec:
            try:
                diffs = spec_diff(spec, hidden[row["task"]])
            except (KeyError, TypeError, ValueError) as e:
                diffs = [("spec", f"could not compare: {type(e).__name__}: {e}")]
        failures.append({"task": row["task"], "repeat": row["repeat"], "category": row["category"],
                         "domain": row["domain"], "error": row.get("error"),
                         "checks": row.get("failing_details") or [{"property": p, "tier": "", "message": ""}
                                                                 for p in row.get("failing", [])],
                         "diffs": [t for _, t in diffs] if diffs else ([] if diffs is not None else None),
                         "diff_fields": [f for f, _ in diffs] if diffs else [],
                         "gap": suggest_gap(row, diffs)})
    return {"run_dir": run_dir, "split": split, "result": res, "failures": failures}


def report(an: dict) -> str:
    res, fails = an["result"], an["failures"]
    a, fc = res["aggregate"], res["fixed_conditions"]
    n = len(res["runs"])
    cats = Counter(f["category"] for f in fails)
    gaps = Counter(f["gap"] for f in fails)
    sysm = fc.get("system", {})
    L = [f"# Failure analysis: {sysm.get('name', 'system')} on the {an['split']} split\n",
         f"Run: `{_where(an['run_dir'])}` · {fc['date']} · git {fc['git_commit'][:7]} · "
         f"model {sysm.get('model') or '—'} · {len(res['tasks'])} tasks × {res['repeats']} repeats = {n} runs. "
         "Generated by `python -m eval.analyse` (plan Day 25); the gap types are suggestions to confirm by hand.\n",
         "## Headline\n",
         f"- **Success rate:** {a['system_success_rate']} (spread across repeats {a['spread_across_repeats']})",
         f"- **Validity rate** (Tier 0–3 PASS, any system): {a['validity_rate']}",
         f"- **Highest tier reached** (runs): {a['tier_reached']}",
         f"- **Failure categories:** {dict(cats.most_common()) or 'none'}",
         f"- **No output:** {a['no_output']} · builder refusals: {a['builder_refusals']}",
         f"- **Cost:** ${a['total_cost_usd']} in total, ${a['cost_per_task_usd']} per task" if a.get("total_cost_usd") is not None else "",
         ""]
    if fails:
        top_cat, k = cats.most_common(1)[0]
        top_gap, kg = gaps.most_common(1)[0]
        L += [f"**Largest failure category:** `{top_cat}` ({k} of {len(fails)} failures). "
              f"**Most frequent suggested gap:** {top_gap} ({kg}).\n",
              "## Suggested gap types\n", "| Gap | Failures |", "|---|---|"]
        L += [f"| {g} | {c} |" for g, c in gaps.most_common()]
        L += ["", "## Failures\n", "| Task | Rep | Category | What failed | Spec vs hidden spec | Gap (suggested) |",
              "|---|---|---|---|---|---|"]
        for f in sorted(fails, key=lambda f: (f["task"], f["repeat"])):
            what = f["error"] or "; ".join(f"{c['property']}: {c['message']}".rstrip(": ") for c in f["checks"][:3])
            diff = "not recorded" if f["diffs"] is None else ("; ".join(f["diffs"]) or "equal")
            L.append(f"| {f['task']} | {f['repeat']} | {f['category']} | {_cell(what)} | {_cell(diff)} | {f['gap']} |")
    else:
        L.append("No failures.")
    L += ["", "## Per task\n", "| Task | Success (of repeats) |", "|---|---|"]
    L += [f"| {t} | {v} |" for t, v in sorted(a["per_task"].items())]
    return "\n".join(l for l in L if l is not None) + "\n"


def _where(path: str) -> str:
    p = os.path.abspath(path)
    return os.path.relpath(p, ROOT) if p.startswith(ROOT + os.sep) else p


def _cell(s: str, n: int = 400) -> str:
    s = (s or "").replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= n else s[:n - 1] + "…"


def main():
    ap = argparse.ArgumentParser(prog="python -m eval.analyse")
    ap.add_argument("run_dir")
    ap.add_argument("--write-doc", help="also write the report to this Markdown file")
    ap.add_argument("--json", action="store_true", help="print the failure list as JSON")
    args = ap.parse_args()
    an = analyse(args.run_dir)
    if args.json:
        print(json.dumps(an["failures"], indent=1, default=str))
    text = report(an)
    with open(os.path.join(args.run_dir, "analysis.md"), "w") as fh:
        fh.write(text)
    if args.write_doc:
        with open(args.write_doc, "w") as fh:
            fh.write(text)
    if not args.json:
        print(text)


if __name__ == "__main__":
    main()

"""Prove the validator works (plan Day 15; SPEC §7.12 validator quality).

Runs the validator over every positive control (references, reduced fixtures), the natural
negatives (raw msi2lmp fixtures) and every corrupted variant in data/corrupted/manifest.json.
For each file it also records what LAMMPS *alone* does with it (Tier 3a + 3b run directly,
even when Tier 0 fails), to quantify the validator's added value.

Outputs:
  runs/validator_matrix/results.json   full ValidationResult per file (gitignored)
  docs/validator_matrix.csv            one row per file
  docs/VALIDATOR_RESULTS.md            the tables for the write-up
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from validator import __version__, validate  # noqa: E402
from validator.config import declared  # noqa: E402
from validator.registry import config_for, load_sidecar  # noqa: E402
from validator.tier3 import NOCOEFF_ARTEFACT_RE, run_lammps  # noqa: E402

POSITIVE = ["data/reference/REF-01.data", "data/reference/REF-02.data", "data/reference/REF-03.data",
            "data/reference/REF-04.data", "data/fixtures/FIX-T11.data", "data/fixtures/FIX-T14.data"]
POSITIVE += ["data/reference/REF-05.data", "data/reference/REF-06.data", "data/reference/REF-07.data",
             "data/reference/REF-08.data"] + [f"data/reference/eval/t{i:02d}.data" for i in range(1, 15)] + ["data/reference/pce_builder/PB-01_pcff.data", "data/reference/pce_builder/PB-01_cvff.data", "data/reference/pce_builder/PB-02_pcff.data", "data/reference/pce_builder/PB-02_cvff.data", "data/reference/composite/CP-01_pcff.data", "data/reference/composite/CP-01_cvff.data", "data/reference/minerals/c3s_unit_cell_minimized_pcff.data", "data/reference/minerals/c3s_unit_cell_minimized_cvff.data", "data/reference/minerals/c3a_unit_cell_pcff.data", "data/reference/minerals/c3a_unit_cell_cvff.data", "data/reference/minerals/ettr_unit_cell_pcff.data", "data/reference/minerals/monosulfate_cell_221_pcff.data"]
# Real tool output, not synthetic mutations: msi2lmp (tilt not reduced) and LAMMPS 'replicate ... bond/periodic'
# (scripts/build_references.py crosscheck). Each is judged on its own merits: TC.2 against its parent says
# whether it is actually wrong; the validator must FAIL exactly the wrong ones.
NATURAL_NEGATIVE = ["data/fixtures/FIX-T11-raw.data", "data/fixtures/FIX-T14-raw.data"] + \
    sorted(os.path.relpath(f, ROOT) for f in __import__("glob").glob(os.path.join(ROOT, "data/converted/lammps_replicate/*.data")))


def lammps_alone(path, cfg, res):
    """LAMMPS's own verdict, independent of the validator's Tier 0 gate."""
    s = (res.lammps or {}).get("structure")
    f = (res.lammps or {}).get("full")
    if s is None:
        s = run_lammps(path, cfg, "structure")
        f = run_lammps(path, cfg, "full")
    allow = set(declared(cfg).get("tier3", {}).get("warning_allow_list") or [])

    def extra_warnings(r):
        out = []
        for w in (r or {}).get("warnings", []):
            w2 = w.split(" (src/")[0]
            if NOCOEFF_ARTEFACT_RE.match(w2) or w2.replace("WARNING: ", "", 1) in allow:
                continue
            out.append(w2)
        return out

    def cat():
        if s is None:
            return "not run"
        if s["outcome"] == "CRASH":
            return "Crash"
        if s["outcome"] in ("ERROR", "TIMEOUT"):
            return "Loud"
        if f is not None:
            if f["outcome"] == "CRASH":
                return "Crash@run"
            if f["outcome"] in ("ERROR", "TIMEOUT"):
                return "Loud@run"
            th = f.get("thermo") or {}
            if th.get("nonfinite"):
                return "Non-finite@run"
        if extra_warnings(s) or extra_warnings(f):
            return "Warn"
        return "Silent"
    return {"category": cat(), "structure_outcome": s and s["outcome"], "full_outcome": f and f["outcome"],
            "errors": ((s or {}).get("errors", []) + (f or {}).get("errors", []))[:3],
            "warnings": (extra_warnings(s) + extra_warnings(f))[:3]}


def classify(res, expected):
    fails = [c.property for c in res.checks if c.verdict == "FAIL" and c.tier in (0, 1, 2, 3)]
    tc_fail = [c.property for c in res.checks if c.verdict == "FAIL" and c.tier == "TC"]
    ncal = [c.property for c in res.checks if c.verdict == "NOT_CALIBRATED"]
    first_tier = min((c.tier for c in res.checks if c.verdict == "FAIL" and c.tier in (0, 1, 2, 3)), default=None)
    hit = sorted(set(expected) & set(fails + tc_fail))
    own = [c.property for c in res.checks if c.verdict == "FAIL" and c.tier in (0, 1, 2)]
    if own:
        status = "CAUGHT"
    elif fails:
        status = "CAUGHT_T3_ONLY"
    elif tc_fail:
        status = "CAUGHT_TC_ONLY"
    elif res.verdict == "INCOMPLETE":
        status = "FLAGGED_INCOMPLETE"
    else:
        status = "MISSED"
    return {"verdict": res.verdict, "status": status, "failing": fails, "own_failing": own, "tc_failing": tc_fail,
            "not_calibrated": ncal, "first_failing_tier": first_tier, "expected_hit": hit,
            "expected_met": bool(hit)}


def git_rev():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip() or "uncommitted"
    except OSError:
        return "unknown"


def main():
    t0 = time.time()
    rows, full = [], []
    with open(os.path.join(ROOT, "data/corrupted/manifest.json")) as fh:
        manifest = json.load(fh)["files"]
    jobs = [("positive", p, None) for p in POSITIVE] + [("natural_negative", p, None) for p in NATURAL_NEGATIVE] \
        + [("corrupted", m["file"], m) for m in manifest]
    for kind, rel, m in jobs:
        path = os.path.join(ROOT, rel)
        meta = load_sidecar(path)
        cfg = config_for(path, meta)
        ref = os.path.join(ROOT, meta["parent_file"]) if meta.get("parent_file") and kind != "positive" else None
        res = validate(path, cfg, reference=ref)
        expected = (m or {}).get("expected_failing_properties", [])
        c = classify(res, expected)
        lam = lammps_alone(path, cfg, res)
        row = {"kind": kind, "id": meta.get("id"), "parent": (meta or {}).get("parent_id", ""),
               "fm": (meta or {}).get("failure_mode", ""), "variant": (meta or {}).get("variant", ""),
               "expected": ";".join(expected), "expected_tier": (m or {}).get("expected_tier", ""),
               "verdict": c["verdict"], "status": c["status"], "tier_reached": res.tier_reached,
               "first_failing_tier": c["first_failing_tier"], "failing": ";".join(c["failing"]), "own_failing": ";".join(c["own_failing"]),
               "tc_failing": ";".join(c["tc_failing"]), "not_calibrated": ";".join(c["not_calibrated"]),
               "expected_met": c["expected_met"], "lammps_alone": lam["category"],
               "lammps_3a": lam["structure_outcome"], "lammps_3b": lam["full_outcome"],
               "lammps_errors": " | ".join(lam["errors"]), "lammps_warnings": " | ".join(lam["warnings"]),
               "first_message": next((x.message for x in res.checks if x.verdict == "FAIL"), "")[:160]}
        rows.append(row)
        full.append(res.to_dict())
    os.makedirs(os.path.join(ROOT, "runs/validator_matrix"), exist_ok=True)
    with open(os.path.join(ROOT, "runs/validator_matrix/results.json"), "w") as fh:
        json.dump(full, fh, indent=1, default=str)
    with open(os.path.join(ROOT, "docs/validator_matrix.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    write_report(rows, time.time() - t0)
    pos = [r for r in rows if r["kind"] == "positive"]
    cor = [r for r in rows if r["kind"] == "corrupted"]
    print(f"positive controls: {sum(r['verdict'] == 'PASS' for r in pos)}/{len(pos)} PASS")
    print(f"corrupted: {Counter(r['status'] for r in cor)}; expected property hit: "
          f"{sum(r['expected_met'] for r in cor)}/{len(cor)}")
    print(f"LAMMPS alone on corrupted: {Counter(r['lammps_alone'] for r in cor)}")
    print(f"elapsed {time.time() - t0:.1f}s")


def write_report(rows, elapsed):
    pos = [r for r in rows if r["kind"] == "positive"]
    neg = [r for r in rows if r["kind"] == "natural_negative"]
    cor = [r for r in rows if r["kind"] == "corrupted"]
    groups = defaultdict(list)
    for r in cor:
        groups[(r["fm"], r["variant"])].append(r)
    L = []
    L.append("# Validator results (plan Day 15)\n")
    L.append(f"Generated by `scripts/run_matrix.py` on {_dt.date.today().isoformat()} · validator {__version__} · "
             f"git {git_rev()} · LAMMPS `lmp_serial` 22 Jul 2025 – Update 6 (serial) · {len(rows)} files in "
             f"{elapsed:.0f} s. Per-file rows: `docs/validator_matrix.csv`; full results: "
             f"`runs/validator_matrix/results.json` (regenerate with the command above).\n")
    L.append("**Status vocabulary.** CAUGHT = at least one of the validator's own checks (Tiers 0–2) FAILs. "
             "CAUGHT_T3_ONLY = only a Tier 3 property (LAMMPS diagnostics: P3.1–P3.4) FAILs — PROPERTIES §8.8 says "
             "the validator must not rely on these. CAUGHT_TC_ONLY = Tiers 0–3 "
             "raise no FAIL, but the TC.2 comparison with the parent reference does. FLAGGED_INCOMPLETE = no FAIL, "
             "but some property is NOT_CALIBRATED / NOT_EVALUATED, so the file is not certified either. "
             "MISSED = the file would be certified PASS. *Expected hit* = one of the properties named in the "
             "operator's manifest entry FAILs. *LAMMPS alone* = what `read_data … nocoeff` plus the full "
             "`run 0` report by themselves: Silent · Warn · Loud · Loud@run · Crash · Non-finite@run.\n")
    # summary
    st = Counter(r["status"] for r in cor)
    la = Counter(r["lammps_alone"] for r in cor)
    L.append("## Summary\n")
    L.append("| Measure | Result |\n|---|---|")
    L.append(f"| Positive controls (references + reduced fixtures) passing all tiers | "
             f"**{sum(r['verdict'] == 'PASS' for r in pos)} / {len(pos)}** (false-alarm rate {sum(r['verdict'] != 'PASS' for r in pos)}/{len(pos)}) |")
    L.append(f"| Corrupted files | {len(cor)} ({len(groups)} operator variants, "
             f"{len({r['fm'] for r in cor})} failure modes, {len({r['parent'] for r in cor})} parents) |")
    L.append(f"| CAUGHT by the validator's own checks (Tiers 0–2) | **{st['CAUGHT']} / {len(cor)}** |")
    L.append(f"| CAUGHT only at Tier 3 (LAMMPS diagnostics) | {st['CAUGHT_T3_ONLY']} |")
    L.append(f"| CAUGHT only by TC.2 (reference comparison) | {st['CAUGHT_TC_ONLY']} |")
    L.append(f"| FLAGGED_INCOMPLETE (not certified, no FAIL) | {st['FLAGGED_INCOMPLETE']} |")
    L.append(f"| MISSED (would be certified) | **{st['MISSED']}** |")
    L.append(f"| Expected property among the failures | {sum(r['expected_met'] for r in cor)} / {len(cor)} |")
    L.append(f"| LAMMPS alone: Silent / Warn | {la['Silent']} / {la['Warn']} |")
    L.append(f"| LAMMPS alone: Loud / Loud@run / Crash / Non-finite@run | {la['Loud']} / {la['Loud@run']} / "
             f"{la['Crash'] + la['Crash@run']} / {la['Non-finite@run']} |")
    silent_caught = sum(1 for r in cor if r["lammps_alone"] in ("Silent", "Warn") and r["status"] == "CAUGHT")
    t02 = Counter(r["first_failing_tier"] for r in cor if r["status"] == "CAUGHT")
    silent_all = sum(1 for r in cor if r["lammps_alone"] in ("Silent", "Warn"))
    L.append(f"| Corruptions LAMMPS misses (Silent/Warn) that Tiers 0–2 catch | **{silent_caught} / {silent_all}** |")
    L.append(f"| First failing tier of CAUGHT files (T0 / T1 / T2) | {t02.get(0, 0)} / {t02.get(1, 0)} / {t02.get(2, 0)} |\n")
    # positives
    L.append("## Positive controls (must PASS)\n")
    L.append("REF-01..04: PCE candidates (EMC). FIX-T11/T14: synthetic fixtures. REF-05..08 and t01–t14: tobermorite "
             "published-model references and eval-set reference outputs (primary system class from v0.5).\n")
    L.append("| File | Verdict | Tier reached | Notes |\n|---|---|---|---|")
    for r in pos:
        L.append(f"| {r['id']} | {r['verdict']} | {r['tier_reached']} | {r['first_message'] or '—'} |")
    L.append("\n## Natural negatives (real converter output)\n")
    L.append("TC.2 (comparison with the parent built by the reference pipeline) says whether the tool output is "
             "actually wrong; the validator's verdict should agree.\n")
    L.append("| File | Verdict | Failing | TC.2 vs parent | LAMMPS alone | Message |\n|---|---|---|---|---|---|")
    for r in neg:
        tc = "differs" if r["tc_failing"] else ("identical" if r["parent"] else "—")
        L.append(f"| {r['id']} | {r['verdict']} | {r['failing'] or '—'} | {tc} | {r['lammps_alone']} | {r['first_message'] or '—'} |")
    # per operator
    L.append("\n## Mutation × detection (aggregated over parents)\n")
    L.append("Columns: n = files (one per applicable parent); caught = Tiers 0–3 FAIL; exp = expected property failed; "
             "tier = first failing tier(s); failing = properties that FAILed (union); LAMMPS alone = outcomes.\n")
    L.append("| FM | Variant | n | Caught (T0–2) | T3-only | TC-only | Exp. hit | Expected | First tier | Failing (union) | LAMMPS alone |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for (fm, var), rs in sorted(groups.items()):
        n = len(rs)
        caught = sum(r["status"] == "CAUGHT" for r in rs)
        tco = sum(r["status"] == "CAUGHT_TC_ONLY" for r in rs)
        t3o = sum(r["status"] == "CAUGHT_T3_ONLY" for r in rs)
        exp = sum(r["expected_met"] for r in rs)
        tiers = sorted({str(r["first_failing_tier"]) for r in rs if r["first_failing_tier"] is not None})
        failing = sorted({p for r in rs for p in r["failing"].split(";") if p})
        lam = Counter(r["lammps_alone"] for r in rs)
        L.append(f"| {fm} | {var} | {n} | {caught}/{n} | {t3o} | {tco} | {exp}/{n} | {rs[0]['expected']} | "
                 f"{','.join(tiers) or '—'} | {', '.join(failing) or '—'} | "
                 f"{', '.join(f'{k} {v}' for k, v in lam.most_common())} |")
    # gaps
    gaps = [r for r in cor if r["status"] != "CAUGHT"]
    L.append("\n## Not caught by the validator's own checks (Tiers 0–2)\n")
    if not gaps:
        L.append("None.\n")
    else:
        L.append("| File | Status | Tier 3 failing | TC.2 | NOT_CALIBRATED | LAMMPS alone |\n|---|---|---|---|---|---|")
        for r in gaps:
            L.append(f"| {r['id']} | {r['status']} | {r['failing'] or '—'} | {r['tc_failing'] or '—'} | "
                     f"{r['not_calibrated'] or '—'} | {r['lammps_alone']} |")
    with open(os.path.join(ROOT, "docs/VALIDATOR_RESULTS.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()

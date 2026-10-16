"""Tier 3 — LAMMPS acceptance under the declared configuration (PROPERTIES §8.1, P3.1–P3.4).

3a structure-only: `read_data <file> nocoeff`.  3b full: the declared force-field block + `run 0`.
Absence of a LAMMPS error or warning is never evidence of correctness (§8.8); these checks only
add LAMMPS's own verdict on top of Tiers 0-2.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Optional

from .backends import RunResult, make_backend
from .config import declared, resolve
from .parser import ParsedFile
from .result import FAIL, NOT_EVALUATED, PASS, CheckResult

CLEAN, ERROR, CRASH, TIMEOUT, LAUNCH = "CLEAN", "ERROR", "CRASH", "TIMEOUT", "LAUNCH_FAILURE"
# 'read_data ... nocoeff' installs 'zero' styles, so every style-commented Coeff section is compared
# against 'zero' and warns (SRC read_data.cpp:811-875). These come from the Tier 3a mode, not from
# the DATA FILE; style comments are checked independently by P1.11.
NOCOEFF_ARTEFACT_RE = re.compile(r"^WARNING: (Pair|Bond|Angle|Dihedral|Improper) style \S+ in data file differs "
                                 r"from currently defined (pair|bond|angle|dihedral|improper) style zero$")
COUNT_RE = re.compile(r"^\s+(\d+)\s+(atoms|bonds|angles|dihedrals|impropers|velocities)\s*$")
# Error texts that point at the configuration rather than the DATA FILE (§8.1 attribution rule).
CONFIG_ERROR_PATTERNS = [
    r"Unrecognized (pair|bond|angle|dihedral|improper|kspace|atom) style", r"Unknown (pair|bond|angle) style",
    r"Package .* not installed", r"Cannot open (input|include) (script|file)", r"Illegal variable",
    r"Substitution for illegal variable", r"Invalid use of library", r"Unknown command",
]


def _lines(text: str, prefix: str) -> List[str]:
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(prefix):
            out.append(s)
    return out


def _dedupe(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def classify(rr: RunResult, errors: List[str]) -> str:
    if rr.launch_error:
        return LAUNCH
    if rr.timed_out:
        return TIMEOUT
    if rr.signal is not None:
        return CRASH
    if rr.returncode != 0:
        return ERROR if errors else CRASH
    return ERROR if errors else CLEAN


def summarise_run(rr: RunResult) -> Dict[str, Any]:
    text = rr.stdout + "\n" + rr.log
    errors = _dedupe(_lines(text, "ERROR"))
    warnings = _dedupe(_lines(text, "WARNING"))
    counts = {}
    for ln in (rr.log or rr.stdout).splitlines():
        mm = COUNT_RE.match(ln)
        if mm:
            counts[mm.group(2)] = int(mm.group(1))
    thermo = _parse_thermo(rr.log or rr.stdout)
    outcome = classify(rr, errors)
    return {"outcome": outcome, "returncode": rr.returncode, "signal": rr.signal, "timed_out": rr.timed_out,
            "launch_error": rr.launch_error, "errors": errors, "warnings": warnings, "counts": counts,
            "thermo": thermo, "elapsed_s": round(rr.elapsed_s, 3), "backend": rr.backend,
            "stdout_tail": "\n".join(rr.stdout.splitlines()[-25:]), "stderr_tail": rr.stderr[-2000:]}


def _parse_thermo(text: str) -> Optional[Dict[str, Any]]:
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        toks = ln.split()
        if toks and toks[0] == "Step" and i + 1 < len(lines):
            vals = lines[i + 1].split()
            if len(vals) == len(toks):
                out = {}
                for k, v in zip(toks, vals):
                    try:
                        out[k] = float(v)
                    except ValueError:
                        out[k] = v
                nonfinite = [k for k, v in out.items() if not isinstance(v, float) or not math.isfinite(v)]
                return {"values": out, "nonfinite": nonfinite}
    return None


def render(template_path: str, mapping: Dict[str, str]) -> str:
    with open(template_path) as fh:
        text = fh.read()
    for k, v in mapping.items():
        text = text.replace("{" + k + "}", v)
    return text


def _mapping(cfg) -> Dict[str, str]:
    d = declared(cfg)
    b = d.get("boundary", ["p", "p", "p"])
    return {"units": str(d.get("units")), "atom_style": str(d.get("atom_style")),
            "boundary": " ".join(b) if isinstance(b, list) else str(b),
            "datafile": "data.lmp", "coeff_file": "coeffs.inc"}


def run_lammps(path: str, cfg, mode: str) -> Optional[Dict[str, Any]]:
    """Run one Tier 3 mode ('structure' or 'full'); None if the mode is not configured."""
    d = declared(cfg)
    t3 = d.get("tier3", {})
    tmpl = t3.get("structure_template" if mode == "structure" else "full_template")
    if not tmpl or not d.get("units") or not d.get("atom_style"):
        return None
    files = {"data.lmp": str(path)}
    if mode == "full" and "{coeff_file}" in open(resolve(tmpl)).read():
        cf = d.get("coeff_file")
        if not cf:
            return None
        files["coeffs.inc"] = resolve(cf)
    text = render(resolve(tmpl), _mapping(cfg))
    backend = make_backend(cfg)
    timeout = t3.get("timeout_s") or cfg.get("lammps", {}).get("timeout_s", 120)
    rr = backend.run(text, files, timeout)
    s = summarise_run(rr)
    s["mode"] = mode
    s["template"] = tmpl
    return s


def _attribute(errors: List[str]) -> str:
    for e in errors:
        for pat in CONFIG_ERROR_PATTERNS:
            if re.search(pat, e):
                return "CONFIGURATION"
    return "DATA_FILE"


def run_tier3(pf: ParsedFile, cfg, path: str) -> (List[CheckResult], Dict[str, Any]):
    d = declared(cfg)
    lam = {"ran": False, "returncode": None, "errors": [], "structure": None, "full": None}
    checks: List[CheckResult] = []
    s = run_lammps(path, cfg, "structure")
    full_enabled = cfg.get("validator", {}).get("run_tier3_full", True)
    f = run_lammps(path, cfg, "full") if full_enabled else None
    lam.update({"ran": s is not None, "structure": s, "full": f})
    if s is not None:
        lam["returncode"] = s["returncode"]
        lam["errors"] = s["errors"] + ([e for e in f["errors"] if e not in s["errors"]] if f else [])
        if s["outcome"] == LAUNCH:
            msg = f"LAMMPS could not be launched: {s['launch_error']} (configuration, not a DATA FILE verdict)"
            return [CheckResult(n, p, 3, NOT_EVALUATED, msg) for n, p in
                    (("lammps_structure_acceptance", "P3.1"), ("lammps_full_acceptance", "P3.2"),
                     ("lammps_warning_policy", "P3.3"), ("lammps_process_outcome", "P3.4"))], lam

    # P3.1 structure-only acceptance --------------------------------------------------------
    if s is None:
        checks.append(CheckResult("lammps_structure_acceptance", "P3.1", 3, NOT_EVALUATED,
                                  "structure-only template / units / atom_style not declared (OD-C1, OD-C3, OD-F)"))
    else:
        probs = []
        if s["outcome"] != CLEAN:
            probs.append(f"outcome {s['outcome']}" + (f": {s['errors'][0]}" if s["errors"] else
                                                      f" (exit {s['returncode']}, signal {s['signal']})"))
        for key in ("atoms", "bonds", "angles", "dihedrals", "impropers"):
            want = pf.header_int(key, 0) or 0
            got = s["counts"].get(key)
            if s["outcome"] == CLEAN and want and got != want:
                probs.append(f"LAMMPS read {got} {key}, header declares {want}")
        checks.append(CheckResult("lammps_structure_acceptance", "P3.1", 3, FAIL if probs else PASS,
                                  "; ".join(probs), {"outcome": s["outcome"], "counts": s["counts"],
                                                     "errors": s["errors"][:5]}))
    # P3.2 full force-field acceptance ------------------------------------------------------
    if f is None:
        checks.append(CheckResult("lammps_full_acceptance", "P3.2", 3, NOT_EVALUATED,
                                  "no full force-field configuration declared for this file (OD-C2, S-Q2)"))
    else:
        probs = []
        if f["outcome"] != CLEAN:
            probs.append(f"outcome {f['outcome']}" + (f": {f['errors'][0]}" if f["errors"] else
                                                      f" (exit {f['returncode']}, signal {f['signal']})"))
        th = f.get("thermo")
        if f["outcome"] == CLEAN:
            if th is None:
                probs.append("no thermodynamic output after run 0")
            elif th["nonfinite"]:
                probs.append(f"non-finite thermodynamic values after run 0: "
                             f"{ {k: th['values'][k] for k in th['nonfinite']} }")
        attr = _attribute(f["errors"]) if probs else None
        checks.append(CheckResult("lammps_full_acceptance", "P3.2", 3, FAIL if probs else PASS, "; ".join(probs),
                                  {"outcome": f["outcome"], "thermo": th, "errors": f["errors"][:5],
                                   "attribution": attr}))
    # P3.3 warning policy -------------------------------------------------------------------
    allow = set(d.get("tier3", {}).get("warning_allow_list") or [])
    runs = [r for r in (s, f) if r is not None]
    if not runs:
        checks.append(CheckResult("lammps_warning_policy", "P3.3", 3, NOT_EVALUATED, "LAMMPS not run"))
    else:
        def norm(w):
            return re.sub(r"\s*\(src/[^)]*\)\s*$", "", w)
        artefacts = _dedupe([norm(w) for w in (s or {}).get("warnings", []) if NOCOEFF_ARTEFACT_RE.match(norm(w))])
        warns = _dedupe([norm(w) for r in runs for w in r["warnings"]])
        warns = [w for w in warns if not (w in artefacts and not any(norm(x) == w for x in (f or {}).get("warnings", [])))]
        bad = [w for w in warns if w not in allow and w.replace("WARNING: ", "", 1) not in allow]
        checks.append(CheckResult("lammps_warning_policy", "P3.3", 3, FAIL if bad else PASS,
                                  f"{len(bad)} LAMMPS warning(s) not on the allow-list; first: {bad[0]}" if bad else "",
                                  {"warnings": warns, "not_allowed": bad, "tier3a_mode_artefacts": artefacts}))
    # P3.4 process outcome --------------------------------------------------------------------
    if not runs:
        checks.append(CheckResult("lammps_process_outcome", "P3.4", 3, NOT_EVALUATED, "LAMMPS not run"))
    else:
        bad = [f"{r['mode']}: {r['outcome']}" for r in runs if r["outcome"] in (CRASH, TIMEOUT, LAUNCH)]
        checks.append(CheckResult("lammps_process_outcome", "P3.4", 3, FAIL if bad else PASS,
                                  "; ".join(bad) + (" (no ERROR line: undiagnosed rejection)" if bad else ""),
                                  {r["mode"]: {k: r[k] for k in ("outcome", "returncode", "signal", "timed_out",
                                                                 "elapsed_s", "launch_error")} for r in runs}))
    return checks, lam

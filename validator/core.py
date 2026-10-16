"""validate(path, cfg) -> ValidationResult  (plan Day 5 interface; Appendix B schema).

Evaluation order (PROPERTIES §8.2): Tier 0 first, and a Tier 0 failure stops everything; then
Tier 1; Tier 2 checks whose Tier 1 inputs failed are NOT_EVALUATED; Tier 3 runs whenever Tier 0
passes. The TC layer runs only when a reference (or a requested composition) is supplied.
"""
from __future__ import annotations

import time
import traceback
from typing import Any, Dict, Optional

from . import __version__
from .config import declared, load_config, periodic_flags
from .model import build_model
from .parser import parse_file
from .result import NOT_EVALUATED, PASS, CheckResult, ValidationResult
from .tc import run_tc
from .tier0 import run_tier0
from .tier1 import TIER1_CHECKS, run_tier1
from .tier2 import NAMES as T2_NAMES, run_tier2

T1_IDS = [(f.__name__, f"P1.{i + 1}") for i, f in enumerate(TIER1_CHECKS)]
T3_IDS = [("lammps_structure_acceptance", "P3.1"), ("lammps_full_acceptance", "P3.2"),
          ("lammps_warning_policy", "P3.3"), ("lammps_process_outcome", "P3.4")]


def _placeholders(reason: str, tiers=(1, 2, 3)):
    out = []
    if 1 in tiers:
        out += [CheckResult(n.split("_", 2)[-1], p, 1, NOT_EVALUATED, reason) for n, p in T1_IDS]
    if 2 in tiers:
        out += [CheckResult(n, p, 2, NOT_EVALUATED, reason) for p, n in T2_NAMES.items()]
    if 3 in tiers:
        out += [CheckResult(n, p, 3, NOT_EVALUATED, reason) for n, p in T3_IDS]
    return out


def validate(path: str, cfg: Optional[Dict[str, Any]] = None, reference: Optional[str] = None,
             run_tier3: Optional[bool] = None) -> ValidationResult:
    t_start = time.time()
    cfg = cfg if cfg is not None else load_config()
    dec = declared(cfg)
    res = ValidationResult(file=str(path), config_id=f"{dec.get('config_id')}@{dec.get('config_version')}",
                           validator_version=__version__)
    try:
        pf = parse_file(path)
    except OSError as e:
        res.checks.append(CheckResult("readable", "P0.0", 0, "FAIL", f"cannot read file: {e}"))
        res.elapsed_s = time.time() - t_start
        return res
    res.sha256 = pf.sha256

    t0 = run_tier0(pf, cfg)
    res.checks += t0
    if not all(c.verdict == PASS for c in t0):
        res.checks += _placeholders("Tier 0 did not pass: evaluation stopped (PROPERTIES §8.2 item 1)")
        res.elapsed_s = time.time() - t_start
        return res

    try:
        m = build_model(pf, dec["atom_style"], periodic_flags(cfg), dec.get("type_names"))
    except Exception as e:      # should be unreachable after Tier 0; never let a crash be a verdict
        res.checks += _placeholders(f"internal error building model: {type(e).__name__}: {e}", tiers=(1, 2))
        m = None
    if m is not None:
        try:
            t1 = run_tier1(pf, m, cfg)
        except Exception as e:
            t1 = _placeholders(f"internal error in Tier 1: {e!r}\n{traceback.format_exc(limit=3)}", tiers=(1,))
        res.checks += t1
        res.checks += run_tier2(pf, m, cfg, t1)

    do_t3 = cfg.get("validator", {}).get("run_tier3", True) if run_tier3 is None else run_tier3
    if do_t3:
        try:
            from .tier3 import run_tier3 as _t3
            t3, lam = _t3(pf, cfg, str(path))
            res.checks += t3
            res.lammps = lam
        except Exception as e:
            res.checks += _placeholders(f"internal error in Tier 3: {e!r}", tiers=(3,))
    else:
        res.checks += _placeholders("Tier 3 disabled for this call", tiers=(3,))

    if m is not None and (reference or dec.get("expected_composition")):
        res.checks += run_tc(pf, m, cfg, reference)
    res.elapsed_s = time.time() - t_start
    return res

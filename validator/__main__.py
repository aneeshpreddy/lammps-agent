"""Command line: python -m validator FILE [FILE ...] [options]

Exit status: 0 if every file PASSes all tiers, 1 if any FAILs, 2 if any is INCOMPLETE.
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .core import validate
from .registry import config_for, load_sidecar, reference_for


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m validator", description=__doc__)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--declared", help="declared validation configuration (configs/*.yaml); "
                                       "default: the file's sidecar, else config.yaml's default")
    ap.add_argument("--coeff-file", help="coefficient include file for Tier 3b (overrides the sidecar)")
    ap.add_argument("--reference", help="trusted reference DATA FILE for the TC.2 comparison")
    ap.add_argument("--no-tier3", action="store_true", help="skip LAMMPS (Tier 3 becomes NOT_EVALUATED)")
    ap.add_argument("--json", action="store_true", help="print the full ValidationResult JSON")
    a = ap.parse_args(argv)

    verdicts = []
    for f in a.files:
        meta = load_sidecar(f)
        if a.declared:
            over = {"declared": dict((meta or {}).get("overrides", {}))}
            cfg = load_config(declared=a.declared, overrides=over)
        else:
            cfg = config_for(f, meta)
        if a.coeff_file:
            cfg["declared"]["coeff_file"] = a.coeff_file
        ref = a.reference or reference_for(f, meta)
        res = validate(f, cfg, reference=ref, run_tier3=False if a.no_tier3 else None)
        print(res.to_json() if a.json else res.summary())
        verdicts.append(res.verdict)
    if "FAIL" in verdicts:
        return 1
    return 2 if "INCOMPLETE" in verdicts else 0


if __name__ == "__main__":
    sys.exit(main())

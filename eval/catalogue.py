"""Join catalogue for TC.2 chemistry mode (METRICS v1.2, owner 2026-11-05).

In a random-sequence PCE, which bond kinds join neighbouring units depends on the draw. The reference is
one draw, so a correct file with another draw may contain a joining bond kind the reference happens not
to have; likewise the charges of the atoms at the chain ends depend on which units sit there. The
catalogue lists every bond kind and every (atom type, charge) any draw of the task's architecture can
contain: one two-unit chain per ordered pair of monomer labels (X then Y), built with the task's monomers,
end groups and force field. Together they hold every unit-unit join and every end-unit join, and every
atom in its every bonded neighbourhood (bond-increment charges depend only on bonded neighbours). TC.2
accepts a value that is in the reference or in this catalogue (validator/tc.py, `tc_allowed_bond_pairs`,
`tc_allowed_type_charges`).

The harness builds it from the hidden spec at scoring time; the system under test never sees it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import Counter
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builders.pce import ArchitectureSpec, build  # noqa: E402
from validator.model import build_model  # noqa: E402
from validator.parser import parse_file  # noqa: E402
from validator.tc import bond_kinds, type_charges  # noqa: E402


def join_catalogue(hidden_spec: dict) -> dict:
    kinds, charges = _catalogue(json.dumps(hidden_spec, sort_keys=True))
    return {"tc_allowed_bond_pairs": [list(p) for p in kinds], "tc_allowed_type_charges": [list(p) for p in charges]}


@lru_cache(maxsize=None)
def _catalogue(spec_json: str) -> tuple:
    spec = json.loads(spec_json)
    pce = spec["pce"] if spec.get("builder") == "composite" else spec
    arch = ArchitectureSpec.from_json({**pce, "force_field": spec["force_field"], "name": "catalogue"})
    kinds, charges = set(), set()
    with tempfile.TemporaryDirectory() as tmp:
        for x in arch.composition:
            for y in arch.composition:
                name = f"join_{x}_{y}"
                pair = ArchitectureSpec(name=name, monomers=arch.monomers, composition=dict(Counter([x, y])),
                                        sequence=[x, y], end_groups=arch.end_groups, n_chains=1, counterion=None,
                                        force_field=arch.force_field, seed=1, relax=False)
                build(pair, os.path.join(tmp, name))
                pf = parse_file(os.path.join(tmp, name, f"{name}.data"))
                m = build_model(pf, "full", (True, True, True))
                kinds |= bond_kinds(m)
                charges |= type_charges(m)
    return tuple(sorted(kinds)), tuple(sorted(charges))

"""Reference systems for checking the harness itself (plan Day 21), and the system registry.

  oracle        builds each task's hidden spec with the builders: must score 100 %
  corrupt-file  the oracle's file with one corruption operator (scripts/mutate.py) applied: validity
                must fail, so success ~0 %
  corrupt-spec  builds a slightly wrong system (one more unit, cell or EO unit): every file is valid,
                but TC.2 must fail, so success ~0 % with validity ~100 %

The three see the hidden spec (needs_hidden), which a real system never does.
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from builders.dispatch import build_from_spec  # noqa: E402

# (failure mode, variant) tried in order, starting at a task/repeat-dependent offset
FILE_CORRUPTIONS = [("FM06", "zero_all_charges"), ("FM04", "drop_bond_header_adjusted"),
                    ("FM15", "masses_values_permuted"), ("FM13", "duplicate_atom_new_id"),
                    ("FM17", "atom_moved_onto_another"), ("FM22", "bond_coeff_rows_relabelled"),
                    ("FM12", "counter_ion_removed"), ("FM18", "atom_displaced_3A")]


def _build(task, workdir, spec=None):
    try:
        path, rec = build_from_spec(spec or task["hidden_spec"], workdir, task["id"])
        return {"data_file": path, "trace": {"build": {k: rec.get(k) for k in ("natoms", "data_sha256")}}}
    except Exception as e:
        return {"data_file": None, "builder_refused": True, "error": f"{type(e).__name__}: {e}"}


class Oracle:
    needs_hidden = True
    meta = {"name": "oracle", "kind": "builds the hidden spec (harness sanity check)"}

    def __call__(self, task, workdir, repeat=0):
        return _build(task, workdir)


class FileCorrupter:
    needs_hidden = True
    meta = {"name": "corrupt-file", "kind": "oracle output + one corruption operator (harness sanity check)",
            "operators": [f"{fm}/{v}" for fm, v in FILE_CORRUPTIONS]}

    def __call__(self, task, workdir, repeat=0):
        import mutate
        from dataedit import DataText
        out = _build(task, workdir)
        if not out["data_file"]:
            return out
        ops = {(o["fm"], o["variant"]): o for o in mutate.OPERATORS}
        side = os.path.join(ROOT, os.path.splitext(task["reference"])[0] + ".json")
        import json
        ctx = mutate.Ctx(out["data_file"], {"declared_config": task["declared_config"],
                                            "overrides": json.load(open(side)).get("overrides", {})})
        start = (sum(map(ord, task["id"])) + repeat) % len(FILE_CORRUPTIONS)
        original = open(out["data_file"]).read()
        for i in range(len(FILE_CORRUPTIONS)):
            key = FILE_CORRUPTIONS[(start + i) % len(FILE_CORRUPTIONS)]
            d = DataText.read(out["data_file"])
            try:
                params = ops[key]["fn"](d, ctx)
            except (KeyError, StopIteration, IndexError):
                params = None
            if params is None or d.text() == original:
                continue
            d.write(out["data_file"])
            out["trace"]["corruption"] = {"operator": "/".join(key), "params": params}
            return out
        out["trace"]["corruption"] = None
        return out


def perturb_spec(spec: dict) -> dict:
    """A different, still buildable system: a mineral gets one more cell along its first lateral axis;
    a PCE one more EO unit in its first side chain (or one more acid unit)."""
    s = copy.deepcopy(spec)
    if s["builder"] == "minerals":
        s["supercell"] = [s["supercell"][0] + 1] + list(s["supercell"][1:])
        return s
    p = s["pce"] if s["builder"] == "composite" else s
    if "side_chain_length" in p:
        p["side_chain_length"] = int(p["side_chain_length"]) + 1
        return s
    for lab, m in p["monomers"].items():
        if m.get("kind") in ("ester_peg", "ether_peg"):
            m["eo_units"] = int(m["eo_units"]) + 1
            return s
    lab = next(iter(p["composition"]))
    p["composition"][lab] += 1
    return s


class SpecCorrupter:
    needs_hidden = True
    meta = {"name": "corrupt-spec", "kind": "builds a slightly different system (harness sanity check for TC.2)"}

    def __call__(self, task, workdir, repeat=0):
        out = _build(task, workdir, perturb_spec(task["hidden_spec"]))
        out.setdefault("trace", {})["perturbation"] = "see eval/systems.py perturb_spec"
        return out


def make_system(name: str, mock: str = None):
    if name == "oracle":
        return Oracle()
    if name == "corrupt-file":
        return FileCorrupter()
    if name == "corrupt-spec":
        return SpecCorrupter()
    if name == "baseline":
        from agents.baseline import BaselineSystem
        return BaselineSystem(mock=mock)
    raise ValueError(f"unknown system {name!r}")

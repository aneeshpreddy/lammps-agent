"""Build a DATA FILE from a builder spec — the one entry point shared by the eval oracle, the baseline and
the agent's tool layer.

A builder spec is the `hidden_spec` shape of eval/tasks/*.json:
  {"builder": "minerals",  "model": ..., "supercell": [nx, ny, nz], "force_field": ...}
  {"builder": "pce",       <builders/pce.py architecture, full or convenience form>, "force_field": ...}
  {"builder": "composite", "surface": {...}, "pce": {...}, "height": ..., "orientation": ..., "force_field": ...}
"""
from __future__ import annotations

import os

from .composite import build as build_composite
from .minerals import build_mineral
from .pce import ArchitectureSpec, build as build_pce

BUILDERS = ("minerals", "pce", "composite")


def build_from_spec(spec: dict, outdir: str, name: str):
    """Returns (data_file, build record). Raises on an invalid spec or a builder refusal."""
    kind = spec.get("builder")
    if kind not in BUILDERS:
        raise ValueError(f"builder must be one of {BUILDERS}, got {kind!r}")
    s = {k: v for k, v in spec.items() if k != "builder"}
    s["name"] = name
    os.makedirs(outdir, exist_ok=True)
    if kind == "minerals":
        rec = build_mineral(s["model"], tuple(int(v) for v in s["supercell"]), s["force_field"], outdir, name)
    elif kind == "pce":
        rec = build_pce(ArchitectureSpec.from_json(s), outdir)
        for ext in ("car", "mdf"):
            p = os.path.join(outdir, f"{name}.{ext}")
            if os.path.exists(p):
                os.remove(p)
    else:
        rec = build_composite(s, outdir)
    return os.path.join(outdir, name + ".data"), rec

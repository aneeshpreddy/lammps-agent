"""The website's 3D scenes (web/viewer.py) and the committed landing-page structures (web/structures/)."""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))
import viewer  # noqa: E402

C3S = os.path.join(ROOT, "web", "examples", "c3s_unit_cell_minimized_pcff.data")


def test_scene_keeps_every_atom_and_draws_the_cell():
    S = viewer.scene(C3S)
    hetatm = [l for l in S["pdb"].splitlines() if l.startswith("HETATM")]
    assert len(hetatm) == S["atoms"] == len(S["ids"]) == sum(S["elements"].values())
    assert set(S["elements"]) == {"Ca", "Si", "O"}
    assert len(S["edges"]) == 12                           # a parallelepiped
    assert all(len(p) == 3 and len(q) == 3 for p, q in S["edges"])


def test_viewer_html_loads_hydrogens_and_has_no_inert_controls():
    page = viewer.html(C3S, height=400)
    assert "keepH: true" in page                           # 3Dmol drops hydrogens from PDB text otherwise
    for fn in ("resetView", "fit", "along", "toggleSpin", "toggleBox", "toggleLabels", "toggleH", "restyle", "png"):
        assert f"function {fn}(" in page, fn               # every toolbar button calls a defined function


def test_committed_structures_are_real_outputs():
    files = glob.glob(os.path.join(ROOT, "web", "structures", "*.json"))
    assert len(files) == 5
    for f in files:
        S = json.load(open(f))
        assert S["source"]["run"].startswith("web_") and S["source"]["request"]
        assert S["atoms"] == sum(1 for l in S["pdb"].splitlines() if l.startswith("HETATM"))

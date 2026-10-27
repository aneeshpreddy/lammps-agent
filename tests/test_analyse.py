"""Failure analysis (eval/analyse.py, plan Day 25): spec differences and suggested gap types."""
from __future__ import annotations

import copy

from agents.baseline import from_builder_spec, to_builder_spec
from eval.analyse import spec_diff, suggest_gap
from eval.harness import load_tasks
from eval.systems import perturb_spec


def test_baseline_round_trip_has_no_difference():
    """Every dev hidden spec, through the baseline's answer schema and back, compares equal (labels and
    the PCE convenience form must not count as differences)."""
    for t in load_tasks("dev"):
        h = t["hidden_spec"]
        assert spec_diff(to_builder_spec(from_builder_spec(h)), h) == [], t["id"]


def test_perturbations_are_found_and_classified():
    for t in load_tasks("dev"):
        h = t["hidden_spec"]
        d = spec_diff(perturb_spec(h), h)
        assert len(d) == 1, (t["id"], d)
        field = d[0][0]
        assert field in ("supercell", "units:eo_units", "pce.units:eo_units", "units:counts", "pce.units:counts"), field
        assert suggest_gap({"category": "TC_ONLY"}, d) == "reasoning"


def test_chemistry_and_naming_errors_are_knowledge():
    h = {"builder": "pce", "force_field": "pcff",
         "monomers": {"A": {"kind": "acid", "alpha_methyl": False, "deprotonated": True},
                      "P": {"kind": "ether_peg", "alpha_methyl": True, "spacer": 2, "eo_units": 10, "end": "OH"}},
         "composition": {"A": 4, "P": 2}, "sequence": "random"}
    g = copy.deepcopy(h)
    g["monomers"]["P"]["spacer"] = 1                           # HPEG instead of TPEG
    d = spec_diff(g, h)
    assert [f for f, _ in d] == ["units:chemistry"] and "TPEG" in d[0][1] and "HPEG" in d[0][1]
    assert suggest_gap({"category": "TC_ONLY"}, d) == "knowledge"
    g = copy.deepcopy(h)
    g["force_field"] = "cvff"
    assert suggest_gap({"category": "TC_ONLY"}, spec_diff(g, h)) == "knowledge"
    g = copy.deepcopy(h)
    g["monomers"] = {"X": h["monomers"]["P"], "Y": h["monomers"]["A"]}   # relabelled: no difference
    g["composition"] = {"X": 2, "Y": 4}
    assert spec_diff(g, h) == []
    m = {"builder": "minerals", "model": "tob14_avg_cell", "supercell": [2, 2, 1], "force_field": "pcff"}
    assert [f for f, _ in spec_diff({**m, "model": "tob14_avg_rectangular_cell"}, m)] == ["model"]
    assert [f for f, _ in spec_diff({**m, "builder": "pce"}, m)] == ["builder"]


def test_no_output_and_other_categories():
    assert suggest_gap({"category": "NO_OUTPUT", "error": "unparseable answer: x"}, None) == "formatting"
    assert suggest_gap({"category": "NO_OUTPUT", "error": "API: RateLimitError"}, None) == "infrastructure"
    assert suggest_gap({"category": "NO_OUTPUT", "builder_refused": True,
                        "error": "builder: ValueError: tob11_unit_cell is not available in cvff"}, None) == "knowledge"
    assert suggest_gap({"category": "NO_OUTPUT", "builder_refused": True,
                        "error": "builder: ValueError: the PCE does not fit the cell"}, None) == "reasoning"
    assert suggest_gap({"category": "INCOMPLETE"}, []) == "validator"
    assert suggest_gap({"category": "P2.3"}, []) == "pipeline"

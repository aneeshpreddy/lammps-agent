"""Tool layer (plan Days 26-27): every tool works when called directly from Python, without any LLM."""
from __future__ import annotations

import glob
import json
import os

import pytest

from agents.baseline import to_builder_spec
from builders.pce import architecture_from_params
from tools.examples import EXAMPLES
from tools.schema_check import check
from tools.toolbox import SCHEMAS, ToolBox, definitions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FIELDS = {"ts", "call", "tool", "arguments", "ok", "result", "duration_s"}


def _strict_ok(s, path="$"):
    """Strict tool use: every object closed and fully required, no numeric/string constraints."""
    errs = []
    for k in ("minimum", "maximum", "multipleOf", "minLength", "maxLength"):
        if k in s:
            errs.append(f"{path}: {k}")
    if "anyOf" in s:
        for i, sub in enumerate(s["anyOf"]):
            errs += _strict_ok(sub, f"{path}|{i}")
    if s.get("type") == "object":
        if s.get("additionalProperties") is not False:
            errs.append(f"{path}: additionalProperties")
        if set(s.get("required", [])) != set(s["properties"]):
            errs.append(f"{path}: required")
        for k, v in s["properties"].items():
            errs += _strict_ok(v, f"{path}.{k}")
    if s.get("type") == "array":
        errs += _strict_ok(s["items"], f"{path}[]")
    return errs


def test_definitions_are_strict():
    defs = definitions()
    assert [d["name"] for d in defs] == ["build_data_file", "get_model_info", "get_reference_example"]
    for d in defs:
        assert d["strict"] is True and d["description"]
        assert _strict_ok(d["input_schema"]) == [], d["name"]
    assert "notes" not in SCHEMAS["build_data_file"]["properties"]


def test_schema_check():
    s = SCHEMAS["get_model_info"]
    assert check(s, {"model": "tob11_unit_cell", "force_field": "pcff"}) == []
    assert any("missing required field 'force_field'" in e for e in check(s, {"model": "tob11_unit_cell"}))
    assert any("unknown field 'x'" in e for e in check(s, {"model": "tob11_unit_cell", "force_field": "pcff", "x": 1}))
    assert any("not one of" in e for e in check(s, {"model": "quartz", "force_field": "pcff"}))
    b = SCHEMAS["build_data_file"]
    good = {"builder": "minerals", "force_field": "pcff", "mineral": {"model": "tob11_unit_cell", "supercell": [1, 1, 1]},
            "pce": None, "surface": None, "height": None, "orientation": None}
    assert check(b, good) == []
    assert check(b, {**good, "height": 3}) == []                                  # integer is a number
    assert check(b, {**good, "mineral": {"model": "x", "supercell": [1, True, 1]}})  # bool is not an integer
    assert any("$.height" in e for e in check(b, {**good, "height": "3"}))           # anyOf number|null
    assert check(b, {**good, "surface": {"model": "s", "supercell": "auto"}}) == []
    assert check(b, {**good, "surface": {"model": "s", "supercell": "big"}})


def test_get_model_info(tmp_path):
    tb = ToolBox(str(tmp_path))
    r = tb.run("get_model_info", {"model": "tob11_unit_cell", "force_field": "pcff"})
    assert r["ok"] and r["atoms"] == 88 and r["elements"] == {"Ca": 8, "H": 24, "O": 44, "Si": 12}
    assert r["net_charge_e"] == 0.0 and r["kind"] == "unit cell"
    assert sum(t["count"] for t in r["atom_type_table"]) == 88
    assert {t["ff_type"] for t in r["atom_type_table"]} >= {"sc2", "ca+t", "hoy"}
    s = tb.run("get_model_info", {"model": "tob14_001_surface", "force_field": "pcff"})
    assert s["surface"]["normal"] == "z" and s["surface"]["usable_by_composite_builder"]
    r = tb.run("get_model_info", {"model": "tob11_unit_cell", "force_field": "cvff"})
    assert not r["ok"] and "available in: pcff" in r["error"]
    r = tb.run("get_model_info", {"model": "c3s_unit_cell", "force_field": "pcff"})
    assert not r["ok"] and "c3s_unit_cell_minimized" in r["error"]


def test_reference_examples_are_valid_inputs(tmp_path):
    tb = ToolBox(str(tmp_path))
    for kind in EXAMPLES:
        r = tb.run("get_reference_example", {"kind": kind})
        assert r["ok"], kind
        inp = r["build_data_file_input"]
        assert check(SCHEMAS["build_data_file"], inp) == [], kind
        assert to_builder_spec({**inp, "notes": ""}) is not None


def _pce_fp(p):
    if "monomers" not in p:
        p = architecture_from_params(dict(p))
    return frozenset((u["kind"], bool(u.get("alpha_methyl")), u.get("eo_units"), int(u.get("deprotonated") or 0),
                      p["composition"][lab]) for lab, u in p["monomers"].items())


def _fingerprints(spec):
    if spec["builder"] == "minerals":
        return {("mineral", spec["model"], tuple(spec["supercell"]))}
    if spec["builder"] == "pce":
        return {("pce", _pce_fp(spec))}
    return {("surface", spec["surface"]["model"]), ("pce", _pce_fp(spec["pce"]))}


def test_examples_differ_from_every_eval_task():
    """No example may share a mineral (model, supercell), a PCE chemistry + composition, or a composite's
    surface model with any eval task, dev or test. Only fingerprints are compared; nothing is printed."""
    task_fps = set()
    for f in glob.glob(os.path.join(ROOT, "eval", "tasks", "*.json")):
        task_fps |= _fingerprints(json.load(open(f))["hidden_spec"])
    enough = len(task_fps) > 20
    # only booleans and example names reach the assertion, so a failure never prints task contents
    hits = sorted(f"{kind}:{fp[0]}" for kind, ex in EXAMPLES.items() for fp in _fingerprints(ex["spec"]) if fp in task_fps)
    del task_fps
    assert enough
    assert hits == [], "examples coinciding with an eval task (example:part)"


def test_build_and_log(tmp_path):
    tb = ToolBox(str(tmp_path))
    inp = tb.run("get_reference_example", {"kind": "pce_maleic"})["build_data_file_input"]
    r1 = tb.run("build_data_file", inp)
    assert r1["ok"] and r1["build"] == "build_1" and tb.last_build.endswith("build_1.data")
    f = r1["facts"]
    assert f["net_charge_e"] == 0.0 and f["elements"]["K"] == 4 and r1["builder_details"]["sequences"] == ["MPMPMPMP"]
    # deterministic and safe to retry: same answer, new file, earlier file untouched
    first = open(tb.last_build).read()
    r2 = tb.run("build_data_file", inp)
    assert r2["facts"] == r1["facts"] and r2["builder_details"] == r1["builder_details"]
    assert open(os.path.join(str(tmp_path), "build_1", "build_1.data")).read() == first
    assert open(tb.last_build).read().replace("build_2", "build_1") == first
    # inconsistent spec and builder refusal: ok=false, last_build unchanged
    last = tb.last_build
    r = tb.run("build_data_file", {**inp, "builder": "minerals"})
    assert not r["ok"] and r["stage"] == "spec"
    bad = {**inp, "builder": "minerals", "pce": None, "mineral": {"model": "no_such_model", "supercell": [1, 1, 1]}}
    r = tb.run("build_data_file", bad)
    assert not r["ok"] and r["stage"] == "builder"
    assert tb.last_build == last and [b["ok"] for b in tb.builds] == [True, True, False, False]
    lines = [json.loads(l) for l in open(tb.log_path)]
    assert len(lines) == tb.n_calls == 5
    assert all(LOG_FIELDS <= set(l) for l in lines)
    assert [l["ok"] for l in lines] == [True, True, True, False, False]
    assert lines[1]["result"]["atoms"] == f["atoms"] and lines[3]["result"]["stage"] == "spec"


def test_never_raises_and_tool_result(tmp_path):
    tb = ToolBox(str(tmp_path))
    assert not tb.run("no_such_tool", {})["ok"]
    assert not tb.run("get_model_info", "tob11_unit_cell")["ok"]
    assert "invalid arguments" in tb.run("build_data_file", {"builder": "pce"})["error"]
    block = {"type": "tool_use", "id": "toolu_1", "name": "get_reference_example", "input": {"kind": "mineral"}}
    tr = tb.tool_result(block)
    assert tr["type"] == "tool_result" and tr["tool_use_id"] == "toolu_1" and tr["is_error"] is False
    assert json.loads(tr["content"])["kind"] == "mineral"
    tr = tb.tool_result({**block, "input": {"kind": "nope"}})
    assert tr["is_error"] is True

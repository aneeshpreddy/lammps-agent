"""The website's request assistant (web/assistant.py): parsing, checks and the prompt written from a spec.

No model call: analyse() runs against a fake client. The example specs are the builders' own examples, not
evaluation tasks.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))
import assistant as A  # noqa: E402
from agents.baseline import from_builder_spec  # noqa: E402


def example_specs():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "examples", "pce", "*.json"))):
        s = json.load(open(f))
        out.append({"builder": "pce", "force_field": "pcff", **s})
    for f in sorted(glob.glob(os.path.join(ROOT, "examples", "composite", "*.json"))):
        s = json.load(open(f))
        out.append({"builder": "composite", "force_field": s.get("force_field", "pcff"), **s})
    return out


def mineral(model="tob11_unit_cell", ff="pcff", sc=(2, 2, 1)):
    return {"builder": "minerals", "force_field": ff, "mineral": {"model": model, "supercell": list(sc)}, "pce": None,
            "surface": None, "height": None, "orientation": None, "notes": ""}


@pytest.mark.parametrize("spec", example_specs(), ids=lambda s: s["builder"])
def test_render_prompt_states_every_unit_count(spec):
    a = from_builder_spec(spec)
    text = A.render_prompt(a)
    assert A.FF[a["force_field"]] in text
    for c in a["pce"]["composition"]:
        assert f"{c['count']} " in text
    assert A.spec_problems(a) == []


def test_render_prompt_mineral_and_cvff_coverage():
    a = mineral()
    assert "2 × 2 × 1 supercell" in A.render_prompt(a)
    assert A.spec_problems(a) == []
    assert any("not covered by CVFF" in p for p in A.spec_problems(mineral(ff="cvff")))


def test_parse_parameters_and_ambiguities_skip_malformed_lines():
    r = {"parameters": ["force_field | stated | pcff = PCFF-INTERFACE", "sequence | inferred | not stated | typical",
                        "garbage line", "n_chains | guessed | bad source"],
         "ambiguities": ["maleic deprotonation | fully | partly; none", "| no issue |", "only an issue"]}
    p = A.parameters(r)
    assert p == {"force_field": ("stated", "pcff = PCFF-INTERFACE"), "sequence": ("inferred", "not stated | typical")}
    amb = A.ambiguities(r)
    assert amb[0] == ("maleic deprotonation", "fully", ["partly", "none"])
    assert amb[1] == ("only an issue", "", [])


def test_check_result_flags_unusable_answers():
    assert A.check_result({"buildable": False, "out_of_scope_reason": ""}) == ["not buildable, but no reason given"]
    assert A.check_result({"buildable": False, "out_of_scope_reason": "OPLS-AA is not available"}) == []
    bad = mineral()
    bad["mineral"] = None
    assert A.check_result({"buildable": True, "spec": bad})[0].startswith("inconsistent specification")


def test_calcium_cannot_neutralise_an_odd_charge():
    spec = next(s for s in example_specs() if s["builder"] == "pce" and "monomers" in s)
    a = from_builder_spec(spec)
    p = a["pce"]
    p["monomers"] = [{"label": "A", "kind": "acid", "alpha_methyl": False, "deprotonated": 1, "eo_units": None,
                      "end": None, "spacer": None}]
    p["composition"] = [{"label": "A", "count": 3}]
    p["sequence"] = {"mode": "random", "explicit": None}
    p["n_chains"], p["counterion"] = 1, "Ca2+"
    assert A.carboxylates(a) == 3
    assert any("cannot neutralise 3 carboxylates" in x for x in A.spec_problems(a))
    p["counterion"] = "Na+"
    assert A.spec_problems(a) == []
    assert "neutralise the 3 carboxylates (3 ions)" in A.render_prompt(a)


def test_describe_built_and_builder_defaults():
    spec = {"builder": "minerals", "model": "tob11_unit_cell", "supercell": [1, 1, 1], "force_field": "pcff"}
    facts = {"atoms": 1234, "box_A": {"lengths": [10.0, 11.0, 12.0]}}
    assert "1,234 atoms" in A.describe_built(spec, facts)
    assert A.builder_defaults(spec) == []
    pce = next(s for s in example_specs() if s["builder"] == "pce")
    labels = [k for k, _ in A.builder_defaults({**pce, "box": {"padding": 2.0}})]
    assert "Box padding" in labels


class FakeClient:
    def __init__(self, payload, stop="end_turn"):
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(
            stop_reason=stop, model="fake", content=[SimpleNamespace(type="text", text=json.dumps(payload))]))


def test_analyse_with_fake_client(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "CACHE", str(tmp_path))
    good = {"buildable": True, "out_of_scope_reason": "", "spec": mineral(), "parameters": [], "ambiguities": [], "missing": []}
    out = A.analyse("tobermorite 2x2x1", client=FakeClient(good))
    assert out["ok"] and out["problems"] == []
    assert A.cached("tobermorite 2x2x1")["result"]["spec"]["mineral"]["model"] == "tob11_unit_cell"
    broken = dict(good, spec=dict(mineral(), mineral=None))
    assert not A.analyse("broken", client=FakeClient(broken))["ok"]
    assert A.cached("broken") is None
    assert not A.analyse("cut", client=FakeClient(good, stop="max_tokens"))["ok"]

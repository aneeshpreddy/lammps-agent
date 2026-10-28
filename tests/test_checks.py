"""Variant E (agents/checks.py): build summary + request check, with the scripted mocks; no API call."""
from __future__ import annotations

import json
import os

import pytest

from agents.checks import REQ_PROMPT, built_values, compare
from agents.loop import AgentSystem, replay
from agents.mock import ScriptedClient, _requirements
from eval.harness import load_tasks, score


@pytest.fixture(scope="module")
def tasks():
    return {t["id"]: t for t in load_tasks("dev", ["p02", "m02", "c01"])}


def _events(wd, kind):
    return [e for e in (json.loads(l) for l in open(os.path.join(wd, "trace.jsonl"))) if e["event"] == kind]


def test_compare_rules():
    built = {"system": "pce", "force_field": "cvff", "n_chains": 1, "eo_units": [10, 45], "anchor": ["TPEG"],
             "height_A": 3.0, "supercell": "auto", "counterion": "Na+"}
    assert compare({"system": "mineral", "n_chains": 2}, built) == [("system", "mineral", "pce")]
    assert compare({"eo_units": [45, 10, 10], "anchor": "TPEG", "height_A": 3.04, "supercell": [2, 2, 1]}, built) == []
    assert [m[0] for m in compare({"anchor": "HPEG", "height_A": 3.2, "counterion": "none", "n_chains": None},
                                  built)] == ["anchor", "height_A", "counterion"]


def test_hidden_specs_match_their_own_requirements(tasks):
    for t in tasks.values():
        assert compare(_requirements(t["hidden_spec"]), built_values(t["hidden_spec"], {"supercell": [1, 1, 1]})) == []


def test_extraction_prompt_is_independent_of_the_knowledge():
    assert "catalogue" not in REQ_PROMPT and "Do not infer" in REQ_PROMPT


@pytest.mark.parametrize("tid", ["p02", "m02", "c01"])
def test_valid_but_wrong_build_is_caught_only_with_checks(tasks, tmp_path, tid):
    t = tasks[tid]
    c = AgentSystem(mock="wrongvalid", checks=False)(t, str(tmp_path / "c"))
    assert c["stop"] == "accepted" and c["attempts"] == 1 and not score(t, c)["success"]      # TC.2 fails afterwards
    e = AgentSystem(mock="wrongvalid", checks=True)(t, str(tmp_path / "e"))
    assert e["stop"] == "accepted" and e["attempts"] == 2 and score(t, e)["success"]
    fb = _events(tmp_path / "e", "feedback")[0]["text"]
    assert "the file is valid, but not accepted" in fb and "the request says" in fb


def test_agent_reading_wins_on_a_repeated_build(tasks, tmp_path):
    t = tasks["p02"]

    class WrongExtraction(ScriptedClient):          # the extraction call misreads the number of chains
        def create(self, **kw):
            r = super().create(**kw)
            if "tools" not in kw:
                req = json.loads(r.content[0].text)
                req["n_chains"] += 1
                r.content[0].text = json.dumps(req)
            return r

    out = AgentSystem(client=WrongExtraction("perfect", t), checks=True)(t, str(tmp_path))
    assert out["stop"] == "accepted" and out["attempts"] == 2 and score(t, out)["success"]
    rc = _events(tmp_path, "request_check")
    assert [len(x["raised"]) for x in rc] == [1, 0] and len(rc[1]["kept_by_agent"]) == 1


def test_build_summary_only_with_checks(tasks, tmp_path):
    AgentSystem(mock="perfect", checks=True)(tasks["c01"], str(tmp_path / "e"))
    AgentSystem(mock="perfect", checks=False)(tasks["c01"], str(tmp_path / "c"))
    built = [x for x in _events(tmp_path / "e", "tool") if x["name"] == "build_data_file"][-1]["result"]
    assert built["summary"].startswith("Built: PCE") and " on surface " in built["summary"]
    assert all("summary" not in x["result"] for x in _events(tmp_path / "c", "tool"))
    assert len(_events(tmp_path / "c", "requirements")) == 0


def test_checked_run_replays_exactly(tasks, tmp_path):
    AgentSystem(mock="wrongvalid", checks=True)(tasks["m02"], str(tmp_path / "run"))
    assert replay(str(tmp_path / "run"), str(tmp_path / "again")) == []


def test_checks_need_full_feedback():
    with pytest.raises(ValueError):
        AgentSystem(mock="perfect", feedback="none", checks=True)
    assert AgentSystem(mock="perfect", checks=True).meta["name"] == "agent-checked-mock-perfect"

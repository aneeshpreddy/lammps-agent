"""Agent loop (plan Days 29-33) with the scripted mock models of agents/mock.py: no API call."""
from __future__ import annotations

import json
import os
import time

import pytest

from agents.baseline import knowledge, system_prompt
from agents.loop import (AgentSystem, ToolTimeout, _with_cache_breakpoint, agent_system_prompt, declared_config_for,
                         feedback_text, replay, time_limit)
from eval.harness import load_tasks, score
from validator import validate


@pytest.fixture(scope="module")
def tasks():
    return {t["id"]: t for t in load_tasks("dev", ["p02", "m02"])}


def _events(wd):
    return [json.loads(l) for l in open(os.path.join(wd, "trace.jsonl"))]


def test_prompts_share_the_knowledge_word_for_word():
    k = knowledge()
    assert system_prompt().endswith(k) and agent_system_prompt().endswith(k)
    assert "build_data_file" in agent_system_prompt() and "output schema" not in agent_system_prompt()


def test_perfect_is_accepted_first_time(tasks, tmp_path):
    out = AgentSystem(mock="perfect")(tasks["p02"], str(tmp_path))
    assert out["stop"] == "accepted" and out["attempts"] == 1 and score(tasks["p02"], out)["success"]
    ev = [e["event"] for e in _events(tmp_path)]
    assert ev[0] == "start" and ev[-1] == "stop" and ev.count("validation") == 1 and "feedback" not in ev


def test_validator_feedback_leads_to_a_fix(tasks, tmp_path):
    out = AgentSystem(mock="fix")(tasks["p02"], str(tmp_path))
    assert out["stop"] == "accepted" and out["attempts"] == 2 and score(tasks["p02"], out)["success"]
    ev = _events(tmp_path)
    fb = [e for e in ev if e["event"] == "feedback"]
    assert len(fb) == 1 and "P2.1" in fb[0]["text"] and "total charge = -4" in fb[0]["text"]
    v = [e for e in ev if e["event"] == "validation"]
    assert [x["passed"] for x in v] == [False, True]
    # each attempt's output file is kept
    assert os.path.exists(tmp_path / "build_1" / "build_1.data") and os.path.exists(tmp_path / "build_2" / "build_2.data")


def test_builder_error_is_fixed_within_the_attempt(tasks, tmp_path):
    out = AgentSystem(mock="fix")(tasks["m02"], str(tmp_path))
    assert out["stop"] == "accepted" and out["attempts"] == 1
    tools = [e for e in _events(tmp_path) if e["event"] == "tool"]
    assert [t["is_error"] for t in tools] == [True, False]


def test_repeated_failure_changes_the_instruction_then_escalates(tasks, tmp_path):
    out = AgentSystem(mock="stubborn")(tasks["p02"], str(tmp_path))
    assert out["escalated"] and out["stop"].startswith("escalated") and "P2.1" in out["stop"]
    fb = [e for e in _events(tmp_path) if e["event"] == "feedback"]
    assert [e["repeated"] for e in fb] == [False, True] and "reconsider the approach" in fb[1]["text"]
    assert score(tasks["p02"], out)["category"] == "P2.1"          # the last build is still submitted and scored


def test_feedback_modes(tasks, tmp_path):
    out = AgentSystem(mock="stubborn")(tasks["p02"], str(tmp_path))
    res = validate(out["data_file"], declared_config_for({"builder": "pce", "force_field": "cvff"}))
    full = feedback_text("build_1", 1, 3, res, "full", repeated=True)
    assert "P2.1" in full and "P3.3" in full and "reconsider" in full
    assert feedback_text("build_1", 1, 3, res, "none", repeated=True) == "The last build did not pass validation. Try again."
    t01 = feedback_text("build_1", 1, 3, res, "tiers01", repeated=False)
    assert "P2.1" not in t01 and "No Tier 0-1 check failed" in t01
    assert "without a successful build" in feedback_text("x", 2, 3, None, "full", repeated=False)


def test_bounds_stop_cleanly(tasks, tmp_path):
    # step limit in every attempt, never a build: ends with a reason, no output
    out = AgentSystem(mock="runaway", limits={"max_steps_per_attempt": 2, "max_attempts": 2})(tasks["p02"], str(tmp_path / "a"))
    assert out["data_file"] is None and out["stop"] == "attempt limit"
    assert [a["ended"] for a in out["trace"]["attempts"]] == ["step limit", "step limit"]
    assert score(tasks["p02"], out)["category"] == "NO_OUTPUT"
    # token limit (the mock reports 1100 tokens per call)
    out = AgentSystem(mock="runaway", limits={"max_tokens_per_task": 2500})(tasks["p02"], str(tmp_path / "b"))
    assert out["stop"].startswith("token limit") and out["trace"]["usage"]["input_tokens"] == 3000
    # a limit hit after a valid build: the build is still validated and accepted, and the limit is recorded
    out = AgentSystem(mock="perfect", limits={"max_tokens_per_task": 1500})(tasks["p02"], str(tmp_path / "b2"))
    assert out["stop"].startswith("accepted after token limit") and score(tasks["p02"], out)["success"]
    # wall-clock limit
    out = AgentSystem(mock="perfect", limits={"max_wall_s": 0})(tasks["p02"], str(tmp_path / "c"))
    assert out["stop"].startswith("time limit") and out["data_file"] is None
    stop = _events(tmp_path / "c")[-1]
    assert stop["event"] == "stop" and stop["stop"].startswith("time limit")


def test_tool_timeout():
    with pytest.raises(ToolTimeout):
        with time_limit(0.05):
            time.sleep(1)
    with time_limit(1):
        pass


def test_replay_reproduces_a_run(tasks, tmp_path):
    AgentSystem(mock="fix")(tasks["p02"], str(tmp_path / "run"))
    assert replay(str(tmp_path / "run"), str(tmp_path / "again")) == []


def test_cache_breakpoint_does_not_touch_the_conversation():
    msgs = [{"role": "user", "content": "build x"}, {"role": "assistant", "content": []},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "{}"}]}]
    sent = _with_cache_breakpoint(msgs)
    assert sent[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in msgs[-1]["content"][-1] and sent[:2] == msgs[:2]
    assert _with_cache_breakpoint(msgs[:1])[0]["content"][0]["cache_control"]


def test_declared_config_follows_the_build():
    cfg = declared_config_for({"builder": "minerals", "model": "tob11_unit_cell", "force_field": "pcff"})
    dec = cfg["declared"]
    assert dec["density_family"] == "tob11_unit_cell" and "pcff" in dec["config_id"]
    assert declared_config_for({"builder": "composite", "force_field": "cvff"})["declared"]["config_id"].startswith("interface-cvff")

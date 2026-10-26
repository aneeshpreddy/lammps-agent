"""Evaluation harness and single-call baseline glue (no API calls, no test-split runs)."""
import datetime as dt
import glob
import json
import os

import pytest

from agents.baseline import SCHEMA, from_builder_spec, system_prompt, to_builder_spec
from builders.pce import ArchitectureSpec
from eval.harness import aggregate, load_tasks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_test_split_is_closed_before_16_nov():
    with pytest.raises(RuntimeError, match="closed until 2026-11-16"):
        load_tasks("test", today=dt.date(2026, 11, 15))
    assert len(load_tasks("dev")) == 13


def _arch(p, ff):
    return ArchitectureSpec.from_json({**p, "force_field": ff, "name": "x"})


def _same(a, b):
    assert a["builder"] == b["builder"] and a["force_field"] == b["force_field"]
    if a["builder"] == "minerals":
        assert (a["model"], list(a["supercell"])) == (b["model"], list(b["supercell"]))
        return
    pa, pb = (a, b) if a["builder"] == "pce" else (a["pce"], b["pce"])
    if a["builder"] == "pce":
        pa = {k: v for k, v in pa.items() if k not in ("builder", "force_field", "name")}
        pb = {k: v for k, v in pb.items() if k not in ("builder", "force_field", "name")}
    assert _arch(pa, a["force_field"]) == _arch(pb, b["force_field"])
    if a["builder"] == "composite":
        assert a["surface"] == b["surface"]
        assert a.get("height") == b.get("height") and a.get("orientation") == b.get("orientation")


def test_baseline_schema_round_trips_every_dev_task_and_example():
    specs = [t["hidden_spec"] for t in load_tasks("dev")]
    for f in sorted(glob.glob(os.path.join(ROOT, "examples", "pce", "*.json"))):
        specs.append({"builder": "pce", **json.load(open(f))})
    for f in sorted(glob.glob(os.path.join(ROOT, "examples", "composite", "*.json"))):
        d = json.load(open(f))
        specs.append({"builder": "composite", **d})
    for s in specs:
        _same(to_builder_spec(from_builder_spec(s)), s)


def test_schema_meets_structured_output_rules():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            for k in ("minimum", "maximum", "minLength", "maxLength", "multipleOf"):
                assert k not in node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(SCHEMA)


def test_system_prompt_lists_every_model_and_no_task():
    p = system_prompt()
    for car in glob.glob(os.path.join(os.path.dirname(ROOT), "CEMENT_MINERALS", "*.car")):
        assert os.path.basename(car)[:-4] in p
    for t in load_tasks("dev"):
        assert t["input"][:60] not in p


def test_aggregate_follows_metrics():
    tasks = [{"id": i, "difficulty": d, "domain": "pce", "force_field": "pcff"} for i, d in (("a", "easy"), ("b", "hard"))]
    base = {"valid": True, "failing": [], "category": "SUCCESS", "tier_reached": 3, "usage": {}, "cost_usd": 0.0,
            "latency_s": 1.0}
    runs = [dict(base, task="a", repeat=0, success=True), dict(base, task="a", repeat=1, success=True),
            dict(base, task="b", repeat=0, success=False, category="P2.1", failing=["P2.1"], valid=False),
            dict(base, task="b", repeat=1, success=True)]
    a = aggregate(runs, tasks, 2)
    assert a["per_task"] == {"a": 1.0, "b": 0.5}
    assert a["system_success_rate"] == 0.75
    assert a["spread_across_repeats"]["per_repeat"] == [0.5, 1.0]
    assert a["pass_at_k"] == 1.0
    assert a["validity_rate"] == 0.75
    assert a["by_difficulty"]["hard"]["rate"] == 0.5
    assert a["failure_categories"] == {"P2.1": 1}

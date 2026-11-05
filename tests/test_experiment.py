"""Experiment tables (eval/experiment.py) from synthetic harness results: no build, no model."""
from __future__ import annotations

import json
import os

from eval.experiment import first_attempt, mock_for, sign_test, tables
from eval.harness import aggregate

TASKS = [{"id": f"t{i}", "difficulty": "easy", "domain": d, "force_field": "pcff"}
         for i, d in enumerate(["mineral", "pce", "pce", "composite"])]


def _write(exp, folder, name, successes, category="TC_ONLY", attempts=1):
    runs = []
    for k in range(2):
        for t, ok in zip(TASKS, successes):
            runs.append({"task": t["id"], "repeat": k, "success": ok, "valid": True, "failing": [], "tier_reached": 3,
                         "category": "SUCCESS" if ok else category, "builder_refused": False, "attempts": attempts,
                         "cost_usd": 0.001, "usage": {"input_tokens": 100}, "latency_s": 1.0, "stop": "accepted",
                         "escalated": False})
            wd = os.path.join(exp, folder, "runs", t["id"], f"r{k}")
            os.makedirs(wd, exist_ok=True)
            att = [{"attempt": 1, "verdict": "PASS", "fingerprint": []}] if attempts == 1 else \
                [{"attempt": 1, "verdict": "FAIL", "fingerprint": [["P2.1", "2"]]}, {"attempt": 2, "verdict": "PASS", "fingerprint": []}]
            json.dump({"trace": {"attempts": att}}, open(os.path.join(wd, "trace.json"), "w"))
    fc = {"system": {"name": name, "model": None}, "git_commit": "abcdef0", "git_dirty": False, "validator_version": "1",
          "split_sha256": "0" * 64, "lammps": "LAMMPS", "pricing": {"date": "2026-10-27", "source": "pricing page"}}
    json.dump({"fixed_conditions": fc, "tasks": [t["id"] for t in TASKS], "repeats": 2,
               "aggregate": aggregate(runs, TASKS, 2), "runs": runs}, open(os.path.join(exp, folder, "results.json"), "w"))


def test_tables_and_figures(tmp_path):
    exp = str(tmp_path)
    _write(exp, "baseline", "baseline-mock-perfect", [True, False, False, False])
    _write(exp, "agent-nofeedback", "agent-nofeedback", [True, False, True, False], category="P2.1", attempts=2)
    _write(exp, "agent", "agent", [True, True, True, False], attempts=2)
    md = tables(exp)
    assert "| **A** | baseline (single call, no tools) | **0.250** |" in md
    assert "| C vs B | validator feedback | +0.250 | 1 / 3 / 0 | 1.000 |" in md
    assert "| TC_ONLY | 6 | 2/6 | 4/6 |" in md                      # A's failures, B and C on the same runs
    assert "P2.1 → 4/8 succeed" in md                                  # inside the loop (B)
    assert os.path.exists(tmp_path / "figures" / "success_per_system.png")
    assert os.path.exists(tmp_path / "figures" / "success_by_domain.png")


def test_helpers():
    assert sign_test(6, 0) < 0.05 < sign_test(5, 0) and sign_test(0, 0) == 1.0
    assert mock_for("agent", ["baseline=perfect", "fix"]) == "fix" and mock_for("baseline", ["baseline=perfect"]) == "perfect"
    assert mock_for("agent", None) is None
    assert first_attempt({"attempts": [{"verdict": "FAIL", "fingerprint": [["REQ:supercell", "req"]]}]}) == "REQ:supercell"
    assert first_attempt({"attempts": [{"verdict": "NO_BUILD", "fingerprint": ["NO_BUILD"]}]}) == "NO_BUILD"

"""Code-freeze record (scripts/freeze_config.py): no model, no build."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import freeze_config  # noqa: E402


def test_record_and_check(tmp_path, monkeypatch):
    c = freeze_config.current()
    assert c["tools"]["names"] == ["build_data_file", "get_model_info", "get_reference_example"]
    assert len(c["prompts"]["agent_system_sha256"]) == 64 and c["loop"]["limits"]["max_attempts"] >= 1
    assert "| Model |" in freeze_config.markdown(c)
    path = tmp_path / "frozen.json"
    monkeypatch.setattr(freeze_config, "JSON_PATH", str(path))
    assert freeze_config.check()[0].startswith("no frozen configuration")
    json.dump(c, open(path, "w"))
    assert freeze_config.check() == []
    c["loop"]["limits"]["max_attempts"] += 1
    c["git_commit"] = "something else"                 # volatile: not compared
    c["git_tag"] = None                                 # later commits are not on the tag
    c["pricing"] = {"date": "2026-11-16"}               # prices re-checked on the day of use
    json.dump(c, open(path, "w"))
    assert freeze_config.check() == [f"loop.limits.max_attempts: frozen {c['loop']['limits']['max_attempts']} / "
                                     f"now {c['loop']['limits']['max_attempts'] - 1}"]


def test_test_split_needs_the_freeze(monkeypatch, tmp_path):
    from eval import experiment
    monkeypatch.setattr(freeze_config, "JSON_PATH", str(tmp_path / "none.json"))
    with pytest.raises(SystemExit, match="frozen configuration"):
        experiment.run(["baseline"], "test", 1, str(tmp_path / "out"))

"""Code freeze record (plan Day 39) -> docs/FROZEN_CONFIG.md + docs/FROZEN_CONFIG.json.

  python scripts/freeze_config.py            record the current configuration (at the freeze, after tagging)
  python scripts/freeze_config.py --check    compare the current configuration with the recorded one

Records everything a scored run depends on: model ID and effort, the hashes of every prompt, schema and tool
definition, the loop limits and feedback mode, component versions, the validator's declared configurations
and calibration files, the split, the pricing record, LAMMPS and git. eval/experiment.py refuses to run the
test split unless --check finds no difference.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
JSON_PATH = os.path.join(ROOT, "docs", "FROZEN_CONFIG.json")
MD_PATH = os.path.join(ROOT, "docs", "FROZEN_CONFIG.md")
VOLATILE = ("recorded", "git_commit", "git_dirty")       # not compared by --check


def _h(x) -> str:
    data = x if isinstance(x, (bytes, str)) else json.dumps(x, sort_keys=True)
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _file(rel: str) -> str:
    return _h(open(os.path.join(ROOT, rel), "rb").read())


def current() -> dict:
    import yaml
    from agents.baseline import EFFORT, MAX_TOKENS, MODEL, PROMPT_VERSION, SCHEMA, system_prompt
    from agents.checks import CHECKS_VERSION, REQ_PROMPT, REQ_SCHEMA
    from agents.loop import LOOP_VERSION, agent_system_prompt, load_limits
    from eval.harness import SPLIT, VALIDATOR_VERSION, prices
    from tools.toolbox import TOOLS_VERSION, definitions

    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    lmp = open(os.path.join(ROOT, "docs", "lammps_build.txt")).read().strip().splitlines()
    return {
        "recorded": _dt.datetime.now().isoformat(timespec="seconds"),
        "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "git_tag": git("describe", "--tags", "--exact-match") or None,
        "model": {"provider": cfg["model"].get("provider"), "model_id": MODEL, "effort": EFFORT, "max_tokens": MAX_TOKENS,
                  "thinking": "adaptive (model default)", "sampling": "API defaults"},
        "prompts": {"baseline_version": PROMPT_VERSION, "baseline_system_sha256": _h(system_prompt()),
                    "baseline_schema_sha256": _h(SCHEMA), "agent_system_sha256": _h(agent_system_prompt()),
                    "request_check_prompt_sha256": _h(REQ_PROMPT), "request_check_schema_sha256": _h(REQ_SCHEMA)},
        "tools": {"version": TOOLS_VERSION, "definitions_sha256": _h(definitions()),
                  "names": [d["name"] for d in definitions()]},
        "loop": {"version": LOOP_VERSION, "limits": load_limits(), "feedback": cfg["agent"].get("feedback", "full"),
                 "checks_default": bool(cfg["agent"].get("checks", False)), "checks_version": CHECKS_VERSION},
        "validator": {"version": VALIDATOR_VERSION,
                      "configs": {f: _file(f"configs/{f}") for f in sorted(os.listdir(os.path.join(ROOT, "configs")))},
                      "calibration": {f: _file(f"calibration/{f}")
                                      for f in sorted(os.listdir(os.path.join(ROOT, "calibration")))}},
        "eval": {"split_sha256": _h(open(SPLIT, "rb").read()), "metrics_sha256": _file("docs/METRICS.md"),
                 "tasks_sha256": _h({f: _file(f"eval/tasks/{f}") for f in sorted(os.listdir(os.path.join(ROOT, "eval", "tasks")))})},
        "pricing": {k: v for k, v in prices().items() if k != "models"} | {"sha256": _file("eval/pricing.json")},
        "lammps": next((l.strip() for l in lmp if "LAMMPS" in l or "Simulator" in l), lmp[0] if lmp else ""),
        "config_yaml_sha256": _file("config.yaml"),
    }


def differences(rec: dict, now: dict, path="") -> list:
    out = []
    for k in sorted(set(rec) | set(now)):
        if not path and k in VOLATILE:
            continue
        a, b = rec.get(k), now.get(k)
        if isinstance(a, dict) and isinstance(b, dict):
            out += differences(a, b, f"{path}{k}.")
        elif a != b:
            out.append(f"{path}{k}: frozen {json.dumps(a)[:80]} / now {json.dumps(b)[:80]}")
    return out


def check() -> list:
    """Differences between the frozen record and now ([] = unchanged); a missing record is one difference."""
    if not os.path.exists(JSON_PATH):
        return ["no frozen configuration recorded (run scripts/freeze_config.py at the code freeze)"]
    return differences(json.load(open(JSON_PATH)), current())


def markdown(c: dict) -> str:
    m, p, t, lp, v, e = c["model"], c["prompts"], c["tools"], c["loop"], c["validator"], c["eval"]
    L = ["# Frozen configuration (plan Day 39)", "",
         f"Recorded {c['recorded']} by `scripts/freeze_config.py` · git {c['git_commit'][:7]}"
         f"{' (dirty)' if c['git_dirty'] else ''}{' · tag ' + c['git_tag'] if c['git_tag'] else ''}. "
         "From now on only bug fixes that block evaluation are allowed; `python scripts/freeze_config.py --check` "
         "lists anything that changed, and `eval/experiment.py` refuses to run the test split if it finds a difference.",
         "", "| Item | Frozen value |", "|---|---|",
         f"| Model | `{m['model_id']}` ({m['provider']}), effort {m['effort']}, max_tokens {m['max_tokens']}, thinking {m['thinking']}, sampling {m['sampling']} |",
         f"| Baseline prompt | {p['baseline_version']}; system `{p['baseline_system_sha256'][:16]}…`, schema `{p['baseline_schema_sha256'][:16]}…` |",
         f"| Agent prompt | system `{p['agent_system_sha256'][:16]}…` |",
         f"| Request check (E) | prompt `{p['request_check_prompt_sha256'][:16]}…`, schema `{p['request_check_schema_sha256'][:16]}…`, {lp['checks_version']} |",
         f"| Tools | {t['version']}: {', '.join(t['names'])}; definitions `{t['definitions_sha256'][:16]}…` |",
         f"| Loop | {lp['version']}; feedback {lp['feedback']}; checks by default {lp['checks_default']}; limits "
         + ", ".join(f"{k} {val}" for k, val in lp["limits"].items()) + " |",
         f"| Validator | {v['version']}; {len(v['configs'])} declared configurations, {len(v['calibration'])} calibration files (hashes in FROZEN_CONFIG.json) |",
         f"| Eval set | split `{e['split_sha256'][:16]}…`, tasks `{e['tasks_sha256'][:16]}…`, METRICS.md `{e['metrics_sha256'][:16]}…` |",
         f"| Prices | {c['pricing'].get('source', '')} ({c['pricing'].get('date', '')}) |",
         f"| LAMMPS | {c['lammps']} |",
         f"| config.yaml | `{c['config_yaml_sha256'][:16]}…` |", "",
         "Full values: `docs/FROZEN_CONFIG.json`."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        diff = check()
        print("\n".join(diff) if diff else "unchanged since the freeze")
        return 1 if diff else 0
    c = current()
    json.dump(c, open(JSON_PATH, "w"), indent=2)
    open(MD_PATH, "w").write(markdown(c))
    print(markdown(c))
    return 0


if __name__ == "__main__":
    sys.exit(main())

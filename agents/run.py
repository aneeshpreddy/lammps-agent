"""Build a LAMMPS DATA FILE from a plain-English request with the agent (C, config.yaml defaults).

  export ANTHROPIC_API_KEY=...   (never written to a file)
  python -m agents.run "Build a LAMMPS data file in PCFF-INTERFACE for ..." [--out DIR]
  python -m agents.run --file request.txt --out runs/requests/my_system

Writes into DIR (default runs/requests/<timestamp>/):
  system.data   the accepted file (a copy of the last build), only if every Tier 0-3 check passed
  trace.jsonl   every model response, tool call and validation
  REPORT.md     what was tried and why it failed, if no build was accepted
and prints one sentence saying what was built, so the user can check it against the request: the
validator certifies that the file is valid, not that it is the system that was meant.

Exit status: 0 accepted, 1 not accepted (see REPORT.md), 2 no run (bad arguments, folder in use).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents.loop import AgentSystem  # noqa: E402
from eval.harness import cost_usd, prices  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agents.run", description=__doc__.split("\n")[0])
    ap.add_argument("request", nargs="?", help="the request, in quotes")
    ap.add_argument("--file", help="read the request from this text file instead")
    ap.add_argument("--out", help="output folder (default runs/requests/<timestamp>); must not hold a run")
    ap.add_argument("--mock", help=argparse.SUPPRESS)       # tests only: POLICY:TASK, a scripted model (agents/mock.py)
    a = ap.parse_args(argv)
    if bool(a.request) == bool(a.file):
        ap.print_usage(sys.stderr)
        print("give the request either in quotes or with --file", file=sys.stderr)
        return 2
    text = (open(a.file).read() if a.file else a.request).strip()
    out = a.out or os.path.join(ROOT, "runs", "requests", _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))

    task = {"id": "request", "input": text}
    policy = None
    if a.mock:                          # the scripted models read a task's hidden spec: dev tasks only
        import json
        policy, tid = a.mock.split(":")
        task["hidden_spec"] = json.load(open(os.path.join(ROOT, "eval", "tasks", f"{tid}.json")))["hidden_spec"]
    system = AgentSystem(mock=policy)
    try:
        r = system(task, out)
    except (FileExistsError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2

    accepted = r["stop"].startswith("accepted")
    cost = cost_usd(system.model, r.get("usage"), prices())
    print(f"{'ACCEPTED' if accepted else 'NOT ACCEPTED'}: {r['stop']} ({r['attempts']} attempt(s))")
    if r.get("build_summary"):
        print(r["build_summary"])
    if accepted:
        dest = os.path.join(out, "system.data")
        shutil.copyfile(r["data_file"], dest)
        print(f"File: {dest}")
        print("Every Tier 0-3 check passed, including LAMMPS with the full force field. "
              "Check the sentence above against your request: the validator cannot know what you meant.")
    else:
        if r.get("error"):
            print(f"Error: {r['error']}")
        if r.get("report"):
            print(f"Report: {r['report']} (do not use the last file without review)")
    print(f"Trace: {os.path.join(out, 'trace.jsonl')}" + (f" · cost ${cost:.4f}" if cost else ""))
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())

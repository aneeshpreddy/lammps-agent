"""Agent loop (plan Days 29-33): tool use, validator feedback, retries, bounds, non-convergence, traces.

Plain Python, no agent framework, so the control flow is visible (plan Day 29):

  for each attempt (at most K):
      the model calls tools until it stops (stop_reason != "tool_use") or the step limit is hit
      the ORCHESTRATOR validates the attempt's last build: always, Tiers 0-3 (plan Day 30). The validator is
      never a tool, and it gets only what the agent built: the declared configuration follows from the
      builder spec (builder, force field, mineral model). The task's reference is never seen here, so
      TC.2 (is it the requested system?) is checked only by the harness afterwards.
      PASS -> done. FAIL -> a concise summary of the failing checks and LAMMPS errors goes back to the model.
  Bounds (plan Day 31): steps per attempt, attempts, tokens per task, wall-clock, per-tool timeout; when one
  is hit the loop stops cleanly and records why.
  Non-convergence (plan Day 32): an attempt's fingerprint is its set of failing (property, tier). The same
  fingerprint twice -> the feedback asks for a different approach; three times -> escalate (stop).
  Traces (plan Day 33): <workdir>/trace.jsonl holds every model response (thinking included), tool call and
  result, validation and feedback; builds stay in <workdir>/build_<n>/; replay() re-runs a run from its folder.
  Escalation (plan Day 38): a run that ends without an accepted build writes <workdir>/REPORT.md (the last
  output, its failing checks, every attempt and what changed between builds), so it is never mistaken for a
  good file. Guard rails: nothing is written into data/reference/; an existing run folder is not overwritten
  unless overwrite=True; no tool submits jobs or runs commands (the three tools are the whole interface).

Feedback modes (plan Day 42 ablation): "full" (C), "none" (B: "try again" only, no validator detail, no
strategy hint), "tiers01" (optional D: only Tier 0-1 failures are described). checks=True is variant E
(C + build summary + request check, agents/checks.py); off by default.

The model sees the same domain knowledge as the baseline (agents/baseline.py knowledge(), word for word) and
the same builder spec (as the build_data_file input), so the systems differ only by tools, feedback and retries.
"""
from __future__ import annotations

import contextlib
import copy
import datetime
import hashlib
import json
import os
import signal
import sys
import threading
import time
from collections import Counter
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents.baseline import EFFORT, MAX_TOKENS, MODEL, knowledge  # noqa: E402
from agents.checks import (CHECKS_VERSION, REQ_PROMPT, REQ_SCHEMA, built_values, compare,  # noqa: E402
                           extract_requirements, mismatch_lines)
from tools.toolbox import TOOLS_VERSION, ToolBox, definitions, guard_workdir  # noqa: E402
from validator import load_config, validate  # noqa: E402

LOOP_VERSION = "loop-v1 (2026-10-27)"
FEEDBACK_MODES = ("full", "tiers01", "none")
DEFAULT_LIMITS = {"max_attempts": 3, "max_steps_per_attempt": 12, "max_tokens_per_task": 400000,
                  "max_wall_s": 1200, "tool_timeout_s": 300}

AGENT_INTRO = """You build a LAMMPS DATA FILE for the request, using tools. \
You do not write the file: the deterministic builders do (INTERFACE FF 1.5, msi2lmp typing and charges); you decide what to build.

## How to work
- Build the requested system with build_data_file. get_model_info compares mineral models and get_reference_example shows the exact input format; use them when they help.
- Check the facts build_data_file returns against the request (element counts, backbone sequences, counter-ions, supercell, surface, height). If they do not match, change the spec and build again.
- When the last build is the requested system, stop calling tools and reply with one sentence. The last successful build is the one submitted.
- After you stop, the file is validated. If validation fails you receive the result and can rebuild."""


def agent_system_prompt() -> str:
    return AGENT_INTRO + "\n\n" + knowledge()


def load_limits() -> dict:
    import yaml
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"))).get("agent") or {}
    return {k: cfg.get(k, v) for k, v in DEFAULT_LIMITS.items()}


# ---------------------------------------------------------------------------------------------
def declared_config_for(spec: dict):
    """The declared validation configuration of what the agent built (no task information)."""
    family = {"minerals": "minerals", "pce": "pce", "composite": "composite"}[spec["builder"]]
    overrides = {"density_family": spec["model"]} if spec["builder"] == "minerals" else {}
    return load_config(declared=f"configs/interface_{spec['force_field']}_{family}.yaml",
                       overrides={"declared": overrides})


def not_passing(res) -> list:
    return [c for c in res.checks if c.tier in (0, 1, 2, 3) and c.verdict not in ("PASS", "NOT_APPLICABLE")]


def fingerprint(res) -> tuple:
    return tuple(sorted((c.property, str(c.tier)) for c in not_passing(res)))


def feedback_text(build: str, attempt: int, k: int, res, mode: str, repeated: bool, mismatches: list = None) -> str:
    """The observation sent back after a failed attempt (plan Day 30: name, tier, message, key numbers,
    LAMMPS ERROR lines; not the whole log). mismatches: variant E's request check (agents/checks.py)."""
    if mode == "none":
        return "The last build did not pass validation. Try again."
    head = f"Validation of {build} (attempt {attempt} of {k}): not accepted."
    if res is None:
        lines = [f"Attempt {attempt} of {k} ended without a successful build. Build the requested system with "
                 "build_data_file."]
    elif res.passed:
        lines = [f"Validation of {build} (attempt {attempt} of {k}): the file is valid, but not accepted."]
    else:
        bad = not_passing(res)
        shown = [c for c in bad if mode == "full" or c.tier in (0, 1)]
        lines = [head]
        if shown:
            lines.append("Checks that did not pass:")
            lines += [f"- {c.property} (tier {c.tier}, {c.verdict}): {(c.message or '').strip()[:300]}" for c in shown[:8]]
            if len(shown) > 8:
                lines.append(f"- … and {len(shown) - 8} more")
        else:
            lines.append("No Tier 0-1 check failed; a later check did not pass.")
        errs = [e for e in (res.lammps or {}).get("errors", []) if e][:5] if mode == "full" else []
        if errs:
            lines.append("LAMMPS errors:")
            lines += [f"- {str(e)[:300]}" for e in errs]
        if not mismatches:
            lines.append("Change the spec and rebuild with build_data_file; when the new build is right, stop calling tools.")
    if mismatches:
        lines.append("It does not match what the request states:")
        lines += mismatch_lines(mismatches)
        lines.append("Re-read the request and rebuild with build_data_file. If you are sure the build is what the request "
                     "asks for, build it again unchanged; it is then accepted if it is valid.")
    if repeated and mode != "none":
        lines.append("This is the same result as an earlier attempt. Do not patch the last spec again: reconsider the "
                     "approach. Re-read the request, check the model or monomers with the lookup tools, then build again.")
    return "\n".join(lines)


def _flat(d, prefix=""):
    if not isinstance(d, dict):
        return {prefix: d}
    out = {}
    for k, v in d.items():
        out.update(_flat(v, f"{prefix}.{k}" if prefix else k))
    return out


def spec_changes(before: dict, after: dict) -> list:
    """What changed between two build_data_file inputs, field by field."""
    a, b = _flat(before), _flat(after)
    return [f"{k}: {json.dumps(a.get(k))} -> {json.dumps(b.get(k))}" for k in sorted(set(a) | set(b))
            if a.get(k) != b.get(k)]


def report_text(task: dict, stop: str, attempts: list, builds: list, build_attempt: dict, last_res,
                out_file, workdir: str) -> str:
    """REPORT.md for a run that ended without an accepted build (plan Day 38)."""
    rel = os.path.relpath(out_file, workdir) if out_file else None
    L = [f"# Not accepted: {task['id']}", "", "**Request:**", ""]
    L += ["> " + line for line in task["input"].splitlines()]
    L += ["", f"**Outcome:** {stop}.", "",
          f"**The last build (`{rel}`) did NOT pass validation. Do not use it without review.**" if rel
          else "**No file was built.**", "", "## Attempts", "",
          "| Attempt | Model calls | Ended | Build | Verdict | Checks that did not pass |", "|---|---|---|---|---|---|"]
    for a in attempts:
        fp = ", ".join(f[0] if isinstance(f, (list, tuple)) else f for f in a["fingerprint"])
        L.append(f"| {a['attempt']} | {a['steps']} | {a['ended']} | {a['file'] or '—'} | {a['verdict']} | {fp or '—'} |")
    if last_res is not None:
        L += ["", "## The last build: checks that did not pass", ""]
        L += [f"- **{c.property}** (tier {c.tier}, {c.verdict}): {(c.message or '').strip()[:500]}" for c in not_passing(last_res)]
        errs = [e for e in (last_res.lammps or {}).get("errors", []) if e][:5]
        if errs:
            L += ["", "LAMMPS errors:", ""] + [f"- `{str(e)[:300]}`" for e in errs]
    L += ["", "## What was tried", ""]
    prev = None
    for b in builds:
        head = f"- `{b['build']}` (attempt {build_attempt.get(b['build'], '?')}): "
        inp = b.get("input") or {}
        if prev is None:
            what = f"builder {inp.get('builder')}, force field {inp.get('force_field')}"
        else:
            ch = spec_changes(prev, inp)
            what = "changed " + "; ".join(ch) if ch else "the same input as the previous build"
        L.append(head + what + ("" if b["ok"] else f" — **refused**: {b.get('error', '')[:300]}"))
        prev = inp
    if not builds:
        L.append("- no build_data_file call")
    L += ["", "## For a human", "",
          "- Compare the request with the failing checks above; every build is kept in `build_<n>/`.",
          "- The full record (model responses, tool calls, validations, feedback) is `trace.jsonl`."]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------
class ToolTimeout(Exception):
    pass


@contextlib.contextmanager
def time_limit(seconds):
    """SIGALRM-based limit for one tool call (main thread only; elsewhere no limit). A builder's LAMMPS child
    is killed by subprocess.run when the alarm interrupts it."""
    if not seconds or threading.current_thread() is not threading.main_thread():
        yield
        return

    def handler(signum, frame):
        raise ToolTimeout(f"tool call exceeded {seconds} s")
    old = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _dump(block) -> dict:
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json", exclude_none=True)
    if isinstance(block, dict):
        return block
    return {k: v for k, v in vars(block).items() if v is not None}


def _get(block, key):
    return block[key] if isinstance(block, dict) else getattr(block, key, None)


def _with_cache_breakpoint(messages: list) -> list:
    """Copy of the conversation with a cache breakpoint on its last block, so each call re-reads the earlier
    turns from the prompt cache (with the system-prompt breakpoint: 2 of the 4 allowed)."""
    out = list(messages)
    last = copy.deepcopy(out[-1])
    content = last["content"]
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if isinstance(content[-1], dict):
        content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
    last["content"] = content
    out[-1] = last
    return out


def _add_user_text(messages: list, text: str):
    """Append text as the next user turn (merged into a trailing user turn, e.g. tool results after a step limit)."""
    if messages and messages[-1]["role"] == "user":
        c = messages[-1]["content"]
        messages[-1]["content"] = (c if isinstance(c, list) else [{"type": "text", "text": c}]) + [{"type": "text", "text": text}]
    else:
        messages.append({"role": "user", "content": text})


class Trace:
    def __init__(self, path: str):
        self.path, self.t0 = path, time.time()
        open(path, "w").close()

    def event(self, kind: str, **data):
        line = {"t": round(time.time() - self.t0, 3),
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"),
                "event": kind, **data}
        with open(self.path, "a") as f:
            f.write(json.dumps(line, default=str) + "\n")


# ---------------------------------------------------------------------------------------------
class AgentSystem:
    """system(task_view, workdir, repeat) for eval/harness.py."""

    def __init__(self, feedback: str = None, mock: str = None, client=None, model: str = MODEL,
                 effort: str = EFFORT, limits: dict = None, overwrite: bool = False, checks: bool = None):
        import yaml
        cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"))).get("agent") or {}
        self.feedback = feedback or cfg.get("feedback", "full")
        if self.feedback not in FEEDBACK_MODES:
            raise ValueError(f"feedback must be one of {FEEDBACK_MODES}")
        self.checks = bool(cfg.get("checks", False) if checks is None else checks)
        if self.checks and self.feedback != "full":
            raise ValueError("variant E (checks) is defined on top of full feedback (C)")
        self.mock, self._client, self.overwrite = mock, client, overwrite
        self.needs_hidden = bool(mock)
        self.model, self.effort = model, effort
        self.limits = {**load_limits(), **(limits or {})}
        self.system = agent_system_prompt()
        self.tools = definitions()
        name = {"full": "agent", "none": "agent-nofeedback", "tiers01": "agent-tiers01"}[self.feedback]
        name = "agent-checked" if self.checks else name
        self.meta = {"name": name + (f"-mock-{mock}" if mock else ""), "kind": "tool-use loop + validator feedback",
                     "model": None if mock else model, "effort": effort,
                     "thinking": "adaptive (always on for this model)", "max_tokens": MAX_TOKENS,
                     "feedback": self.feedback, "limits": self.limits, "loop_version": LOOP_VERSION,
                     "tools_version": TOOLS_VERSION,
                     "system_prompt_sha256": hashlib.sha256(self.system.encode()).hexdigest(),
                     "tools_sha256": hashlib.sha256(json.dumps(self.tools, sort_keys=True).encode()).hexdigest(),
                     "tool_choice": "auto (forced tool choice is not supported by this model)",
                     "checks": ({"version": CHECKS_VERSION, "build_summary": True, "request_check": True,
                                 "request_prompt_sha256": hashlib.sha256(REQ_PROMPT.encode()).hexdigest(),
                                 "request_schema_sha256": hashlib.sha256(
                                     json.dumps(REQ_SCHEMA, sort_keys=True).encode()).hexdigest()}
                                if self.checks else None)}

    def _client_for(self, task):
        if self._client is not None:
            return self._client
        if self.mock:
            from agents.mock import ScriptedClient
            return ScriptedClient(self.mock, task)
        import anthropic
        self._client = anthropic.Anthropic()
        return self._client

    def _call(self, client, messages):
        return client.messages.create(
            model=self.model, max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            tools=self.tools, messages=_with_cache_breakpoint(messages),
            output_config={"effort": self.effort})

    def __call__(self, task, workdir, repeat=0):
        L = self.limits
        t0 = time.time()
        guard_workdir(workdir)
        if os.path.exists(os.path.join(workdir, "trace.jsonl")) and not self.overwrite:
            raise FileExistsError(f"{workdir} already holds a run; choose a new folder or pass overwrite=True")
        os.makedirs(workdir, exist_ok=True)
        trace = Trace(os.path.join(workdir, "trace.jsonl"))
        trace.event("start", task=task["id"], input=task["input"], repeat=repeat, meta=self.meta, tools=self.tools)
        client = self._client_for(task)
        tb = ToolBox(workdir, describe=self.checks)
        messages = [{"role": "user", "content": task["input"]}]
        usage = Counter()
        seen = Counter()
        attempts, final, stop, error = [], None, None, None
        build_attempt, res = {}, None
        req, raised = None, set()
        if self.checks:                         # variant E: what the request states, read by a separate call
            try:
                req, req_usage, ev = extract_requirements(client, self.model, self.effort, task["input"])
                usage.update(req_usage)
                trace.event("requirements", requirements=req, **ev)
            except Exception as e:
                if type(e).__name__ == "AuthenticationError" or "authentication method" in str(e):
                    raise SystemExit("No valid Anthropic credentials: set ANTHROPIC_API_KEY (or run `ant auth login`).")
                trace.event("requirements", requirements=None, error=f"{type(e).__name__}: {str(e)[:300]}")

        for attempt in range(1, L["max_attempts"] + 1):
            steps, ended = 0, None
            while ended is None:
                if steps >= L["max_steps_per_attempt"]:
                    ended = "step limit"
                    break
                if sum(usage.values()) >= L["max_tokens_per_task"]:
                    stop = f"token limit ({sum(usage.values())} >= {L['max_tokens_per_task']})"
                    break
                if time.time() - t0 >= L["max_wall_s"]:
                    stop = f"time limit ({L['max_wall_s']} s)"
                    break
                tc = time.time()
                try:
                    resp = self._call(client, messages)
                except Exception as e:
                    stop, error = "api error", f"API: {type(e).__name__}: {str(e)[:300]}"
                    if type(e).__name__ == "AuthenticationError" or "authentication method" in str(e):
                        raise SystemExit("No valid Anthropic credentials: set ANTHROPIC_API_KEY (or run `ant auth login`).")
                    break
                steps += 1
                u = resp.usage
                call_usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                              "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                              "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
                usage.update(call_usage)
                trace.event("response", attempt=attempt, step=steps, stop_reason=resp.stop_reason,
                            request_id=getattr(resp, "_request_id", None), model=getattr(resp, "model", None),
                            usage=call_usage, latency_s=round(time.time() - tc, 2),
                            content=[_dump(b) for b in resp.content])
                messages.append({"role": "assistant", "content": resp.content})
                if resp.stop_reason == "tool_use":
                    results = []
                    for b in resp.content:
                        if _get(b, "type") != "tool_use":
                            continue
                        ts = time.time()
                        try:
                            with time_limit(L["tool_timeout_s"]):
                                r = tb.tool_result(b)
                        except ToolTimeout as e:
                            r = {"type": "tool_result", "tool_use_id": _get(b, "id"),
                                 "content": json.dumps({"ok": False, "error": str(e)}), "is_error": True}
                        trace.event("tool", attempt=attempt, step=steps, name=_get(b, "name"), id=_get(b, "id"),
                                    input=_get(b, "input"), result=json.loads(r["content"]), is_error=r["is_error"],
                                    duration_s=round(time.time() - ts, 3))
                        if _get(b, "name") == "build_data_file":
                            build_attempt[json.loads(r["content"]).get("build")] = attempt
                        results.append(r)
                    messages.append({"role": "user", "content": results})
                elif resp.stop_reason == "refusal":
                    stop = "refusal"
                    break
                else:                       # end_turn, max_tokens, ...: the attempt is over
                    ended = resp.stop_reason
            if stop and tb.last_build is None:
                break

            # the orchestrator validates the attempt's last build: always (plan Day 30)
            build = tb.last_build
            res = None
            if build:
                tv = time.time()
                res = validate(build, declared_config_for(tb.spec_of(build)))
                fp = fingerprint(res)
                mism = []
                if req:
                    entry = tb.entry_of(build)
                    found = compare(req, built_values(entry["spec"], entry.get("details")))
                    mism = [m for m in found if (m[0], json.dumps(m[2])) not in raised]
                    raised |= {(m[0], json.dumps(m[2])) for m in mism}
                    trace.event("request_check", attempt=attempt, mismatches=found, raised=mism,
                                kept_by_agent=[m for m in found if m not in mism])
                    fp = fp + tuple(("REQ:" + m[0], "req") for m in mism)
                trace.event("validation", attempt=attempt, file=os.path.relpath(build, workdir), verdict=res.verdict,
                            passed=bool(res.passed), fingerprint=fp,
                            checks=[c.to_dict() for c in not_passing(res)],
                            lammps_errors=(res.lammps or {}).get("errors", []), duration_s=round(time.time() - tv, 2))
            else:
                fp, mism = ("NO_BUILD",), []
                trace.event("validation", attempt=attempt, file=None, verdict="NO_BUILD", passed=False, fingerprint=fp)
            attempts.append({"attempt": attempt, "steps": steps, "ended": ended or stop,
                             "file": os.path.relpath(build, workdir) if build else None,
                             "verdict": res.verdict if res else "NO_BUILD", "fingerprint": list(fp)})
            if res is not None and res.passed and not mism:
                final = build
                break
            if stop:
                break
            seen[fp] += 1
            if seen[fp] >= 3:
                why = ", ".join(f[0] for f in fp) or "no check named"
                stop = f"escalated: the same failure in three attempts ({why}; last attempt ended: {ended or stop})"
                break
            if attempt == L["max_attempts"]:
                stop = "attempt limit"
                break
            text = feedback_text(os.path.basename(build or "").replace(".data", "") or "the last build", attempt,
                                 L["max_attempts"], res, self.feedback, repeated=seen[fp] == 2, mismatches=mism)
            _add_user_text(messages, text)
            trace.event("feedback", attempt=attempt, mode=self.feedback, repeated=seen[fp] == 2, text=text)

        out_file = final or tb.last_build
        accepted = "accepted" + (f" after {stop}" if stop else "")
        summary = {"attempts": attempts, "stop": accepted if final else (stop or "attempt limit"),
                   "accepted_in_loop": bool(final), "usage": dict(usage), "wall_s": round(time.time() - t0, 2),
                   "tool_calls": tb.n_calls, "builds": tb.n_builds}
        report = None
        if not final:
            report = os.path.join(workdir, "REPORT.md")
            with open(report, "w") as fh:
                fh.write(report_text(task, summary["stop"], attempts, tb.builds, build_attempt,
                                     res if attempts and attempts[-1]["file"] else None, out_file, workdir))
            summary["report"] = "REPORT.md"
        trace.event("stop", **summary, data_file=os.path.relpath(out_file, workdir) if out_file else None)
        return {"data_file": out_file, "report": report, "attempts": len(attempts) or 1,
                "usage": {} if self.mock else dict(usage),
                "error": error or (None if final or out_file else f"no build ({summary['stop']})"),
                "escalated": summary["stop"].startswith("escalated"), "stop": summary["stop"], "trace": summary}


# ---------------------------------------------------------------------------------------------
def replay(run_dir: str, workdir: str) -> list:
    """Re-run a recorded run with its recorded model responses in place of the model; returns the
    differences in tool results and verdicts (empty = the run is reproduced exactly)."""
    events = [json.loads(l) for l in open(os.path.join(run_dir, "trace.jsonl"))]
    start = events[0]
    meta = start["meta"]
    responses = [e for e in events if e["event"] == "response"]
    requirements = next((e for e in events if e["event"] == "requirements"), None)

    class ReplayClient:
        def __init__(self):
            self.messages = self
            self.i = 0

        def create(self, **kw):
            if "tools" not in kw:                   # variant E's extraction call, recorded as "requirements"
                return SimpleNamespace(stop_reason=requirements["stop_reason"], model=None,
                                       usage=SimpleNamespace(**requirements["usage"]),
                                       content=[SimpleNamespace(type="text", text=requirements["text"])])
            e = responses[self.i]
            self.i += 1
            return SimpleNamespace(stop_reason=e["stop_reason"], model=e.get("model"),
                                   usage=SimpleNamespace(**{k: e["usage"].get(k, 0) for k in
                                                            ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                                             "cache_read_input_tokens")}),
                                   content=[SimpleNamespace(**b) for b in e["content"]])

    system = AgentSystem(feedback=meta["feedback"], client=ReplayClient(), limits=meta["limits"],
                         checks=bool(meta.get("checks")))
    system({"id": start["task"], "input": start["input"]}, workdir)
    again = [json.loads(l) for l in open(os.path.join(workdir, "trace.jsonl"))]

    def key(evts):
        return [(e["event"], e.get("name"), json.dumps(e.get("result"), sort_keys=True) if e["event"] == "tool" else None,
                 e.get("verdict"), tuple(map(tuple, e.get("fingerprint") or ())), e.get("text"))
                for e in evts if e["event"] in ("tool", "validation", "feedback", "request_check")]
    a, b = key(events), key(again)
    return [f"{i}: recorded {x} / replayed {y}" for i, (x, y) in enumerate(zip(a, b)) if x != y] + \
        ([f"event count {len(a)} vs {len(b)}"] if len(a) != len(b) else [])

# Agent loop (plan Days 29–33)

Code: `agents/loop.py` (loop, bounds, feedback, traces, replay), `agents/mock.py` (scripted models for tests). Tools: `docs/TOOLS.md`. Tests: `tests/test_loop.py`. Harness checks: `docs/HARNESS.md`. Version `loop-v1 (2026-10-27)`. Built 27 Oct against scripted mock models; **no model has run it yet**.

## The loop

```
messages = [task input]
for attempt in 1..K:                                   K = max_attempts (3)
    repeat (at most max_steps_per_attempt calls):
        response = model(system prompt, tools, messages)   # tool_choice auto
        if response asks for tools: run them, send tool_result blocks back
        else: the attempt is over
    the ORCHESTRATOR validates the attempt's last build: always
        PASS             -> accepted, stop
        not accepted     -> fingerprint = set of failing (property, tier)
                            same fingerprint 3 times -> escalate, stop
                            otherwise feedback -> next attempt
```

**Validation in the loop** uses Tiers 0–3 with the declared configuration of what the agent built. The builder, force field and mineral model choose `configs/interface_{ff}_{family}.yaml` and the density family. The task's reference is never used inside the loop, so TC.2 ("is it the requested system?") is only checked by the harness afterwards.

**Same knowledge as the baseline.** The agent's system prompt is a short "how to work" section plus `knowledge()` from `agents/baseline.py`, word for word: force fields, builders, monomers, model catalogue. The `build_data_file` input is the baseline's output schema. The baseline's own prompt was not changed by this refactor (same SHA-256). Agent and baseline therefore differ only in tools, feedback and retries.

## Feedback (plan Day 30) and the ablation modes (Day 42)

After a failed attempt the model receives:
- the build name and the attempt number;
- each check that did not pass (property, tier, verdict, message with its key numbers; at most 8);
- up to 5 LAMMPS ERROR lines;
- the instruction to rebuild.

It does not receive the whole log. For example:

```
Validation of build_1 (attempt 1 of 3): not accepted.
Checks that did not pass:
- P2.1 (tier 2, FAIL): total charge = -4.000000 e, target +0.0000 e (tolerance 1.62e-05 e …)
- P3.3 (tier 3, FAIL): 1 LAMMPS warning(s) not on the allow-list; first: WARNING: System is not charge neutral, net charge = -4
Change the spec and rebuild with build_data_file; when the new build is right, stop calling tools.
```

| `feedback` | Ablation | What follows a failed attempt |
|---|---|---|
| `full` | C (the agent) | the message above, plus the "reconsider" hint on a repeated fingerprint |
| `none` | B (retries without feedback) | only "The last build did not pass validation. Try again." No check names, no hint. |
| `tiers01` | optional D | only Tier 0–1 failures are described |

Run them as `--system agent`, `--system agent-nofeedback` or `--system agent-tiers01`. The default mode is set in `config.yaml` (`agent: feedback`).

## Bounds (plan Day 31)

Configured in `config.yaml` → `agent:`. The values are PROVISIONAL and will be tuned on dev runs only.

| Limit | Default | When it is hit |
|---|---|---|
| `max_steps_per_attempt` | 12 model calls | the attempt ends and its last build (if any) is validated |
| `max_attempts` (K) | 3 | stop: `attempt limit` |
| `max_tokens_per_task` | 400 000 (input + cache + output) | stop: `token limit (…)` |
| `max_wall_s` | 1 200 s | stop: `time limit (…)` |
| `tool_timeout_s` | 300 s per call | the tool call returns an error to the model (SIGALRM; a builder's LAMMPS child is killed) |

**A limit hit after a build.** The build is still validated. If it passes, the run is `accepted after token limit …`. Otherwise the last build is submitted and scored as it is.

**Refusal or API error.** The loop stops, and the reason is recorded.

**Missing credentials.** The whole run stops at the first call.

## Non-convergence (plan Day 32)

An attempt's fingerprint is the sorted set of (property, tier) that did not pass, or `NO_BUILD`.
- **Second identical fingerprint:** the feedback adds "This is the same result as an earlier attempt. Do not patch the last spec again: reconsider the approach…".
- **Third:** escalation. The loop stops with `escalated: … (P2.1, P3.3; last attempt ended: end_turn)`, and the harness counts `escalations`.

## Traces and replay (plan Day 33)

Each run's folder (`runs/eval/<run>/runs/<task>/r<k>/`) holds:
- **`trace.jsonl`**, one line per event:
  - `start`: task, input, system settings, limits, tool definitions;
  - `response`: stop reason, request ID, usage, latency, every content block including thinking;
  - `tool`: name, input, full result, error flag, duration;
  - `validation`: verdict, fingerprint, the checks that did not pass, LAMMPS errors;
  - `feedback`: the exact text;
  - `stop`: reason, attempts, token totals, wall time.
- **every build**, in `build_<n>/` (each attempt's output file);
- **`tool_calls.jsonl`** (the tool layer's log);
- **`trace.json`**, the harness's score.

The run folder also holds `system_prompt.txt`.

`replay(run_dir, workdir)` re-runs a recorded run, with the recorded model responses standing in for the model. It returns every difference in tool results, verdicts and feedback; an empty list means the run was reproduced exactly. Tests and checks use it.

## Checks without a model

- **`tests/test_loop.py` (11 tests):**
  - the prompts share the knowledge;
  - accepted first time;
  - validator feedback leads to a fix;
  - a builder error is fixed within the attempt;
  - a repeated failure changes the instruction, then escalates;
  - the three feedback modes;
  - each bound stops cleanly with its reason;
  - tool timeout;
  - replay is exact;
  - the cache breakpoint;
  - the validation config follows the build.
- **Harness checks** (`docs/HARNESS.md`): mock perfect, fix and stubborn agents on the whole dev split, each with an expected result.

The mocks read the hidden spec. They check the loop's control flow, never a model.

## Cost-relevant details

- **Prompt caching.** The system prompt (with the tools) and the conversation so far are cached: a breakpoint goes on the system block and on the last block of each request. Each call therefore re-reads earlier turns at the cache-read price.
- **Usage accounting.** Usage is summed per task and priced by the harness (`eval/pricing.json`).

## Known limitation, to discuss before the dev runs

**The validator inside the loop catches invalid files, not wrong systems.** The builders produce valid files for almost every consistent spec. Validator feedback can therefore only help where Tiers 0–3 catch something:
- **charge:** a PCE without counter-ions (P2.1);
- **box margins:** a box padding outside 1–5 Å (P2.10);
- **overlaps:** a composite placed too close to the surface (P2.3);
- **builder refusals:** these come back as tool errors within an attempt.

A **wrong but valid system** passes inside the loop and fails only the harness's TC.2. Examples:
- the wrong mineral model, or a wrong supercell;
- a wrong EO length;
- the wrong anchor (HPEG against TPEG).

The agent can catch these only by comparing the facts `build_data_file` returns against the request. The prompt asks it to do that.

This matters for the ablation: if most baseline failures turn out to be TC-only, B and C may differ little. That would be a finding, not a bug. The baseline failure analysis (`eval/analyse.py`, gap types) will show which kind dominates. Options if TC-only failures dominate:
- an explicit "check the build against the request" step in the loop;
- a request-checking tool that restates the build in words.

Both would be decided on dev data only.

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

Configured in `config.yaml` → `agent:`. Tuned on dev runs only. In the dev runs of 3 Nov, no run needed a second attempt or hit a limit, so the defaults are kept.

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

## Escalation report and guard rails (plan Day 38)

**Report.** A run that ends without an accepted build writes `REPORT.md` in its folder and returns its path as `report`. This covers escalation, the attempt limit, a token or time limit, a refusal and an API error. The report gives:
- the outcome, and a bold warning that the last build did NOT pass validation (or that nothing was built);
- one row per attempt: model calls, how it ended, the build, the verdict, and the checks that did not pass;
- the last build's failing checks, with messages and LAMMPS errors;
- what was tried: each build's input as a field-by-field change from the previous build, and the builder's reason for any refusal.

**Scoring.** The harness still scores the last build, so the failure category (P2.1, TC_ONLY, …) stays visible in the results. A user of the agent gets the report together with a file that is clearly marked as not accepted.

**Guard rails:**
- Nothing is written into `data/reference/`. `ToolBox` and the loop refuse a work folder inside it.
- A run folder that already holds a run (`trace.jsonl`) is not overwritten unless `AgentSystem(overwrite=True)` is passed.
- The harness refuses an output folder that already holds results.
- No cluster jobs. The agent's whole interface is the three tools: none runs a command or submits a job. The validator's LAMMPS backend is set by the owner in `config.yaml`, never by the agent.

## Checks without a model

- **`tests/test_loop.py` (14 tests):**
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
  - the validation config follows the build;
  - a run that is not accepted writes a report, and the report lists what changed between builds;
  - the guard rails (no overwrite, no writes into `data/reference/`, no reuse of a harness output folder).
- **Harness checks** (`docs/HARNESS.md`): mock perfect, fix and stubborn agents on the whole dev split, each with an expected result.

The mocks read the hidden spec. They check the loop's control flow, never a model.

## Cost-relevant details

- **Prompt caching.** The system prompt (with the tools) and the conversation so far are cached: a breakpoint goes on the system block and on the last block of each request. Each call therefore re-reads earlier turns at the cache-read price.
- **Usage accounting.** Usage is summed per task and priced by the harness (`eval/pricing.json`).

## Known limitation, confirmed by the dev runs

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

This matters for the ablation: if most baseline failures turn out to be TC-only, B and C may differ little. That would be a finding, not a bug. Variant E (below) is built for this case.

**Dev runs, 3 Nov** (Sonnet 5.5, 13 tasks × 3 repeats, `docs/RESULTS_DEV.md`). This is what happened:
- **No file was rejected.** The in-loop validator did not reject a single build in B, C or E. Every accepted file was valid in attempt 1, so C's feedback never fired.
- **The only recoverable failure was a builder refusal.** On c06 the PCE was too wide for the one slab cell the request fixes. The refusal comes back as a tool error, so B and C both see it.
  - At first, both enlarged the cell, which gives a valid file of the wrong system.
  - After the refusal message was changed to also suggest another seed (`builders/composite.py`), both kept the cell and changed the seed: c06 went from 0/3 to 3/3.
- **Result: B and C do not differ.** Under METRICS v1.2: A 0.92, B 1.00, C 1.00.
  - Under v1.1, C had one failure on c04. It was a scoring effect of random sequences in TC.2 chemistry mode, not a model error: the hidden spec itself passed with only 5 of 10 seeds.
  - v1.2 (owner, 5 Nov) made that mode order-free. The re-score from the saved files turned that run, and 3 others on c04, into passes.

## The build summary and the command-line tool (5 Nov)

**Every run says what its file is.** The loop returns `build_summary`: one plain sentence (`describe_build`, `agents/checks.py`) saying what the submitted file contains. For example: "Built: PCE (PCFF-INTERFACE), 1 chain(s), each 16 backbone units [methacrylic acid (COO-) x12, methacrylate ester PEG EO10 OCH3 x4], 4 side chain(s), sequence alternating, counter-ion Ca2+; 486 atoms, net charge +0 e, box 25.3 x 32.6 x 37.7 Å."

**Why.** The validator certifies validity, not intent. A valid file of the wrong system, such as 2×2 slab cells where 2×1 was asked, passes it. The sentence lets the person who wrote the request catch that in seconds, without a second model reading the request (variant E's request check, which misread p04 on dev).

**`python -m agents.run "request" [--out DIR]`** (`agents/run.py`):
- runs the agent with the `config.yaml` defaults;
- prints the verdict and the sentence;
- copies an accepted file to `DIR/system.data`, or points to `REPORT.md`.

The exit status is 0 if accepted, 1 if not accepted, and 2 if there was no run.

**Showing the sentence to the agent too** (`agent: summary` in `config.yaml`, or `--system agent-summary`). The same sentence is added to every `build_data_file` result, so the model can compare it with the request itself. This is variant E without the request check. **Dev run, 5 Nov:** `runs/eval/agent-summary_dev_20261105-182152` against C in `runs/exp/dev_20261103-180733/agent`.
- **Success:** 1.00 against 1.00 under METRICS v1.2. Under v1.1 it was 0.95 against 0.97, both from the c04 random-sequence scoring effect.
- **The model never acted on the sentence.** All 39 runs in both systems built exactly once.

**It stays off for the agent:** it had no effect and costs a few more tokens. It stays on for the person reading the result.

## Declining and stating assumptions (loop-v2, 6 Nov)

**The trial.** Six natural-language requests, written in a chemist's style, were run through `agents/run.py`. No eval task was involved.
- Four were right.
- On the APEG surface request, the side chains got methoxy ends. The request did not say, but APEG is normally OH-terminated.
- "Make me a PCE…" was built with silent defaults.
- **"C-S-H with Ca/Si 1.7 and water in CLAYFF" came back as tobermorite 14 Å in PCFF-INTERFACE, ACCEPTED.** The agent had declined correctly in attempt 1. The loop then fed back "Build the requested system", and the agent built a substitute.

**Changes:**
- **A reply without a build is a decline.** If an attempt ends with an answer and no successful build, the run stops as "declined by the agent". No file is written; the reason goes to the reply and to REPORT.md.
- **The agent prompt** tells it to decline, rather than substitute, what the builders cannot make, and to name its assumptions in its final reply. `agents/run.py` prints that reply.
- **The shared knowledge (baseline-v3)** gives the side-chain end when the request does not state one: OCH3 for MPEG, OH for APEG, HPEG, TPEG and VPEG. Every eval task states it, so no task is affected.

**After the change, the same six requests** gave six right outcomes. Each one lists its assumptions, the APEG ends are OH, and the C-S-H request is declined with the reason. Test: mock policy `decline`.

## Variant E: build summary and request check (dropped by the owner on 5 Nov)

E is not part of the test experiment. Its code stays in the repository (`--system agent-checked`), so the dev result below can be reproduced.

Code: `agents/checks.py` (`checks-v1 (2026-10-28)`). Run with `--system agent-checked`; in `config.yaml` it is `agent: checks: false`. E is C plus two checks. Neither one ever sees the task's reference.

- **Build summary (no model).** `build_data_file` also returns one sentence saying what was built. For example: "Built: PCE (CVFF-INTERFACE), 1 chain(s), each 16 backbone units [maleic (2 COO-) x8, APEG EO20 OH x8], 8 side chain(s), sequence alternating, counter-ion Na+; …". A wrong-but-valid build is easier for the model to notice in words than in raw counts.
- **Request check.** Once per task, a separate model call gets only the request and a short field glossary (`REQ_PROMPT`). It does not get the agent's knowledge or conversation. It returns what the request states explicitly, in `REQ_SCHEMA`, with every field null when it is not stated:
  - domain, force field, supercell;
  - chains, backbone units, side chains and acid units per chain;
  - EO lengths, anchor, counter-ion, sequence;
  - height, orientation.

  After each attempt, plain code (`compare`) checks those statements against what was built. A mismatch blocks acceptance and goes back to the agent with the validator feedback:

  ```
  Validation of build_1 (attempt 1 of 3): the file is valid, but not accepted.
  It does not match what the request states:
  - supercell: the request says [2, 2, 1], the build has [3, 2, 1]
  Re-read the request and rebuild with build_data_file. If you are sure the build is what the request asks for, build it again unchanged; it is then accepted if it is valid.
  ```

- **The agent's reading wins on a repeat.** Each (field, built value) mismatch is raised only once. If the agent rebuilds it unchanged, it is accepted and recorded as `kept_by_agent` in the trace. A wrong extraction can therefore cost one attempt, but it can never force an escalation.

**Not compared:** mineral model names. Mapping a name to a catalogue model is the knowledge being tested, so the build summary leaves that check to the agent.

**Cost.** One extra call per task with a short prompt, counted in the task's tokens.

**Dev runs, 3 Nov.** E did worse than C: 0.92 against 1.00 under METRICS v1.2 (0.90 against 0.97 under v1.1). Two things happened:
- **A wrong extraction was followed.** On p04 the request check read "30 methacrylate units and 10 MPEG methacrylate side chains" as a backbone of 30, when it is 30 + 10 = 40. The agent rebuilt to match in all 3 runs, instead of keeping its correct build.
- **A real mismatch was caught.** The check caught the c06 supercell change before the seed hint existed.

**Owner, 5 Nov: dropped.** It is reported as a negative result. The user-facing alternative is the build summary printed by `agents/run.py`; the person who wrote the request checks it.

**Checks without a model:**
- `tests/test_checks.py` (10 tests): a valid-but-wrong build (mock `wrongvalid`) is accepted by C and fails TC.2, while E catches it and fixes it in attempt 2, for a PCE, a mineral and a composite task. A misread request costs one attempt and the agent's build is then accepted. Replay is exact.
- `docs/HARNESS.md`: the same comparison on the whole dev split.

E is decided on dev data only. Keep it only if it beats C there; either way, report it as ablation E.

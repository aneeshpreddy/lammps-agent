# Single-call baseline (plan Days 23–24)

Code: `agents/baseline.py`. Harness: `eval/harness.py` (METRICS.md v1.1). Harness sanity checks: `docs/HARNESS.md`.

## What it is

The simplest system that follows design decision E (SPEC §7.3): **one model call per task, no tools, no validator feedback, no retry.**

- **Input:** the model receives the task's natural-language `input` and nothing else from the task (METRICS §1). The harness enforces this by passing `{"id", "input"}` only.
- **Output:** a builder spec as structured output (JSON schema in `agents/baseline.py`, `SCHEMA`):
  - builder `minerals`, `pce` or `composite`, plus the force field;
  - mineral model and supercell;
  - PCE monomers, composition, sequence, end groups, chains, counter-ion, box padding and seed;
  - surface model and supercell, height and orientation.
- **Build:** the deterministic builders turn the spec into the DATA FILE (`builders/dispatch.py`, the same entry point as the oracle and the future tool layer).
- **Coordinates:** the model never writes coordinate lines.

| A run fails when | Category |
|---|---|
| The model refuses, the answer is truncated or unparseable, or the spec is inconsistent | `NO_OUTPUT` |
| A builder refuses (missing parameters, PCE does not fit the surface cell, unknown model) | `NO_OUTPUT`, also counted as a builder refusal |
| The file fails a Tier 0–3 check | first failing property |
| The file is valid but is the wrong system | `TC_ONLY` |

**System prompt.** It is generated from the builders' documentation and the model database (`python -m agents.baseline --show-prompt` prints it), and contains:
- force-field coverage;
- the three builders and their fields;
- monomer kinds, including how APEG/HPEG/TPEG/VPEG and MPEG map to the fields;
- sequence modes;
- one line per INTERFACE cement-mineral model: cell, kind, surface normal, and the force fields that cover it.

Nothing in it is task-specific; `tests/test_harness.py` checks that no task text appears in it.

The agent loop (2–13 Nov) will add tools and validator feedback on top of the same builders. The difference between the two systems is then the value of the loop.

## Settings (recorded in every `results.json`, METRICS §5)

| Setting | Value | Source |
|---|---|---|
| Model | `claude-opus-5-5` (Claude Opus 5.5) | Claude API ID, models overview, fetched 2026-10-27 |
| Effort | `medium` (the model's documented default, set explicitly) | models overview 2026-10-27 |
| Thinking | adaptive, always on for this model (not configurable) | models overview 2026-10-27 |
| Sampling | API defaults (temperature is not settable on this model) | — |
| `max_tokens` | 16 000 | — |
| Output format | structured output, `output_config.format` JSON schema | — |
| Prompt caching | system prompt marked `cache_control: ephemeral` | — |
| Refusal fallback | **off**: a fallback model would change which model is measured; a refusal is a failed run | — |
| Prices | $4 / MTok input, $20 / MTok output, $5 / MTok 5-min cache write, $0.20 / MTok cache read | `eval/pricing.json`, pricing page fetched 2026-10-27 |
| Prompt version | `baseline-v1 (2026-10-27)`; system prompt and schema SHA-256 in `results.json` | — |
| SDK | `anthropic` 0.125.0 (Python 3.9 venv; the 1.x SDK needs Python ≥ 3.10) | — |

## Run it

The model is chosen in one place: the `model:` block of `config.yaml` (provider, model ID, effort, date). It stays PROVISIONAL until model access is decided with the supervisor (27 Oct). If the model changes, record the new ID and its prices from the docs on that day (`eval/pricing.json`) before running.

The API key is read from the environment and never written to a file (CLAUDE.md rule):

```bash
cd lammps-agent && source .venv/bin/activate
read -s ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY      # paste at the silent prompt; or: ant auth login
python scripts/api_smoke.py                                  # 1 tiny call: checks key, credit and model ID
python -m eval.harness --system baseline --split dev --repeats 3 --out runs/eval/baseline_dev
python -m eval.analyse runs/eval/baseline_dev --write-doc docs/BASELINE_RESULTS.md
```

- **Scope:** 13 dev tasks × 3 repeats = 39 calls.
- **Cost estimate:** about 4 k input and 2–6 k output tokens (including thinking) per call, so **about $0.10 per call and $3–5 for the dev run** with Opus 5.5 (about half that with Sonnet 5.5; prices of 2026-10-27). The run reports the measured cost.
- **Without credentials** the run stops at the first call with a message. No partial results are written as failed runs.
- **Saved per run** (plan Day 24): `system_prompt.txt` (the exact system prompt), and per task and repeat a `trace.json` with the request ID, the raw response text, the parsed answer, the builder spec, the score and the failing checks with their messages. The output DATA FILE is saved next to the trace. `results.json` and `summary.md` aggregate them.
- **Failure analysis** (plan Day 25, `eval/analyse.py`). The analysis writes `analysis.md` in the run folder and, with `--write-doc`, `docs/BASELINE_RESULTS.md`. It contains:
  - the success rate;
  - the tier distribution;
  - the failure categories;
  - every failure, with its validator messages and a field-by-field difference between the model's spec and the hidden spec (monomers compared by chemistry, not label);
  - a **suggested** gap type: formatting, knowledge, reasoning, pipeline, validator or infrastructure.

  The plan asks for the gap types to be confirmed by reading the failures (step 2), so the suggestions are a starting point.
  - Checked on the sanity systems: the spec corrupter gives 13 of 13 "reasoning", each with the exact perturbation; the file corrupter gives 13 of 13 "pipeline".
- **Test split:** not run before 16 Nov (the harness refuses).

## Status (2026-10-27)

- **Ready:** the code, the schema glue and the harness. With a mock "perfect model" that answers with the hidden spec, the baseline's own code path scores 1.00 on the dev split (`docs/HARNESS.md`). Its schema can therefore express every dev task, and its conversion to builder specs is faithful.
- **Not run:** no model access yet (`ANTHROPIC_API_KEY` unset). The supervisor is deciding how model access will be provided: a paid key, institute cloud credits, or a free open-weight model (27 Oct). Once decided, the scored dev run and its analysis are the commands above.

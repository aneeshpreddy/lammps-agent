# Experiments, results tables and the code freeze (plan Days 39–43)

Code: `eval/experiment.py` (runner and tables) and `scripts/freeze_config.py` (freeze record). Tests: `tests/test_experiment.py` and `tests/test_freeze.py`. Built on 28 Oct, before any model run. Every step from model access to tables is therefore one command.

## The systems (plan Day 42)

| Label | `--system` | What it is |
|---|---|---|
| A | `baseline` | single call, no tools, no feedback |
| B | `agent-nofeedback` | the loop with retries, but only "try again" after a failed attempt |
| C | `agent` | the loop with validator feedback (the agent) |
| D (optional) | `agent-tiers01` | feedback from Tier 0–1 checks only |
| E (optional) | `agent-checked` | C + build summary + request check (docs/AGENT.md) |

Every system uses the same model (`config.yaml` `model:`), the same tasks and the same repeats. The central claim is **B vs C**: the value of validator feedback.

## Running

```bash
# dev split, every system, 3 repeats -> runs/exp/dev_<timestamp>/<system>/ + results.md + figures/
python -m eval.experiment run --split dev --systems baseline agent-nofeedback agent agent-checked --write-doc docs/RESULTS_DEV.md

# tables again from finished runs (e.g. after adding a system)
python -m eval.experiment tables runs/exp/dev_<timestamp> --write-doc docs/RESULTS_DEV.md
```

- **One system at a time.** Each system is one harness evaluation (`eval/harness.py`). A system whose folder already holds `results.json` is kept, never overwritten. An interrupted experiment is continued by running the same command with `--out` set to the same folder.
- **Pipeline check without a model.** `--mock POLICY` or `--mock SYSTEM=POLICY …` (e.g. `baseline=perfect agent=wrongvalid agent-checked=wrongvalid`) runs scripted models. This checks the pipeline, never a result.

## The tables (plan Day 43)

`results.md` (and the `--write-doc` copy) contains:

1. **Success per system:** mean of per-task rates, spread across repeats (mean ± sd, min–max), pass@k, validity.
2. **Success by domain, difficulty and force field.**
3. **Ablation contrasts on the same tasks:** B vs A, C vs B, C vs A, C vs D, E vs C. Each gives the mean difference, the per-task better / same / worse counts, and an exact two-sided sign test.
   - With 13 dev or 9 test tasks, a sign test reaches p < 0.05 only with at least 6 tasks better and none worse.
   - The per-task counts are the honest summary. Claim only what they show (plan Day 44).
4. **Failure categories per system:** the first failing property, or NO_OUTPUT / TC_ONLY / INCOMPLETE.
5. **The baseline's failures:** for each A failure category, how often every other system succeeded on the same task and repeat.
6. **Inside the loop:** the first attempt's outcome as the loop saw it, against final success. This is the recovery view, including "accepted in attempt 1" runs that TC.2 rejects afterwards.
7. **Cost:** attempts, escalations, tokens, cost (priced with `eval/pricing.json`, whose date is cited), latency.

**Figures.** Two figures are written to `figures/` and copied next to the `--write-doc` file:
- task success per system: the bar is the mean and the dots are the individual repeats;
- task success by domain: one colour per system, fixed by its label (A–E), so colours never shift between runs.

**The validator table** (plan Day 43, item 4) is `docs/VALIDATOR_RESULTS.md`.

## Code freeze (plan Day 39)

At the freeze, after tagging `v1.0`:

```bash
python scripts/freeze_config.py          # writes docs/FROZEN_CONFIG.md and docs/FROZEN_CONFIG.json
python scripts/freeze_config.py --check  # later: lists anything that changed (exit 1), or "unchanged since the freeze"
```

**What is recorded:**
- model ID, effort, max_tokens, thinking and sampling;
- SHA-256 of the baseline and agent system prompts, the baseline schema, the request-check prompt and schema, and the tool definitions;
- the loop's limits, feedback mode and the E default;
- component versions;
- the hash of every declared configuration and calibration file;
- the split, task and METRICS hashes;
- the pricing record, LAMMPS, `config.yaml`, and the git commit and tag.

**Enforced:** `eval.experiment run --split test` refuses to start unless `--check` finds no difference. The commit itself is not compared, so documentation commits after the freeze are fine. Any change to a prompt, tool, limit, configuration or task blocks the test run.

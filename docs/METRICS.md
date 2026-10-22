# METRICS — how systems are scored on the eval set (plan Day 20)

Version 1.0, 2026-10-22. Frozen together with `eval/split.json`. Changing any definition below after
the first scored run requires a new version and re-scoring every system already reported.

## 1. What a system receives and returns

- **Input:** the task's `input` string only (natural language). `hidden_spec`, `reference`, `tc_mode` and
  `expected_counts` are never shown to the system under test.
- **Output:** one LAMMPS DATA FILE path, plus a trace (prompts, responses, tool calls, timings, token usage).
- A system may decline a task (no file). A declined task scores as a failure with category `NO_OUTPUT`.

## 2. Task success (the headline metric)

A run of task *t* **succeeds** iff both hold:

1. **Valid:** the validator returns `passed = true` for the output under the task's `declared_config`:
   every Tier 0–3 check is PASS or NOT_APPLICABLE (PROPERTIES §8.2). FAIL, NOT_EVALUATED and NOT_CALIBRATED
   all count as not valid.
2. **Correct:** TC.2 against the task's reference returns PASS in the task's `tc_mode`:

| `tc_mode` | Used for | Equivalent when |
|---|---|---|
| `graph` | minerals (with `tc_compare_cell`), PCE with a deterministic sequence (alternating, block, explicit) | same header counts (atoms, bonds, angles, dihedrals, impropers); identical multiset of molecules, each identified by a Weisfeiler–Lehman hash (24 rounds) of its bond graph labelled by atom-type name and charge (3 decimals); for minerals also the same cell lengths and tilt within 1e-3 Å |
| `chemistry` | PCE with a random or gradient sequence | same header counts; per molecule the same multiset of (atom-type name, charge), the same net charge and the same counts of bonded type pairs. Positions and monomer order are free: any draw of the requested architecture is correct |
| `positions` | not used in v2 (kept for tasks whose geometry is fixed by the request) | atoms matched by minimum-image position; types, charges, topology, coefficients and cell equal |

Neither criterion alone is enough: a file can pass every tier and still be the wrong system, and a correct
system written with a defect fails Tier 0–3 (plan Day 20 "watch out").

## 3. Repeats and aggregation

- **Repeats:** 3 runs per task on the dev split; 5 per task on the test split (plan Days 24, 41). Each
  repeat is a fresh run (no shared state); record the model's sampling settings.
- **Per-task success rate** = successes / repeats. **System success rate** = mean of per-task rates
  (each task weighs the same), reported with the **spread across repeats**: for repeat *k*, the success
  fraction over tasks; report mean ± standard deviation of those *k* fractions and the min–max.
- Report the rate overall and broken down by **difficulty**, **domain** (pce / mineral) and **force
  field** (class I / class II).
- **pass@k** (k = repeats): fraction of tasks with at least one success — reported, never as the headline.

## 4. Diagnostic metrics

| Metric | Definition |
|---|---|
| Validity rate | fraction of runs with `passed = true`, whatever TC says |
| Tier-reached distribution | histogram of `tier_reached` (−1 … 3) over runs |
| First failing property | for failed runs: the lowest-tier FAIL (property ID); categories `NO_OUTPUT`, `TC_ONLY` (valid but not equivalent), or the property |
| Per-failure-mode incidence | for each FM in FAILURE_MODES, the fraction of runs whose failing properties map to it (§9.1 Property column) |
| Recovery rate (agent only) | among runs whose first attempt failed, the fraction that end in success |
| Correction iterations | number of generation attempts until success or stop (agent only; baseline = 1) |
| Tokens per task | input and output tokens summed over all model calls of a run (from the API response usage fields) |
| Cost per task | tokens × the provider's list price **on the run date** (cite the pricing page and date) |
| Latency | wall-clock seconds from task start to final file, including validation |
| Builder refusals | runs in which a builder refused (missing parameters or non-finite output); counted, and they are failures |

## 5. Fixed conditions (recorded with every scored run)

- Validator version (git commit) and `config_version` of each declared configuration; calibration files
  and their dates; LAMMPS build (`docs/lammps_build.txt`, Homebrew 22 Jul 2025 – Update 6, serial).
- Model ID, date, sampling parameters, system prompt version (hash), tool definitions (hash), limits
  (steps, attempts, tokens, time).
- `eval/split.json` hash (LOG.md 2026-10-22).

## 6. Rules

- The **test split is not opened** (no runs, no reading of failures) until 16 Nov (plan Day 41).
- Tuning (prompts, tools, limits) uses the dev split only; every change is logged with its dev score.
- A reference that turns out to be wrong is fixed only with a logged reason; every system is then
  re-scored on that task.
- Baseline and agent are scored on the same tasks, repeats and fixed conditions.

# Frozen configuration (plan Day 39)

Recorded 2026-11-06T02:01:15 by `scripts/freeze_config.py` · git eacb286 · tag v1.0. From now on only bug fixes that block evaluation are allowed; `python scripts/freeze_config.py --check` lists anything that changed, and `eval/experiment.py` refuses to run the test split if it finds a difference.

| Item | Frozen value |
|---|---|
| Model | `claude-sonnet-5-5` (anthropic), effort medium, max_tokens 16000, thinking adaptive (model default), sampling API defaults |
| Baseline prompt | baseline-v3 (2026-11-06); system `7d40278c68cf5329…`, schema `1c91f609f58bba49…` |
| Agent prompt | system `e14dbcc75171d55d…` |
| Request check (E) | prompt `a17c0aaddba80542…`, schema `618d0337a9bc0462…`, checks-v1 (2026-10-28) |
| Tools | tools-v1 (2026-10-27): build_data_file, get_model_info, get_reference_example; definitions `2e869096603062c9…` |
| Loop | loop-v2 (2026-11-06); feedback full; checks by default False; build summary by default False; limits max_attempts 3, max_steps_per_attempt 12, max_tokens_per_task 400000, max_wall_s 1200, tool_timeout_s 300 |
| Validator | 1.0.0; 9 declared configurations, 8 calibration files (hashes in FROZEN_CONFIG.json) |
| Eval set | split `063c2ddad24be986…`, tasks `74e32c43ced9c9a7…`, METRICS.md `cf4aed9c99e9ace4…` |
| Prices | https://platform.claude.com/docs/en/about-claude/pricing (and models/overview), fetched 2026-10-27, re-checked unchanged 2026-11-03 (2026-11-03) |
| LAMMPS | Large-scale Atomic/Molecular Massively Parallel Simulator - 22 Jul 2025 - Update 6 |
| config.yaml | `16456ea11c6f44d7…` |

Full values: `docs/FROZEN_CONFIG.json`.

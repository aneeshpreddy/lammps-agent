# CLAUDE.md — handoff for this repository

Project: an agentic AI that generates LAMMPS DATA FILEs (structure + topology) for cementitious systems. **System class (supervisor, 2026-10-20 and 2026-10-26, SPEC §7.3/§7.16/§7.17): PCE superplasticisers of any architecture (in a box slightly bigger than the atoms) + all INTERFACE FF 1.5 cement minerals + PCE on a cement-mineral surface, in CVFF-INTERFACE (class I) and PCFF-INTERFACE (class II).** "Main chains" = backbone length. Builders: `builders/pce.py`, `builders/minerals.py`, `builders/composite.py`. Eval tasks: `eval/tasks/` (v3, 22 tasks), overview `docs/EVAL_SET.md`. The deterministic validator is the contribution. Plan: `../LAMMPS_Agent_Daywise_Plan.pdf` (30 Sep – 21 Nov 2026). Spec: `docs/SPEC.md`, `docs/PROPERTIES.md`, `docs/FAILURE_MODES.md` (v0.6). `../Specs/` is the frozen v0.3a snapshot; edit `docs/`, not `../Specs/`.

## Build order (do not skip ahead)
validator (done; Gate 1 passed, owner 22 Oct) → eval set (v3: 22 tasks PCE + minerals + composites, both force fields; METRICS.md v1.1 and split v2 frozen 26 Oct — do NOT open the test split before 16 Nov; harness next) → single-call baseline (26–28 Oct) → tool layer → agent loop (2–13 Nov, code freeze 13 Nov) → evaluation (16–18 Nov) → write-up.

## Rules
- The validator never uses ASE, pymatgen or the LLM to reach a verdict. ASE and pymatgen are allowed only as converters under test or for cross-checks.
- Never write into `data/reference/` (the files are read-only). Corrupted variants go to `data/corrupted/`.
- No tolerance without a derivation. A property without a tolerance returns NOT_CALIBRATED, and that never counts as PASS. Record new tolerances in `calibration/*.json` through `scripts/calibrate.py`.
- "LAMMPS would catch it" never satisfies a property (PROPERTIES §8.8).
- Owner decisions (OD-B…OD-N, S-Q1…S-Q7) are not yours to take. Use the provisional values in `configs/*.yaml` and list them (SPEC §7.14).
- The orchestrator will always run the validator after each generation attempt. Do not expose it as an optional agent tool.
- Record model IDs and prices from the docs on the day you use them, never from memory.

## Commands
```bash
source .venv/bin/activate
pytest -q
python -m validator FILE [--declared configs/X.yaml] [--coeff-file F] [--reference REF] [--json] [--no-tier3]
python scripts/calibrate.py && python scripts/mutate.py && python scripts/run_matrix.py
```
LAMMPS: `lmp_serial` (Homebrew, 22 Jul 2025 – Update 6). Its PPPM segfaults on many valid boxes (use Ewald), and `replicate … bond/periodic` builds wrong bonds in tilted cells (use `scripts/supercell.py`) — FAILURE_MODES §9.6. Probe IDs T1–T39 in the docs refer to an earlier `source_audit/` folder that is not on this machine.

## End every working day
Commit, then add three lines to `docs/LOG.md` (done / not done / tomorrow), following Appendix C.

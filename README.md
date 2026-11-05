# lammps-agent — validator for LAMMPS DATA FILEs

A deterministic validator for LAMMPS DATA FILEs (`read_data` input). It is the first component of an agentic system that will generate those files for cementitious systems. The validator does not use the LLM, and it does not use the converters it checks (ASE, pymatgen, msi2lmp): it has its own parser, built from the LAMMPS `read_data` source.

Specification: `docs/SPEC.md`, `docs/PROPERTIES.md` (44 properties in Tiers 0–3, plus 2 task-correctness properties), `docs/FAILURE_MODES.md` (35 failure modes). Current results: `docs/VALIDATOR_RESULTS.md`.

| Tier | Question | Examples |
|---|---|---|
| 0 | Can the file be parsed? | header keywords, section names, numeric syntax, Atoms columns, 254-character lines, missing box lines |
| 1 | Is it internally consistent? | counts vs rows, unique IDs, topology references, Masses and Coeff rows, image flags, topology-type signatures, bonded-term completeness |
| 2 | Is it physically plausible? | net charge, cell consistency, overlaps, bond lengths, density, mass ↔ element, image consistency, tilt bound, bond coefficients vs geometry, box margin |
| 3 | Does LAMMPS accept it under the declared configuration? | `read_data … nocoeff`; the full force field + `run 0`; warning policy; crash/timeout classification |
| TC | Does it match the request or a reference? | comparison with a trusted reference: by position, by molecular graph, or by chemistry (position- and sequence-free) |

## Structure builders (agent tools)

```bash
python -m builders.pce examples/pce/mpeg_methacrylate.json --ff pcff --out runs/pce     # any PCE architecture
python -m builders.pce examples/pce/hpeg.json --ff cvff --out runs/pce                  # class I
python -m builders.minerals tob11_unit_cell --supercell 2 2 1 --ff pcff --out runs/minerals
python -m builders.minerals --list                                                      # all INTERFACE models
python -m builders.composite examples/composite/tob11_004_small.json --out runs/composite  # PCE on a mineral surface
python scripts/pce_examples.py            # docs/PCE_BUILDER.md  (every example, both force fields, validated)
python scripts/composite_examples.py      # docs/COMPOSITE.md    (PCE on surfaces, both force fields, validated)
python scripts/build_eval_set.py          # eval set v3: eval/tasks/*.json + data/reference/eval_v3/ + docs/EVAL_SET.md
# eval/split.json is frozen (scripts/make_split.py; extended 2026-10-26 with --extend); success: docs/METRICS.md
python scripts/build_mineral_references.py   # docs/MINERALS.md (every cement mineral, both force fields)
```

## Use the agent: one request in plain English

```bash
export ANTHROPIC_API_KEY=...        # in ~/.zshrc or the terminal, never in the repo
python -m agents.run "Build a LAMMPS data file in PCFF-INTERFACE for an MPEG-type PCE with 12 methacrylic acid units (all deprotonated) and 4 methoxy-PEG methacrylate side chains of 10 EO units, alternating, calcium counter-ions." --out runs/requests/my_pce
python -m agents.run --file request.txt --out runs/requests/my_system
```

The command prints one sentence saying what was built ("Built: PCE (PCFF-INTERFACE), 1 chain(s), each 16 backbone units …"). It writes `system.data` only if every Tier 0–3 check passed, including LAMMPS with the full force field; otherwise it writes a `REPORT.md` of what was tried. Read the sentence against your request: the validator certifies that the file is valid, not that it is the system you meant. The agent uses the `config.yaml` defaults (model, feedback, limits); a request costs about 1–3 cents.

## Evaluation: harness, baseline, agent, experiments

```bash
python scripts/harness_checks.py                                  # docs/HARNESS.md: oracle / corrupters / mock baseline and agents on dev
python scripts/api_smoke.py                                       # one tiny model call: is the key working?
python -m agents.baseline --show-prompt                           # the baseline's system prompt and output schema
python -m eval.harness --system baseline --split dev --repeats 3 --write-doc docs/BASELINE_RESULTS.md   # needs ANTHROPIC_API_KEY
python -m eval.analyse runs/eval/<run>/ --write-doc docs/BASELINE_RESULTS.md                           # failure analysis
python -m eval.experiment run --split dev --systems baseline agent-nofeedback agent --write-doc docs/RESULTS_DEV.md
python scripts/freeze_config.py [--check]                         # code freeze record: docs/FROZEN_CONFIG.md
```

The harness refuses the test split before 16 Nov and checks the split and task files against the frozen hashes (METRICS.md). The experiment runner also refuses the test split unless the configuration is unchanged since the code freeze. Design and settings: `docs/BASELINE.md` (baseline), `docs/TOOLS.md` (tools), `docs/AGENT.md` (agent loop, the dropped variant E), `docs/EVALUATION.md` (experiments, tables, freeze).

PCE files are written in a box slightly bigger than the atoms (2 Å per face; supervisor 2026-10-26, checked by P2.10). Force fields: CVFF-INTERFACE (class I) and PCFF-INTERFACE (class II), INTERFACE FF 1.5. The builders refuse to write a file when the force field lacks a parameter (other than class II cross terms) or when msi2lmp writes a non-finite value.

## Reproduce the results from a clean checkout

1. Install (below), including LAMMPS, and check that `pytest -q` passes.
2. Validator table: `python scripts/run_matrix.py` regenerates `docs/VALIDATOR_RESULTS.md`. It takes about 15 minutes, for 996 files.
3. Harness checks: `python scripts/harness_checks.py` regenerates `docs/HARNESS.md`. These use no model.
4. Model runs: set `ANTHROPIC_API_KEY` in the environment, never in a file. Check it with `python scripts/api_smoke.py`. The model is the one in `config.yaml` → `model:`.
5. Development experiment: `python -m eval.experiment run --split dev --systems baseline agent-nofeedback agent --write-doc docs/RESULTS_DEV.md`.
6. Test experiment: `python scripts/freeze_config.py --check` must report no change since the freeze. Then run the same command with `--split test` and `--write-doc docs/RESULTS_TEST.md`.

Prices come from `eval/pricing.json`, which is dated. Results differ between runs because model sampling is not deterministic; the tables report the spread across repeats. Everything else (builders, validator, scoring) is deterministic.

## Install

```bash
cd lammps-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Two data folders sit next to the repository, not in it.** The builders read them from the repository's parent folder:

```
UGRP/
├── lammps-agent/        this repository
├── INTERFACE_FF_1_5/    INTERFACE FF 1.5: FORCE_FIELDS/*.frc and MODEL_DATABASE/ (from its authors, the Heinz group)
└── CEMENT_MINERALS/     the research group's cement-mineral .car/.mdf models
```

They are not redistributed here. Without them, the builders, the agent and every test that builds a structure fail. The validator alone (`python -m validator`) works without them.

You also need LAMMPS. On macOS: `brew install lammps`. On first use, the builders compile `msi2lmp` from the Homebrew LAMMPS sources into `build/msi2lmp/`. That needs the Xcode command-line tools (`xcode-select --install`). The Homebrew executables are `lmp_serial` and `lmp_mpi`; set `lammps.executable` in `config.yaml`. The build used for every result in `docs/` is recorded in `docs/lammps_build.txt` (22 Jul 2025 – Update 6, with CLASS2, KSPACE and MOLECULE).

## Validate a file

```bash
python -m validator data/reference/REF-01.data                # uses the sidecar REF-01.json
python -m validator my.data --declared configs/emc_pcff_real_full.yaml --coeff-file my.params
python -m validator my.data --reference data/reference/REF-01.data --json   # adds TC.2
python -m validator my.data --no-tier3                        # skip LAMMPS
```

The exit status is 0 if every file passes, 1 if any file fails, and 2 if any result is incomplete (NOT_CALIBRATED or NOT_EVALUATED).

From Python:

```python
from validator import validate
from validator.registry import config_for
res = validate("x.data", config_for("x.data"), reference=None)
res.passed, res.verdict, res.tier_reached, res.failing(), res.to_json()
```

Every result follows the `ValidationResult` schema (plan Appendix B). Each check carries `property` (e.g. `P2.1`), `tier`, `verdict` (PASS · FAIL · NOT_EVALUATED · NOT_CALIBRATED · NOT_APPLICABLE), `message` and `details`. `lammps.errors` holds the ERROR lines that LAMMPS printed.

## Configuration

- `config.yaml` (project): the LAMMPS executable, the backend (`local` · `ssh` · `docker`), the timeout, and the default declared configuration.
- `configs/*.yaml`: the declared validation configuration records (SPEC §7.10). These set the units, atom_style, boundary and styles, and the policies for image flags, wrapping, tilt, charge, encoding and the warning allow-list. **The project owner accepted every value on 2026-11-05** (SPEC §7.14).
  - `interface_pcff_tobermorite.yaml`: **the primary system** — bulk tobermorite, PCFF-INTERFACE (status ACCEPTED, SPEC §7.3, §7.14). Default in `config.yaml`.
  - `emc_pcff_real_full.yaml`: for the EMC/PCFF PCE references (status ACCEPTED; regression set).
  - `interface_pcff_fixture.yaml`: for the synthetic tobermorite fixtures (status SYNTHETIC).
- `calibration/*.json`: the Tier 2 tolerances, with the reference IDs, SHA-256 checksums and the basis for each value. Rebuild them with `python scripts/calibrate.py`.
- Each data file has a sidecar `<name>.json` that names its declared configuration and per-file overrides (for example the coefficient file).

## Regenerate the validator's inputs (details for step 2 above)

```bash
pytest -q                              # unit tests (Tier 3 tests need lmp_serial)
python scripts/make_fixtures.py        # triclinic fixtures from the raw msi2lmp output
python scripts/build_references.py base eval crosscheck   # tobermorite references REF-05..08, eval refs t01–t14
python scripts/evidence_runs.py        # docs/REFERENCE_EVIDENCE.md (short MD + extensivity, ~1 min)
python scripts/calibrate.py            # calibration/pce_emc.json, calibration/tobermorite_fixture.json
python scripts/mutate.py               # data/corrupted/: negative controls (948 on 2026-10-26) + manifest.json
python scripts/run_matrix.py           # docs/VALIDATOR_RESULTS.md, docs/validator_matrix.csv  (~15 min)
python scripts/reproduce_r13.py        # docs/R13_ASE_ROUNDTRIP.md (ASE round trip)
```

`data/corrupted/*.data` and `data/converted/` are not tracked in git, because the scripts regenerate them deterministically. The sidecars record the SHA-256 of every file.

## Layout

See plan Appendix A. `validator/` holds the parser and Tiers 0–3, TC, the backends and the configuration. `scripts/` holds the fixture, calibration, mutation, matrix and R13 tools, and `tests/` holds the unit tests. `data/reference/` holds the candidate references (read-only) and `provenance.md`. `data/fixtures/` holds the synthetic tobermorite fixtures. `templates/` holds the Tier 3 input templates. `eval/` holds the tasks, the frozen split and the harness. `agents/` holds the single-call baseline, the agent loop, variant E's checks and the scripted mock models. `tools/` holds the agent's tool layer (`docs/TOOLS.md`); `agent/` is an empty placeholder.

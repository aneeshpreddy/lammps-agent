# lammps-agent — validator for LAMMPS DATA FILEs

A deterministic validator for LAMMPS DATA FILEs (`read_data` input). It is the first component of an agentic system that will generate those files for cementitious systems. The validator does not use the LLM, and it does not use the converters it checks (ASE, pymatgen, msi2lmp): it has its own parser, built from the LAMMPS `read_data` source.

Specification: `docs/SPEC.md`, `docs/PROPERTIES.md` (42 properties in Tiers 0–3, plus 2 task-correctness properties), `docs/FAILURE_MODES.md` (35 failure modes). Current results: `docs/VALIDATOR_RESULTS.md`.

| Tier | Question | Examples |
|---|---|---|
| 0 | Can the file be parsed? | header keywords, section names, numeric syntax, Atoms columns, 254-character lines, missing box lines |
| 1 | Is it internally consistent? | counts vs rows, unique IDs, topology references, Masses and Coeff rows, image flags, topology-type signatures, bonded-term completeness |
| 2 | Is it physically plausible? | net charge, cell consistency, overlaps, bond lengths, density, mass ↔ element, image consistency, tilt bound |
| 3 | Does LAMMPS accept it under the declared configuration? | `read_data … nocoeff`; the full force field + `run 0`; warning policy; crash/timeout classification |
| TC | Does it match the request or a reference? | position-matched comparison with a trusted reference |

## Install

```bash
cd lammps-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

You also need LAMMPS. On macOS: `brew install lammps`. The Homebrew executables are `lmp_serial` and `lmp_mpi`; set `lammps.executable` in `config.yaml`. The build used for every result in `docs/` is recorded in `docs/lammps_build.txt` (22 Jul 2025 – Update 6, with CLASS2, KSPACE and MOLECULE).

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
- `configs/*.yaml`: the declared validation configuration records (SPEC §7.10). These set the units, atom_style, boundary and styles, and the policies for image flags, wrapping, tilt, charge, encoding and the warning allow-list. **Every value is provisional until the project owner decides** (SPEC §7.14).
  - `interface_pcff_tobermorite.yaml`: **the primary system** — bulk tobermorite, PCFF-INTERFACE (status PROVISIONAL_DEFAULT, SPEC §7.3). Default in `config.yaml`.
  - `emc_pcff_real_full.yaml`: for the EMC/PCFF PCE references (status PROVISIONAL; regression set).
  - `interface_pcff_fixture.yaml`: for the synthetic tobermorite fixtures (status SYNTHETIC).
- `calibration/*.json`: the Tier 2 tolerances, with the reference IDs, SHA-256 checksums and the basis for each value. Rebuild them with `python scripts/calibrate.py`.
- Each data file has a sidecar `<name>.json` that names its declared configuration and per-file overrides (for example the coefficient file).

## Reproduce the results

```bash
pytest -q                              # 77 unit tests (Tier 3 tests need lmp_serial)
python scripts/make_fixtures.py        # triclinic fixtures from the raw msi2lmp output
python scripts/build_references.py base eval crosscheck   # tobermorite references REF-05..08, eval refs t01–t14
python scripts/evidence_runs.py        # docs/REFERENCE_EVIDENCE.md (short MD + extensivity, ~1 min)
python scripts/calibrate.py            # calibration/pce_emc.json, calibration/tobermorite_fixture.json
python scripts/mutate.py               # data/corrupted/: 264 negative controls + manifest.json
python scripts/run_matrix.py           # docs/VALIDATOR_RESULTS.md, docs/validator_matrix.csv  (~2 min)
python scripts/reproduce_r13.py        # docs/R13_ASE_ROUNDTRIP.md (ASE round trip)
```

`data/corrupted/*.data` and `data/converted/` are not tracked in git, because the scripts regenerate them deterministically. The sidecars record the SHA-256 of every file.

## Layout

See plan Appendix A. `validator/` holds the parser and Tiers 0–3, TC, the backends and the configuration. `scripts/` holds the fixture, calibration, mutation, matrix and R13 tools, and `tests/` holds the unit tests. `data/reference/` holds the candidate references (read-only) and `provenance.md`. `data/fixtures/` holds the synthetic tobermorite fixtures. `templates/` holds the Tier 3 input templates. `tools/`, `agent/` and `eval/` are placeholders for the later phases.

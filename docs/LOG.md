# Project Log

The entire specification phase was drafted in a single AI-assisted session on 2026-09-30, ahead of the planned 30 Sep – 3 Oct schedule. The 2026-10-01 to 2026-10-03 entries record that their planned work was brought forward; no work is claimed on those dates.

---

## 2026-09-30 — SPEC: Task Boundary (and full phase draft)

### Done
- Drafted `docs/SPEC.md`, `docs/PROPERTIES.md`, `docs/FAILURE_MODES.md`, `docs/SPEC_SUMMARY.md`, `data/reference/provenance.md` (template only).
- Research pass: LAMMPS read_data, run, Howto_triclinic, atom_style docs; ASE lammpsdata source; pymatgen LAMMPS I/O docs; arXiv 2603.20630, 2605.08941, 2606.09422, 2607.22596, 2604.02537.
- **Correction pass (v0.1 → v0.2).** Re-fetched the LAMMPS read_data and atom_modify docs (release built 30Sep2026) and checked C-S-H model citations. Changes:
  1. Duplicate-ID claim re-sourced: the read_data "incomplete check" remark applies only to `read_data … add merge`; the general statement now rests on the atom_modify doc ("They should also be unique, though LAMMPS does not check for this").
  2. Added P0.7 (line after a section keyword is always skipped by LAMMPS) and FM26.
  3. Added P0.8 (box keywords must be explicit; LAMMPS silently defaults lo/hi to −0.5/0.5) and FM25.
  4. Added P0.9 (topology and Velocities sections must follow Atoms).
  5. Corrected P1.7: PairIJ Coeffs requires N(N+1)/2 lines, not one per type.
  6. Corrected image-flag reset wording: non-periodic flags are reset **with a warning**, not silently.
  7. P1.12: strict `< hi` rule for fixed boundaries now VERIFIED (was partly UNVERIFIED).
  8. P2.7: impossibility of fully consistent image flags in infinite periodic bonded crystals now VERIFIED in current docs; applicability restricted to declared unwrapped-coordinate uses.
  9. Added note that tilted dimensions should be periodic (LAMMPS may lose atoms otherwise).
  10. P1.3 now marked dependent on atom_style (type column position differs by style); "style-agnostic" start list corrected.
  11. Property count corrected: 34 properties across Tiers 0–3 + 2 TC (v0.1 stated 30).
  12. Novelty statements narrowed to "among the works reviewed"; Paimon's lightweight deterministic structure summary acknowledged.
  13. Scope rules not decided by the owner (box kinds, unsupported styles) relabelled RECOMMENDATION (provisional).
  14. Brick-model citation confirmed (Kunhi Mohamed, Parker, Bowen, Galmarini, Cem. Concr. Res. 107 (2018) 221–235); pyCSH venue confirmed (Cem. Concr. Res. 183 (2024) 107593); ERICA FF and cemff added as force-field **options** under OD-C2 (author lists still to be confirmed).
  15. Added OD-K (type-label support).
  16. Removed specific MDGym/Paimon benchmark figures not re-verified in the correction pass.

### Not Done
- Owner decisions OD-B to OD-K.
- Reference collection (REFERENCE COLLECTION REQUIRED).
- Supervisor review.
- Reproduction of the R13 ASE round-trip report.
- Broader literature search for existing DATA FILE validators / converter test suites.
- Full re-read of LAMMPS docs R2–R8 and Claude docs R14–R16.

### Open Questions
- OD-B … OD-K and S-Q1 … S-Q6 (see `SPEC.md` §7.4, §7.9).

### Tomorrow
- Obtain owner answers to OD-B, OD-C1–C3, OD-G.
- Identify which group DATA FILEs are production-proven and who holds them.

### Hours
- To be filled by project owner.

---

## 2026-10-01 — SPEC: Properties

### Done
- Not yet reached. Planned work (correctness properties, tiers, tolerance policy) was completed early on 2026-09-30.

### Not Done
- Owner review of property IDs and tier assignments.
- Tolerance calibration (requires references).

### Open Questions
- S-Q1, S-Q2, S-Q3, OD-H.

### Tomorrow
- —

### Hours
- To be filled by project owner.

---

## 2026-10-02 — SPEC: Failure modes, oracle, references

### Done
- Not yet reached. Planned work (failure modes, oracle definition, provenance template) was completed early on 2026-09-30.

### Not Done
- Reference collection.
- R13 reproduction.

### Open Questions
- Which group files are production-proven, and who holds them?

### Tomorrow
- —

### Hours
- To be filled by project owner.

---

## 2026-10-03 — SPEC: Consolidation / review

### Done
- Not yet reached. Cross-document consistency audit and correction pass were performed on 2026-09-30.

### Not Done
- Owner and supervisor sign-off.
- Resolution of blocking decisions.

### Open Questions
- Start the validator phase on 2026-10-05 with the style-agnostic Tier 0/1 subset only (see `SPEC_SUMMARY.md` §9)?

### Tomorrow
- Validator phase from 2026-10-05 (conditional on the above).

### Hours
- To be filled by project owner.

---

## 2026-10-02 — Environment setup + LAMMPS source audit (actual work, AI-assisted)

### Done
- Installed Homebrew and LAMMPS on the owner's Mac (macOS 26.7.1, arm64). `brew install lammps` installed 22 Jul 2025 – Update 6 (formula `20250722-update6`). Executables are **`lmp_serial` / `lmp_mpi`** (CLAUDE.md §8 says `lammps_serial` / `lammps_mpi`; that needs correcting). MOLECULE and KSPACE are installed. `lmp_serial -h` output saved as `source_audit/lammps_build.txt`.
- Smoke test: a 2-atom `atom_style full` file with `kspace_style ewald` and `run 0` exited 0 with finite energy.
- Fetched the LAMMPS source at tag `stable_22Jul2025_update6` (commit `9c5ab448c`, `src/` and `src/MOLECULE/` only). This is the tag Homebrew built from (`sbom.spdx.json`).
- Read `read_data.cpp`, `atom.cpp`, `atom_vec*.cpp`, `utils.cpp`, `domain.cpp` (parts), `kspace.cpp` (parts), `special.cpp` (one function), `write_data.cpp` (one line), and `ntopo_bond_all.cpp` (messages).
- Ran 64 synthetic probe files on `lmp_serial` (serial, `newton_bond on`): `source_audit/probe.py`, `probe2.py`, `probe3.py`, `probe3b.py`, with results `probe*_results.txt`.
- Wrote `source_audit/SOURCE_AUDIT.md` (a verdict for every FM and property in v0.2).
- Produced spec set **v0.3a** in `Specs v0.3a (source-audited)/`. The v0.2 originals are unchanged.

### Change log v0.2 → v0.3a
1. **FAILURE_MODES:**
   - Every mode now records the LAMMPS behaviour on this build, the source lines and the probe IDs.
   - "Reproduced?" is now Yes for 16 of the 26 v0.2 modes, and for all 9 new modes.
   - FM05, FM18, FM20, FM21 and FM26 are no longer UNVERIFIED.
   - FM03, FM07, FM09, FM10, FM11, FM13, FM14 and FM24 were corrected or refined.
   - **New FM27–FM35:** surplus final row; dangling topology ID (crash); velocity coverage; negative molecule IDs; Masses duplicates/gaps; Coeff duplicates/gaps; misleading style comment; duplicate header keyword; non-standard numbers.
   - Added §9.4, corruption operators for negative controls.
   - Totals are now 35 modes / 33 in scope.
2. **PROPERTIES:**
   - Added a "LAMMPS if violated" column.
   - **New P0.10** (header keyword uniqueness), **P0.11** (no surplus rows), **P0.12** (encoding/line endings, policy OPEN), **P1.15** (units hint), **P3.4** (process outcome: clean/error/crash/timeout).
   - P1.4 and P1.7 now require each type ID exactly once.
   - P1.12 triclinic containment resolved: fractional coordinates, 0 ≤ s < 1.
   - P2.8 now records the doc/source disagreement on tilt.
   - P3.2 now requires every thermodynamic value to be finite.
   - New §8.7 (parser grammar from source), §8.8 (do not rely on LAMMPS for), §8.9 (verified message strings).
   - Totals are now 40 properties + 2 TC.
3. **SPEC:**
   - §7.7 facts verified against the source; two corrected (style comment, tilt) and six added.
   - New outcome categories CRASH and LOUD@RUN.
   - Non-goal 11 added.
   - New open items OD-L, OD-M, OD-N and S-Q7.
   - New §7.10 (declared validation configuration record), §7.11 (build policy), §7.12 (evaluation design, RECOMMENDATION), §7.13 (risks).
4. **SPEC_SUMMARY:** updated counts and key findings.
5. **provenance.md:** executable names corrected; build/run-mode fields and v0.3a admission rules added.

### Not Done
- Owner decisions OD-B … OD-N, S-Q1 … S-Q7. No decision was taken or implied.
- Reference collection.
- ASE/pymatgen claims were not re-checked (ASE not installed); R13 reproduction is still pending.
- The failure-mode experiments described in CLAUDE.md (`experiments/fm_verification/`) were not re-run. That folder was not found on this Mac.
- MPI and `newton_bond off` behaviour, `read_data … add`, type labels, and sections larger than 1024 rows were not probed.
- Prior-work figures (SPEC §7.6) were not re-checked.
- Supervisor review of v0.3a.

### Open Questions
- Is there a separate v0.3 (per CLAUDE.md) to merge with v0.3a?
- Which LAMMPS build is authoritative for Tier 3: the local Homebrew Update 6, or the group/cluster build (OD-F)?
- Tilt policy (OD-N); encoding policy (OD-M); units hint on line 1 (S-Q7).

### Tomorrow
- Owner review of v0.3a. Update CLAUDE.md §8 executable names. Locate `experiments/fm_verification/` and re-run it with `LMP=lmp_serial`.

### Hours
- To be filled by project owner.

---

## 2026-10-16 — VALIDATOR phase: plan Days 5–15 (actual work, AI-assisted, one session)

No work is recorded for 5–15 October; everything below was done on 2026-10-16. The repository is `UGRP/lammps-agent/` (plan Appendix A). `UGRP/Specs/` is left untouched as the v0.3a snapshot; the living copies are `docs/*.md` (now v0.4) and `data/reference/provenance.md`.

| Plan day | Deliverable | Where |
|---|---|---|
| D5 (5 Oct) repo, env, LAMMPS, interface | repo + `.gitignore`, `.venv` (Python 3.9.6; numpy 2.0.2, PyYAML, pytest, ASE 3.26.0 for cross-checks only), `config.yaml`, `docs/lammps_build.txt` (`lmp_serial -h`), `validate(path, cfg) -> ValidationResult`, own parser | `validator/core.py`, `validator/parser.py`, `validator/result.py` |
| D6 Tier 0 | P0.1–P0.12, one malformed tiny file per rule | `validator/tier0.py`, `tests/test_tier0.py` |
| D7–D8 Tier 1 | P1.1–P1.15 + new P1.16 (topology-type signatures) and P1.17 (bonded-term completeness) | `validator/tier1.py`, `tests/test_tier1.py` |
| D9 + D11 Tier 2 | P2.1–P2.8; triclinic-safe minimum image and linked-cell neighbour search (tested against brute force); calibration from references first | `validator/tier2.py`, `validator/geometry.py`, `scripts/calibrate.py`, `calibration/*.json` |
| D10 review | PROPERTIES v0.4 §8.10 implementation status, §8.11 calibration record | `docs/PROPERTIES.md` |
| D12 Tier 3 | 3a `read_data … nocoeff`, 3b EMC force-field block + `run 0`; ERROR/WARNING capture; CLEAN/ERROR/CRASH/TIMEOUT classification | `validator/tier3.py`, `templates/` |
| D13 backends | Local (tested); SSH and Docker (written, untested) — selected by `lammps.backend` | `validator/backends.py` |
| D14 corrupted set | 49 operators, 34 failure modes, 264 files from 6 parents, manifest + sidecars | `scripts/mutate.py`, `data/corrupted/` |
| D15 prove it | matrix over positives, natural negatives, corrupted files; LAMMPS-alone comparison | `scripts/run_matrix.py`, `docs/VALIDATOR_RESULTS.md`, `docs/validator_matrix.csv` |
| SPEC §7.13 | R13 reproduction (ASE round trip on REF-01/REF-04) | `scripts/reproduce_r13.py`, `docs/R13_ASE_ROUNDTRIP.md` |

### Done
- Found candidate references in `UGRP/PCEs/` (4 EMC PCE builds with input scripts and coefficient files) → REF-01..04, read-only, checksummed, provenance recorded (creator / production evidence missing). Built triclinic tobermorite fixtures from the INTERFACE FF database with msi2lmp (compiled from LAMMPS tools).
- **Positive controls 6/6 PASS** (0 false alarms). **264/264 corrupted files rejected**: 257 by Tiers 0–2, 2 only by LAMMPS's neutrality warning, 5 only by TC.2 (all explained in `VALIDATOR_RESULTS.md`). LAMMPS alone is Silent/Warn on 151; Tiers 0–2 catch 144 of them. 74 unit tests pass.
- Findings → FAILURE_MODES §9.6: FM28 SIGSEGV reproduced; new SIGSEGV path in `run 0` when bonds exceed the communication cutoff; PE = inf with exit 0 reproduced; EMC `.params` re-sets masses; msi2lmp leaves tilt unreduced; mineral molecule IDs cross bonds; ASE round trip collapses types and drops angles/dihedrals/impropers.
- Spec set v0.4: PROPERTIES (42 + 2 TC, NOT_APPLICABLE verdict, §8.10–8.11), FAILURE_MODES (§9.3, §9.6), SPEC (§7.8, §7.14 provisional values), SPEC_SUMMARY (§10–11), provenance.

### Not Done
- Owner decisions OD-B…OD-N, S-Q1…S-Q7: **none taken**; the validator uses provisional values listed in SPEC §7.14.
- Trusted references (OD-I): REF-01..04 lack creator and production-use evidence; no C-S-H reference exists.
- SSH and Docker backends untested; pymatgen not installed (only needed for optional cross-checks); MPI / `newton_bond off` not probed.
- Repository not pushed (no GitHub remote configured; pushing is the owner's call). Supervisor review of v0.4.

### Open Questions
- Is PCE-on-tobermorite/C-S-H in PCFF-INTERFACE the intended system (folder contents suggest it; SPEC §7.14)?
- τ_Q floor rule (PROPERTIES §8.10 note 1); ±2 % density placeholder; P1.8 policy for mineral models; tilt WARN vs FAIL (OD-N).

### Tomorrow
- Gate 1 review (below), then owner answers to OD-B / OD-I before the eval set (19 Oct).

### Hours
- To be filled by project owner.

---

## 2026-10-17 — GATE 1: validator gate (assessment prepared 2026-10-16; decision is the owner's)

| Pass criterion (plan Day 16) | Status | Evidence |
|---|---|---|
| Tiers 0–3 implemented | MET | PROPERTIES §8.10 |
| Every failure mode caught | MET — all 33 in-scope FMs (+ FM24 scope rejection) have operators; 264/264 files rejected, 257 by the validator's own checks; the 7 others are explained (2 need the τ_Q decision, 5 are task-level: dilute box size, origin shift of a periodic box, permuted coefficient values) | `VALIDATOR_RESULTS.md` |
| Reference files all pass | MET (6/6) — with the caveat that the references are candidates, not trusted | `VALIDATOR_RESULTS.md`, `provenance.md` |
| Tests green | MET (74 passed) | `pytest -q` |
| Code pushed | NOT MET — committed locally; no remote | `git log` |

**Recommended decision:** PASS, conditional on the owner (a) adding a remote and pushing, and (b) accepting the provisional configuration and calibration for now. Tag `validator-v1` created on the commit that produced these results (move it if the owner disagrees). Risk carried into the eval-set week: OD-B / OD-I. If they are still open on 19 Oct, the eval set can only use the PCE/EMC family the validator is calibrated for.

---

## 2026-10-17 / 18 — Gate 1 and open decisions

- Gate 1 assessed as PASS (conditional) in the 2026-10-17 entry; owner informed of what is needed (system class, references).
- 2026-10-18: supervisor not responding. Recommendation recorded (SPEC §7.3, §7.15): bulk tobermorite from the INTERFACE FF database with PCFF-INTERFACE, published models as references with self-generated evidence, and a "proceeding unless you object" note to the supervisor.
- Hours: to be filled by project owner.

---

## 2026-10-19 — EVAL SET Day 17 (+ Days 18–19 references): adopt defaults, build references (AI-assisted)

### Done
- **Decisions B, C, D, E adopted as PROVISIONAL DEFAULT** (owner, default-unless-objection; SPEC v0.5 §7.3, §7.15). Primary configuration `configs/interface_pcff_tobermorite.yaml`; `config.yaml` now defaults to it.
- **Reference pipeline** `scripts/build_references.py`: INTERFACE FF 1.5 model → msi2lmp → tilt reduction → `scripts/supercell.py` → LAMMPS read/write → comments restored (data tokens verified unchanged). REF-05..08 (unit and rectangular cells of tob11/tob14) and 14 eval references t01–t14; all PASS Tiers 0–3.
- **Evidence** `scripts/evidence_runs.py` → `docs/REFERENCE_EVIDENCE.md`: minimise + 5 ps NVT + 10 ps NPT clean for both minerals (lattice within 0.8 %); energy per unit cell equal across all 18 tobermorite files to ≤ 0.011 %.
- **Calibration** `calibration/tobermorite_interface.json` (density window now representational, not the ±2 % placeholder).
- **Eval set** `eval/tasks/t01–t14.json` (3 easy / 8 representative / 3 hard) and `docs/EVAL_SET.md`.
- **Validator changes:** statistical charge floor (PROPERTIES §8.5 rule 3, v0.5) — the missing-hydrogen case is now caught by P2.1 instead of only by LAMMPS; P1.15 fails conflicting units hints; kspace command per configuration with a crash fallback (P3.4 attributes PPPM crashes to the build); floating-point floors for files written at full precision. 77 unit tests pass.
- **Matrix** (448 corrupted files, 10 parents): 0 missed; 439 caught by Tiers 0–2, 9 by TC.2 only. 24/24 positive controls pass. The validator fails exactly the 6 of 10 LAMMPS-replicated supercells that TC.2 shows to be wrong.
- **Findings** (FAILURE_MODES §9.6 items 9–11): PPPM segfaults on many valid boxes; `replicate … bond/periodic` silently joins wrong images in tilted cells; `write_data` drops type names. **Correction:** the 2026-10-16 claim that stretched bonds crash `run 0` was wrong — it was the PPPM defect (item 2 withdrawn).

### Not Done
- Supervisor note not yet sent (owner to send; draft given in chat on 2026-10-18).
- Dev/test split, `METRICS.md`, harness (plan 22–23 Oct).
- A coefficient-vs-.frc check (permuted coefficient values with intact comments are caught only by TC.2); candidate agent tool later.
- Bug reports to LAMMPS (PPPM crash, replicate bond/periodic) — optional, owner's call.

### Tomorrow
- Send the supervisor note; review the 14 tasks; then the split and METRICS.md (Day 20).

### Hours
- To be filled by project owner.

---

## 2026-10-20 — Supervisor directive: PCE of any architecture + all minerals, class I and class II (AI-assisted)

### Done
- Supervisor message recorded verbatim (SPEC v0.6 §7.16). Decisions B and C now DECIDED: PCE (any architecture) + all INTERFACE cement minerals; CVFF-INTERFACE (class I) and PCFF-INTERFACE (class II).
- **`builders/pce.py`**: PCE architecture JSON → typed, charged (force-field bond increments), 3D-grown, relaxed molecule → msi2lmp → LAMMPS DATA FILE. Acid (acrylic/methacrylic, protonated or not), maleic, ester-PEG (MPEG), ether-PEG (APEG/HPEG/TPEG/VPEG), any side-chain length/end group, sequence random/alternating/block/gradient/explicit, any number of chains, Na⁺/K⁺/Ca²⁺. INTERFACE PEO types for ester PEG in PCFF.
- **Cross-check:** rebuilding the group's EMC architectures reproduces REF-01..04 exactly (composition and atoms/bonds/angles/dihedrals/impropers). PCFF charges for backbone and carboxylate equal EMC's to 4 decimals.
- **`builders/minerals.py`**: any INTERFACE model, any supercell, either force field. 35/35 mineral references PASS (27 PCFF, 8 CVFF); CVFF unavailable for tobermorite, ettringite, monosulfate (no parameters) and hydrated C3A (msi2lmp NaN).
- 20/20 example PCEs (10 architectures × 2 force fields) PASS every tier (`docs/PCE_BUILDER.md`).
- Validator: P1.7 conditional sections, P2.4 element-pair fallback, .frc element tables, ion contact floors from published structures, class I improper rule. 98 unit tests.
- Findings 12–15 in FAILURE_MODES §9.6.

### Not Done
- Eval set still tobermorite-only: to be revised for PCE + minerals with a position-free PCE equivalence (METRICS.md, 22 Oct).
- PCE–mineral interface systems (combined builds) not attempted.
- Confirm with the supervisor what "main chains" means (read as number of chains and backbone length).

### Tomorrow
- Revise the eval set (PCE architectures in both force fields + minerals), then split and METRICS.md.

### Hours
- To be filled by project owner.

---

## 2026-10-22 — GATE 1 decision: PASSED (owner)

- **Decision:** Gate 1 passed, confirmed by the project owner on 2026-10-22 after checking the five criteria (plan Day 16).
- **Criteria:** Tiers 0–3 implemented · every failure mode caught (448/448 corrupted files rejected, 0 missed; `VALIDATOR_RESULTS.md`) · all reference files pass · tests green (98 passed) · code pushed (private repo `github.com/aneeshpreddy/lammps-agent`, tag `validator-v1`).
- **Caveats carried forward:** Tier 2 tolerances are provisional (supervisor to confirm the margins); the corruption matrix has not yet been rerun on the system class set on 2026-10-20 (class I CVFF PCEs, non-tobermorite minerals); a position-free TC comparison for PCE is still to be built (needed for METRICS.md).
- **Supervisor sign-off:** not yet recorded; forward the repo link.
- **Next:** rerun the corruption matrix with builder PCEs (both force fields) and mineral references as parents; then the eval set, METRICS.md and the dev/test split.

---

## 2026-10-22 — EVAL SET Day 20: comparison modes, eval set v2, METRICS, frozen split (AI-assisted)

### Done
- **TC.2 position-free modes** (`validator/tc.py`): `graph` (Weisfeiler–Lehman hash of each typed, charged molecule graph; optional cell comparison) and `chemistry` (per molecule: (type, charge) multiset, net charge, bonded type-pair counts). The same spec with a different random draw → `graph` FAIL, `chemistry` PASS; a wrong composition → both FAIL. 101 tests pass.
- **Validator rerun on the new system class:** 20 parents (adding builder PCEs class I/II, C3S, C3A, ettringite, monosulfate); 870 corrupted files, 0 missed, 848 caught by Tiers 0–2, 22 only by TC.2; 34/34 positive controls pass. Three operator defects fixed: no-op mutations are now skipped and listed (8 were "missed" only because nothing had changed), the tilt flip uses the first non-zero component, and the coefficient swap picks rows whose values differ.
- **Eval set v2** (`scripts/build_eval_set.py`, `docs/EVAL_SET.md`): 16 tasks (7 minerals, 9 PCE; 5 class I, 11 class II; 4 easy, 7 representative, 5 hard). Every reference passes all tiers, matches itself in its TC mode, and rebuilds byte-identically. v1 (tobermorite only) is kept in `eval/tasks_v1/`.
- **`docs/METRICS.md` v1.0**: success = valid (all tiers) AND equivalent (TC.2 in the task's mode); 3 repeats on dev, 5 on test; breakdowns and diagnostics.
- **Split frozen** (`scripts/make_split.py`, seed 20261022): dev = m02 m03 m05 m07 p02 p04 p05 p06 p07 p08; test = m01 m04 m06 p01 p03 p09.
  **`eval/split.json` SHA-256: b1e632ad536c23b66b4cec155a4ee44a329b16a758b8ad29c5a1cb1e33c5031f.** Do not open the test split before 16 Nov.

### Not Done
- Harness `eval/harness.py` with oracle / corrupter sanity checks (plan Day 21, 23 Oct).
- Coefficient–geometry consistency check for FM22 (largest remaining TC-only category).
- Supervisor: meaning of "main chains"; whether PCE-on-mineral systems belong in the evaluation.

### Tomorrow
- Harness + oracle/corrupter checks.

### Hours
- To be filled by project owner.

---

## 2026-10-22 (later) — P2.9 bond coefficients vs geometry; builder relaxation fix (AI-assisted)

### Done
- **New P2.9** (`validator/tier2.py`): for each bond type, (mean bond length / its own r0) must lie in the window calibrated for its atom-type pair, else within a default tolerance (calibration `bond_r0` block in every `calibration/*.json`). FM22 (coefficient values moved to another bond type) is now caught by Tiers 0–2 in 12 of 14 cases, up from 0; the 2 left swap rows whose r0 differ by about 1 % (TC.2 catches them). 103 tests pass.
- **Builder defect found and fixed:** measuring P2.9 showed the PCE builder's vacuum relaxation stretched backbone C–C bonds by up to 11 %, caused by unscreened carboxylate repulsion. `builders/relax.py` now excludes 1-4 pairs in the soft stage and uses dielectric 80 in the force-field stage (geometry preparation only; the charges in the file are unchanged). All builder outputs were rebuilt: PB-01/02 parents, the PCE examples (20/20 PASS) and the eval v2 PCE references (16/16 PASS, self-match, byte-identical rebuild).
- **Matrix:** 870 corrupted files, 0 missed, 860 caught by Tiers 0–2 (was 848), 10 only by TC.2 (6 × FM19 and 1 × FM23 on vacuum boxes, 2 × FM22 near-equal r0, 1 × FM06 on monosulfate); 34/34 positive controls pass.
- **Split re-frozen after the reference rebuild** (no system had been scored): membership unchanged (dev = m02 m03 m05 m07 p02 p04 p05 p06 p07 p08; test = m01 m04 m06 p01 p03 p09); the file changed only through the task reference hashes.
  **New `eval/split.json` SHA-256: 6bcfa9a36beeb7995ee8b4566a891753eaa5d6b86c3fdb899b0151a6626a4545** (supersedes b1e632ad…).

### Tomorrow
- Harness `eval/harness.py` + oracle/corrupter checks.

### Hours
- To be filled by project owner.

---

## 2026-10-26 — Supervisor replies; composite builder; tight PCE box; eval set v3 (AI-assisted)

### Done
- **Supervisor replies recorded** (SPEC v0.7 §7.17): Q1 "main chains" = backbone length; Q2 PCE on a mineral surface is in scope now ("yes a combined builder"); Q3 Tier 2 margins accepted, with the PCE "inside a box … slightly bigger than the bounds of the atoms"; Q4 no reply (Homebrew build stays the reference); Q5 EMC PCE files used in production simulations (REFERENCE_EVIDENCE.md §C).
- **Tight PCE box** (`builders/pce.py` `fit_box`): relax in a roomy box (12 Å padding), then shrink to the atom bounds + 2 Å per face. **New P2.10 box margin** (1–5 Å per face, PROVISIONAL reading of "slightly"), declared in `interface_{pcff,cvff}_pce.yaml` v0.2. PCE examples 20/20 PASS (PCE_BUILDER.md).
- **`builders/composite.py`**: a PCE on any INTERFACE slab model, both force fields; normal = axis with the largest empty gap; flat or as built; height above the top face; `auto` lateral supercell; DATA FILE merge with ID offsets, coefficients copied unchanged. Configs `interface_{pcff,cvff}_composite.yaml`, calibration `composite_{ff}.json` (EMC + mineral references, ion contact sources, cross-pair fallback). COMPOSITE.md: 5/5 built composites PASS; tobermorite in class I refused (no parameters).
- **TC.2** `tc_compare_cell` accepts a list of axes (lateral cell only for composites).
- **Eval set v3** (22 tasks: 7 minerals, 9 PCE, 6 composites c01–c06; references in `data/reference/eval_v3/`, all PASS, self-match, byte-identical rebuild). PCE task inputs now ask for the tight box. v2 tasks kept in `eval/tasks_v2/`. **METRICS.md v1.1** (no system scored yet).
- **Split extended** (`make_split.py --extend`): existing assignments kept; composite dev = c01 c04 c06, test = c02 c03 c05.
  **`eval/split.json` (version 2) SHA-256: 063c2ddad24be986bf16dd3b8a549c3681871837d133d20340416003d6cb5fe4** (supersedes 6bcfa9a3…).
- **Matrix:** 948 corrupted files from 22 parents (+ CP-01 pcff/cvff), 0 missed, 942 caught by Tiers 0–2, 6 TC-only; 36/36 positive controls. 106 tests pass.

### Not Done
- Harness `eval/harness.py` with oracle/corrupter checks (plan Day 21) and the baseline (Day 23): about 3 days behind.
- Adsorption height/orientation are not part of TC.2 (stated limitation, METRICS v1.1).

### Tomorrow
- Harness + oracle/corrupter checks, then the single-call baseline on the dev split.

### Hours
- To be filled by project owner.

---

## 2026-10-27 — Plan Days 21–24 caught up: harness, sanity checks, single-call baseline (AI-assisted)

### Done
- **Evaluation harness** (`eval/harness.py`, METRICS v1.1): `evaluate(system, tasks, repeats)` → `results.json` + `summary.md`. Every metric of METRICS §3–4 is computed: success, spread across repeats, pass@k, breakdowns, failure categories, FM incidence, tokens, cost and latency. Fixed conditions are recorded (git commit, config versions, calibration hashes, LAMMPS build, split hash, model settings). Systems receive only `{id, input}`. The split and task files are checked against the frozen hashes, and the test split is refused before 16 Nov.
- **Sanity checks** (`scripts/harness_checks.py`, `docs/HARNESS.md`; dev split, 13 tasks × 3 repeats). All four pass:
  - oracle 1.00;
  - baseline with a mock perfect model 1.00, so the baseline's output schema and conversion to builder specs handle every dev task;
  - file corrupter: success 0.00, validity 0.00 (8 operators);
  - spec corrupter: success 0.00, validity 1.00 (all caught by TC.2).
  The recorded commit f851fb3 shows "dirty" only because of a docs edit.
- **Single-call baseline** (`agents/baseline.py`, `docs/BASELINE.md`): one `claude-opus-5-5` call (effort medium, structured output, refusal fallback off) → builder spec → `builders/dispatch.py`. The system prompt is generated from the builder docs and the model database. Model ID and prices were taken from the docs today (`eval/pricing.json`: $4 / $20 per MTok). `anthropic` 0.125.0 added to requirements.
- **Builder defect found by the spec corrupter** (FAILURE_MODES §9.6 item 19): a TPEG chain with 31 EO units relaxed into a tangle with c–c2 bonds up to 1.81 Å, and P2.9 rejected it. `builders/pce.py` now checks bond strain after relaxation and regrows the conformation (same sequence, new seed, up to 5 times). All existing references rebuild byte-identically, so the split is unchanged.
- 112 tests pass.

### Not Done
- **Scored baseline run on the dev split:** no API credentials on this machine (`ANTHROPIC_API_KEY` unset, no `ant` profile). One command once a key is set: `python -m eval.harness --system baseline --split dev --repeats 3 --write-doc docs/BASELINE_RESULTS.md` (about $3–5).

### Tomorrow (plan: baseline analysis, then the tool layer)
- Run the baseline on dev; read its failures by category; start the tool layer.

### Hours
- To be filled by project owner.

---

## 2026-10-27 (evening) — Plan Days 26–27 done early: tool layer, logging, tool tests (AI-assisted)

The scored baseline run (Day 25 analysis) waits on an API key, so the tool layer was built first. It needs no LLM.

### Done
- **Tool layer** (`tools/`, `docs/TOOLS.md`, `tools-v1`). Three tools, each with a strict schema (`strict: true`):
  - `build_data_file`: the baseline's builder spec → DATA FILE + plain facts (counts, elements, net charge, box, sequences / surface details);
  - `get_model_info`: the plan's `get_type_map`, per cement-mineral model and force field: cell, composition, atom-type and charge table, slab normal;
  - `get_reference_example`: 6 known-good worked examples.
  `run_generation_script(code)` is replaced by `build_data_file(spec)` (design decision E). The validator is not a tool.
- Every tool checks its arguments again (`tools/schema_check.py`), never raises (errors come back as `is_error` results), is deterministic and safe to retry (each build goes to a new folder), and logs one JSON line per call (ts, call, tool, arguments, ok, result summary, duration).
- **Checks** (`scripts/tool_checks.py`, no LLM): all 6 reference examples build and PASS Tiers 0–3. `get_model_info` answers 35 model/force-field pairs and refuses the other 21 with the reason. The log is complete.
- **Tests:** `tests/test_tools.py` (7). It includes a guard that no reference example shares its key parameters with any eval task. **119 tests pass.**

### Disclosure
- The first run of the example-vs-task guard failed, and pytest printed part of the task fingerprint set. It showed the mineral model and supercell of some test-split tasks; it did not show their inputs or any results. Only the developer (the AI assistant) saw it; no evaluated system or prompt did. The test now passes only example names to its assertion. The composite example was moved to the monosulfate (002) surface. Tool and prompt content were not changed in response to what was shown.

### Not Done
- **Scored baseline dev run and its failure analysis** (Day 25): waiting on `ANTHROPIC_API_KEY`.
- **Per-tool timeouts:** plan Day 31 (bounds).

### Tomorrow
- With a key: run the baseline, then analyse it (BASELINE_RESULTS.md, failure categories). Without one: start the loop skeleton (`agents/loop.py`) against a scripted mock model, so the API is needed only for real runs. Gate 2 is on 31 Oct.

### Hours
- To be filled by project owner.

---

## 2026-10-27 (night) — Plan Days 23–28: everything that does not need a model (AI-assisted)

### Done
- **Model access** (Days 23–24 prep).
  - `config.yaml` `model:` is now the one place the model is chosen (`agents/baseline.py` reads it). It is PROVISIONAL until the supervisor decides how model access is provided (paid key, institute cloud credits, or a free open-weight model). The options were written up for the supervisor today.
  - `scripts/api_smoke.py` is the plan's ten-line smoke test.
  - Without credentials, the smoke test and the baseline stop at the first call with a message. A run can no longer record every task as a failure because a key is missing.
  - Every run now saves its exact `system_prompt.txt`. The baseline's prompt is unchanged (same SHA-256).
- **Failure analysis** (Day 25, `eval/analyse.py`). It reports, for any run folder:
  - success, tier distribution and categories;
  - every failure with its validator messages and a field-by-field spec difference from the hidden spec (monomers by chemistry, not label; convenience form expanded);
  - a suggested gap type: formatting, knowledge, reasoning, pipeline, validator or infrastructure.

  On the sanity systems it gives exactly the expected answers: spec corrupter 13 of 13 reasoning, each diff naming the perturbation; file corrupter 13 of 13 pipeline. The harness now stores failing-check messages per run, which the correction cycle (Day 30) will reuse. The sanity systems record the spec they built.
- **Tests:** `tests/test_analyse.py` (4), including a round trip of every dev hidden spec through the baseline's answer schema with no spec difference. **123 tests pass.** Harness sanity checks rerun after the harness change (docs/HARNESS.md).

### Gate 2 readiness (gate on Sat 31 Oct; prepared 27 Oct, the decision is the owner's)

| Pass criterion (plan Day 28) | Status |
|---|---|
| Baseline number recorded | **Not yet:** needs model access |
| Failures categorised | Tooling ready and checked on the sanity systems; needs the run |
| Tools built and tested | **Done** (27 Oct, docs/TOOLS.md) |

**Revised plan to discuss with the supervisor** (plan Day 28: "tell your supervisor, with a revised plan"):
- **If model access is decided by Thu 29 Oct:** smoke test, baseline dev run (~1 h) and analysis on the same day, then reading the failures (~2 h). Gate 2 is met on time, and `baseline-v1` is tagged after the run.
- **If it is decided later:** Gate 2 is met on the tools criterion only, and the baseline number follows within a working day of access. The agent loop starts on 2 Nov as planned, against a scripted mock model.
- **Hard deadline: access by Mon 9 Nov** (first full dev-split run of the agent). After that, the evaluation window (16–18 Nov) is at risk.

### Not Done
- The scored baseline run, its reading, and the `baseline-v1` tag: waiting on model access.

### Tomorrow
- With model access: smoke test, then the baseline run and the analysis. Without it: nothing on the plan before 2 Nov needs doing. The agent loop (Days 29–33) can start early against a mock model.

### Hours
- To be filled by project owner.

---

## 2026-10-27 (late) — Plan Days 29–33 built early: agent loop against scripted mock models (AI-assisted)

Owner's goal (27 Oct): finish by 14–15 Nov. The loop needs no model to build, so it was built now. A compressed timeline is in the conversation notes. It depends on model access by about 3 Nov and on moving the test-open date to the code freeze; that date change is the owner's decision and has not been taken.

### Done
- **Agent loop** (`agents/loop.py`, `docs/AGENT.md`, `loop-v1`).
  - Plain-Python tool-use loop, with K = 3 attempts.
  - The orchestrator validates every attempt's last build (Tiers 0–3, configuration from what was built, never the task's reference).
  - Feedback is concise (property, tier, message, LAMMPS errors), with three modes for the ablation: full (C), none (B: "try again"), tiers01 (D).
  - Bounds: steps, attempts, tokens, wall-clock, per-tool timeout (`config.yaml` `agent:`, PROVISIONAL).
  - Non-convergence: a fingerprint per attempt; a "reconsider" hint on the second identical one, escalation on the third.
  - Full `trace.jsonl` per run, and `replay()`, which reproduces a run exactly from its folder.
  - Prompt caching on the system block and the conversation.
- **Same knowledge as the baseline.** The baseline prompt was split into intro + `knowledge()`. The agent uses the same `knowledge()` word for word, and the baseline prompt is byte-identical (same SHA-256).
- **Scripted mock models** (`agents/mock.py`: perfect, fix, stubborn, runaway). Harness systems `agent`, `agent-nofeedback`, `agent-tiers01`. The harness also records stop reasons and escalations.
- **Tests:** `tests/test_loop.py` (11). **134 tests pass.** Harness checks extended with three agent mock checks (docs/HARNESS.md).

### Found while building (docs/AGENT.md, "Known limitation")
- The validator inside the loop can only catch invalid files. A valid file of the wrong system (wrong model, supercell, EO length, anchor) passes inside the loop and fails only TC.2 in the harness. If baseline failures are mostly TC-only, the B-vs-C ablation may show little difference. That is a possible finding to anticipate, and the baseline analysis will tell. Options are listed in AGENT.md, to be decided on dev data only.

### Not Done
- Any run with a real model (access pending). Loop limits and prompt are untuned (dev runs, from ~3 Nov if access arrives).

### Tomorrow
- Waiting on model access and on the test-open-date decision. Without them: ablation tables and figure scripts, so the 16–18 Nov (or earlier) evaluation days are only run → tables.

### Hours
- To be filled by project owner.

---

## 2026-10-28 — Plan Days 38–43 groundwork without a model: escalation report, variant E, experiment runner, freeze record (AI-assisted)

Model access is still with the supervisor (expected in 1–2 days). Haiku 5.5 was discussed as the low-cost choice ($0.10 / $0.50 per million tokens on the 27 Oct pricing record, about 1/20 of Sonnet 5.5). Nothing was changed in `config.yaml` `model:`; the choice stays with the owner.

### Done
- **Escalation report and guard rails (plan Day 38, `agents/loop.py`).**
  - A run that ends without an accepted build writes `REPORT.md`: the outcome, a warning that the last build did NOT pass, every attempt with its failing checks, the last build's messages and LAMMPS errors, and what changed between builds.
  - Guard rails:
    - no work folder inside `data/reference/` (ToolBox and loop);
    - no overwriting a run folder unless `overwrite=True`;
    - the harness refuses an output folder that already holds results;
    - no tool runs commands or submits jobs.
- **Variant E, optional and off by default (`agents/checks.py`, `--system agent-checked`).** It answers the known limitation that a valid but wrong build passes the loop. It adds:
  - a one-sentence build summary in the `build_data_file` result;
  - a request check: one separate model call reads only the request and lists what it states, and plain code compares that list with each build.

  A mismatch is fed back once per field and value. If the agent rebuilds it unchanged, its reading wins. New mock `wrongvalid`: C accepts the wrong build and TC.2 fails, while E catches and fixes it (tests and harness checks).
- **Experiment runner and tables (plan Days 40–43, `eval/experiment.py`, docs/EVALUATION.md).**
  - One command runs A/B/C(/D/E) on the same tasks and repeats.
  - It writes the tables: success with spread, breakdowns, paired contrasts with per-task counts and a sign test, failure categories, A's failures against the others, in-loop recovery, and cost.
  - It also writes two figures.
- **Freeze record (plan Day 39, `scripts/freeze_config.py`).**
  - It records the model, every prompt, schema and tool hash, the limits, configurations, calibration files, split, tasks, prices and LAMMPS.
  - `--check` lists any change since the freeze, and `eval.experiment run --split test` refuses to start if there is one.
- **Tests:** test_loop (14), test_checks (10), test_experiment (2), test_freeze (2). matplotlib pinned in requirements.

### Not done
- Any run with a real model.
- Whether E is kept is decided on dev data only.
- The test-open-date decision (owner).

### Tomorrow
- Write-up sections that need no results (problem, validator, task set, baseline and agent design, limitations, R18–R21).
- README reproduction steps.

### Hours
- To be filled by project owner.

### 2026-10-28 (later): write-up draft and reproduction steps (plan Days 44–45 groundwork)
- **`docs/REPORT_DRAFT.md`.** Every section that needs no model run is drafted: problem, scope, validator and its validation, task set and metrics, harness checks, systems (A–E), related work, limitations, future work, and a reproduction appendix. Results, abstract and model are marked [RESULTS] / [MODEL].
- **Prior work re-checked against the papers (R18–R21, 2026-10-28).** SPEC §7.6 corrected:
  - R20's title is "An Extensible Agentic Framework…" (Paimon);
  - its deterministic structure summary was not found and was removed;
  - R18's "1 of 80" is now quoted from its abstract.
- **README.** New "Reproduce the results from a clean checkout" section. The old validator block has its counts updated.

### 2026-11-03: model access, baseline (Gate 2) and first dev experiment
- **Model access.** The team's Claude Console API credits ($500). The owner's key lives in the environment only. Smoke test OK.
  - The owner switched the model to **Sonnet 5.5**. A partial Opus 5.5 baseline (11 runs, $0.12) was stopped and is not used.
  - Prices re-checked on the pricing page: unchanged.
- **Baseline v1 (dev): 0.59.** 12 of its 16 failures had one cause: the request leaves the backbone end groups unstated, the reference uses the builder default CH3, and the model chose H.
  - Owner: "follow the reference files".
  - Prompt `baseline-v2` adds "unstated end groups = CH3, CH3". It is shared by every system.
  - **Baseline v2: 0.92.** The only failure is c06, a builder refusal. v1 is kept in `docs/BASELINE_RESULTS_v1.md`.
- **Dev experiment A/B/C/E: 0.90 / 0.87 / 0.90 / 0.87.**
  - The in-loop validator rejected no file, so C's feedback never fired.
  - On c06 the agents answered the "too narrow" refusal by enlarging the cell the request fixes.
- **Fix:** the refusal now also suggests another seed (`builders/composite.py`, plus a test). **Rerun: 0.92 / 1.00 / 0.97 / 0.90.** c06 is now 3/3 for the agents.
- **Remaining failures.**
  - c04 is a TC.2 chemistry-mode effect of random sequences: the hidden spec itself passes with 5 of 10 seeds.
  - E's request check misreads p04 (backbone 30 instead of 30 + 10).
- **Cost on 3 Nov:** about $3.80 in total.
- **The owner rejected** a "model writes the file directly" system.

### 2026-11-04: pre-freeze cleanup
- **Model references.** The fallback model, the run metadata (thinking, sampling) and BASELINE.md, TOOLS.md and REPORT_DRAFT now describe Sonnet 5.5.
  - Its restrictions were tested on the API: `temperature` is rejected, forced `tool_choice` is rejected, and `thinking: disabled` is rejected.
- **Docs.** AGENT.md and EVALUATION.md record the dev findings. The agent limits are kept, because no dev run needed them.

### Not done
- Owner and supervisor decisions:
  - the claim framing (validity guarantee against feedback benefit);
  - the c04 scoring fix (it changes METRICS);
  - keep or drop E;
  - the test-open date;
  - the provisional values in `configs/*.yaml`.

### Tomorrow
- Act on those decisions. Then the final dev run and the code freeze (`v1.0`, `freeze_config.py`).

### Hours
- To be filled by project owner.

### 2026-11-05: configurations accepted, main claim reframed
- **Done.** The project owner accepted every value in the 8 declared configurations (`configs/*.yaml`): `status: ACCEPTED`, recorded in SPEC §7.14, README and CLAUDE.md.
  - No value changed, and the validator does not read `status`.
  - The calibration records (`calibration/*.json`) are also `ACCEPTED`. The 7 non-synthetic records were regenerated with `scripts/calibrate.py`: every tolerance value is identical, and only `status` and `date` changed.
- **Main claim reframed (owner, 2026-11-05).** The main claim is now that the agent's files pass LAMMPS without error ([X] %) and match the requested system ([Y] %) on held-out tasks, and that every file is certified by a validator that caught 948/948 corrupted files.
  - "Validator feedback improves the agent" is no longer claimed. The ablation explains the result instead: the builders prevent invalid files.
  - Updated: REPORT_DRAFT (abstract, §1, §5.3–5.4, §6, §7 position, §8), EVALUATION.md, and the contrast label in `eval/experiment.py`.
- **"What was built" for the user (5 Nov).**
  - New command `python -m agents.run "request" [--out DIR]`. It prints the verdict and one "Built: …" sentence, and writes `system.data` only if accepted (otherwise `REPORT.md`). Real-model check: an MPEG PCE request was accepted in 1 attempt for $0.024.
  - Every run now returns `build_summary`.
  - The variant that also shows the sentence to the agent (`--system agent-summary`) was tested on dev: 0.95 against C's 0.97. The difference is one more c04 run, from the random-sequence scoring effect, and the model never rebuilt. It is kept off.
  - 2 new tests.
- **Not done.** The c04 scoring fix, E, and the test-open date (owner and supervisor).
- **Tomorrow.** Act on those decisions, then the final dev run and the freeze.

### Hours
- To be filled by project owner.

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

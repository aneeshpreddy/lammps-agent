# Project Specification Summary

Version 0.5 (2026-10-19). v0.5: system class and force field adopted as a provisional default (§3, §12). v0.4 (2026-10-16): validator phase.

## 1. Problem
LLM agents can draft LAMMPS INPUT SCRIPTS, but the LAMMPS DATA FILE a simulation starts from can be silently corrupted: permuted atom types, lost charges, dropped bonds, wrong units, a default-sized box. LAMMPS can still accept such a file, producing plausible but wrong C-S-H simulations. **A source-and-experiment audit of LAMMPS 22 Jul 2025 – Update 6 (2026-10-02) found that 21 of 33 in-scope failure modes give no usable LAMMPS signal. One more (a bond to a non-existent atom) crashes LAMMPS with no error message.**

## 2. Task Boundary
Generate, and deterministically validate, one LAMMPS DATA FILE per task for one decided system class. Excluded: INPUT SCRIPT generation, MD workflows, force-field invention, arbitrary materials, reactive force fields (unless chosen), cluster submission.

## 3. Five Core Decisions
- **A. Artifact = LAMMPS DATA FILE**: LOCKED.
- **B. System class**: *PROVISIONAL DEFAULT (2026-10-19)* — bulk tobermorite 11 Å / 14 Å and supercells from the INTERFACE FF 1.5 database.
- **C. Force field + atom_style**: *PROVISIONAL DEFAULT* — PCFF-INTERFACE (class II), atom_style full, units real, periodic, coefficients in the DATA FILE.
- **D. Input representation**: *PROVISIONAL DEFAULT* — natural-language request + hidden structured spec.
- **E. LLM → generation code / tool calls → deterministic writer, with the validator always run by the orchestrator**: *PROVISIONAL DEFAULT*.
- The supervisor has not responded; these are default-unless-objection choices, reversible by re-running the scripts (SPEC §7.15).

## 4. Correctness Model
- **Tier 0** parseable · **Tier 1** internally consistent · **Tier 2** physically plausible (system-specific, calibrated tolerances only) · **Tier 3** accepted by LAMMPS *under the declared configuration*, split into structure-only (`read_data … nocoeff`) and full force-field (`run 0`) modes, plus process-outcome classification (clean / error / crash / timeout).
- Task correctness is a separate layer requiring references.
- **42 properties across Tiers 0–3 plus 2 task-correctness properties** (v0.3a: 40; v0.4 adds P1.16 topology-type signatures and P1.17 bonded-term completeness). Tier 2 tolerances are PROVISIONALLY calibrated from candidate references (PROPERTIES §8.11).
- **Rule:** "LAMMPS would catch it" never satisfies a property. Absence of a LAMMPS error or warning is never a PASS.

## 5. Target Failure Modes
**35 modes (33 in scope)**, e.g. type permutation, element mis-identification, unit mismatch, dropped/duplicated bonds, charge loss, atom-style mismatch, image-flag and tilt corruption, ID renumbering, missing/duplicate atoms, missing box keywords, 254-character truncation, overlap, implausible bonds/density.

New in v0.3a: surplus final row ignored, dangling topology ID (crash), velocity coverage defects, negative molecule IDs, duplicated/missing Masses or Coeff type rows (missed by Tier 3a), misleading style comments, duplicate header keywords, non-standard number formats.

Each in-scope mode maps to a property and, where possible, to a corruption operator for negative controls.

## 6. Key audit findings (2026-10-02)
- LAMMPS's **tilt warning** uses a different rule from its documentation.
- The **style-comment warning** misses mismatched names of equal length (e.g. `charge` vs `atomic`).
- **Duplicate atom IDs** are detected only when max ID < atom count.
- **Missing box lines** default to −0.5…0.5 with no warning.
- **Lines over 254 characters** are cut silently.
- **`run 0`** can exit 0 with PE = inf.
- **Tier 3a** (`read_data … nocoeff`) misses missing Masses and Coeff rows.
- Executables on macOS (Homebrew) are **`lmp_serial` / `lmp_mpi`**.

Full trail: `source_audit/SOURCE_AUDIT.md`.

## 7. Ground Truth / Oracle
2–3 production-proven group DATA FILEs, each with its INPUT SCRIPT, LAMMPS build, and force-field source. **None available yet — REFERENCE COLLECTION REQUIRED.** Matching a reference is not proof of correctness. References must themselves pass the v0.3a checks before use.

## 8. Open Decisions
- **System and force field:** system class (B); atom_style, force field and units (C); input (D); design confirmation (E).
- **Validation configuration:** LAMMPS build (OD-F; a local candidate now exists), boundary conditions, charge target, element↔type map.
- **References and scope:** reference files, type-label support.
- **New:** Tier 3 run settings (OD-L), encoding/line-ending policy (OD-M), tilt policy (OD-N), units hint on line 1 (S-Q7).

**B, C, the build, the boundaries, and the references block parts of the validator.**

## 9. Difference From Relevant Prior Work
- Holbrook et al. (arXiv 2603.20630) deterministically validate LLM-generated *INPUT SCRIPTS* (1 of 80 hardest-prompt scripts fully correct as generated).
- MDGym, Paimon and URSA assess scripts/workflows via outputs, execution success, or LLM critics. The audit shows that "it runs" is a weak criterion for DATA FILEs.
- PolyJarvis builds data files with deterministic tools but validates properties.
- None of the reviewed works provides a deterministic validator for the LAMMPS DATA FILE's structural/topological consistency. This is a gap in the reviewed literature, not a proven novelty. Prior-work figures still need re-checking before supervisor use.

## 10. Validator phase (5–17 Oct 2026) — status
- **Built:** `lammps-agent/validator/` — own parser, Tiers 0–3, TC.1/TC.2, local backend (SSH/Docker written, untested), calibration record, 49 corruption operators, validation matrix, 74 unit tests.
- **Result** (`VALIDATOR_RESULTS.md`): 6/6 positive controls pass (4 candidate references + 2 tilt-reduced tobermorite fixtures). 264/264 corrupted files are rejected: 257 by the validator's own Tier 0–2 checks, 2 only by LAMMPS's neutrality warning (P3.3), 5 only by the reference comparison (TC.2). LAMMPS alone is Silent or Warn-only on 151 of the 264; the validator's own checks catch 144 of those.
- **Real converter output rejected:** an ASE read→write round trip collapses force-field types to elements and drops every angle, dihedral and improper (`R13_ASE_ROUNDTRIP.md`); msi2lmp leaves triclinic tilt unreduced.
- **Provisional, owner to confirm:** every configuration value (SPEC §7.14), the reference candidates (OD-I), the calibration margins and the ±2 % density placeholder (PROPERTIES §8.11), and the τ_Q floor rule (PROPERTIES §8.10 note 1).

## 11. Next phase
Evaluation set (19–24 Oct): 12–15 tasks inside the decided system family. **Blocked on OD-B / OD-D / OD-I** — the eval tasks need a declared system family, an input representation and trusted references. If OD-B is not decided by 19 Oct, the PCE/EMC candidates are the only family the validator is calibrated for.

## 12. Status on 2026-10-19 (v0.5)
- **References:** REF-05..08 — published INTERFACE FF tobermorite models built by a documented pipeline, with self-generated MD evidence (`REFERENCE_EVIDENCE.md`); provisional oracle, supervisor sign-off pending.
- **Eval set drafted:** 14 tasks (3 easy, 8 representative, 3 hard) with reference outputs (`EVAL_SET.md`). Split, metrics and harness are next (22–23 Oct).
- **Validator on the new system:** 24/24 positive controls pass; 448/448 corrupted files rejected (439 by Tiers 0–2, 9 by TC.2 only).
- **New LAMMPS findings:** PPPM segfaults on many valid boxes (Ewald used instead); `replicate … bond/periodic` silently joins wrong periodic images in tilted cells — caught by the validator. The v0.4 "stretched bonds crash" claim was withdrawn (it was the PPPM defect).

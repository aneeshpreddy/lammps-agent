# SPEC — Agentic AI for LAMMPS Data-File Generation

Version 0.7 (2026-10-26). Supersedes v0.6 (2026-10-20). Status: **SYSTEM CLASS SET BY THE SUPERVISOR (2026-10-20, §7.16) AND EXTENDED BY THE SUPERVISOR'S REPLIES OF 2026-10-26 (§7.17); validator and structure builders implemented.**
v0.7 changes: §7.17 records the supervisor's five replies — "main chains" = backbone length; PCE on a cement-mineral surface is in scope now (`builders/composite.py`); the Tier 2 tolerances are accepted, with the PCE written in a box slightly bigger than its atoms (new property P2.10); the EMC PCE files were used in production simulations. Decision B gains (3) PCE on a mineral surface.

Version 0.6 (2026-10-20). Supersedes v0.5 (2026-10-19). Status: SYSTEM CLASS AND FORCE-FIELD POLICY SET BY THE SUPERVISOR (2026-10-20, §7.16); validator and structure builders implemented.
v0.6 changes: decisions B, C, D, E updated per the supervisor's directive (§7.16): the system class is PCE superplasticisers of any architecture plus all INTERFACE cement minerals; the force field is the project's choice, in two classes (class I CVFF-INTERFACE and class II PCFF-INTERFACE).

Version 0.5 (2026-10-19). Supersedes v0.4 (2026-10-16). Status: VALIDATOR BUILT; SYSTEM CLASS ADOPTED AS A PROVISIONAL DEFAULT.
v0.5 changes: decisions B, C, D, E move from OPEN to **PROVISIONAL DEFAULT** (§7.3, §7.15); §7.8 records published-model references; §7.14 now lists the tobermorite configuration.
v0.4 changes only §7.8 (candidate references found) and adds §7.14 (validator-phase status and provisional configuration values). Change logs: `LOG.md` (2026-10-02 and 2026-10-16 entries). No open decision below was taken by the validator phase; where the validator needed a value, it uses a **PROVISIONAL** value recorded in `configs/*.yaml` and listed in §7.14.

> **Version note.** These files were derived from the v0.2 files found in `~/Downloads/UGRP/Specs and .md files/`. The project's CLAUDE.md refers to a "v0.3" with failure-mode experiment results (`experiments/fm_verification/`) that was not found on this machine. If that v0.3 exists, merge it with this v0.3a; do not discard either silently.

---

## 0. Terminology and labels

- **LAMMPS DATA FILE** (DATA FILE): the file read by the `read_data` command — a header (counts, type counts, box) followed by a body of sections (Atoms, Masses, Bonds, Coeff sections, …). **This is the project's artifact.**
- **LAMMPS INPUT SCRIPT** (INPUT SCRIPT): the command script (units, atom_style, boundary, styles, read_data, run). Not the artifact. It appears only as part of the Tier 3 validation configuration.
- **Syntactic validity** = Tier 0. **Structural/internal validity** = Tier 1. **Physical plausibility** = Tier 2 (plausible ≠ correct). **LAMMPS acceptance** = Tier 3. **Scientific/task correctness** = a separate layer (TC) that requires the request and trusted references.
- **LAMMPS outcome vocabulary** *(new)*: Silent · Warn · Loud · Loud@run (passes `read_data`, errors at run setup) · Crash (signal, no ERROR line). See `FAILURE_MODES.md`.
- Statement labels used throughout: FACT · PROJECT DECISION · ASSUMPTION · RECOMMENDATION · OPEN QUESTION · UNVERIFIED · SOURCE-SUPPORTED CLAIM. *(new)* FACT statements about LAMMPS behaviour cite the doc (RD), the source (SRC, tag `stable_22Jul2025_update6`), and/or a probe (PRB, T-number).

---

## 7.1 Executive summary

- **Project.** An agentic AI workflow that produces LAMMPS DATA FILEs for cementitious systems, paired with a deterministic validator that certifies each file against declared correctness properties.
- **Artifact (PROJECT DECISION, LOCKED).** The LAMMPS DATA FILE (structure + topology). Not the INPUT SCRIPT.
- **What the user supplies (OPEN, OD-D).** Not yet decided. Candidates: natural-language specification, CIF or other structure file, parameter dictionary, structured JSON.
- **What the agent does (RECOMMENDATION, OD-E).** The LLM writes generation logic (Python) and/or issues tool calls; deterministic code writes the DATA FILE. The LLM does not emit coordinate lines token-by-token. Awaiting owner confirmation.
- **What validation verifies (PROJECT DECISION — stated design intent).** Tiers 0–3 as defined in `PROPERTIES.md`. The validator is deterministic, independent of the LLM, and independent of the converters it checks (own parser; ASE/pymatgen used only for cross-checks, never for verdicts).
- **Orchestration (RECOMMENDATION, OD-E).** The orchestrator always runs the validator after every generation attempt; it is not an optional tool the model may skip.
- **Why silent corruption matters.** LAMMPS can accept a DATA FILE that encodes permuted atom types, lost charges, dropped bonds, or a default-sized box. The simulation then runs on the wrong system with no error. **v0.3a source audit:** 21 of 33 in-scope failure modes give LAMMPS users no usable signal (FAILURE_MODES §9.5). One (FM28) crashes LAMMPS without an error message. See §7.7.
- **Out of scope.** INPUT SCRIPT generation, full MD workflows, force-field invention, arbitrary materials, production cluster submission.
- **Novelty (limited claim).** The LLM-agent works reviewed (§7.6) target INPUT SCRIPTS or end-to-end workflows; none of them provides a deterministic validator for LAMMPS DATA FILE header/topology/type/charge/image-flag consistency. This is a gap *among the works reviewed*, not an established novelty. A broader literature search is outstanding.

---

## 7.2 Problem definition

```
INPUT (OD-D: OPEN)
  → GENERATION PROCESS (OD-E: LLM → generation logic / tool calls → deterministic writer; RECOMMENDED)
  → LAMMPS DATA FILE (A: LOCKED)
  → VALIDATION (Tier 0 → Tier 3, deterministic; TC layer separate)   ← always run by the orchestrator
```

Tiers 0–3 inspect only the DATA FILE and the declared validation configuration, so they do **not** depend on OD-D. The task-correctness layer (TC) does depend on OD-D.

---

## 7.3 Five core decisions

| Decision | Current Decision | Evidence / Rationale | Status | Consequence |
|---|---|---|---|---|
| **A. Artifact** | LAMMPS DATA FILE | Owner statement. The `read_data` format is fully documented (LAMMPS read_data doc), so a deterministic parser is feasible. *(v0.3a)* The parser grammar has also been derived from the source (PROPERTIES §8.7). | **LOCKED** | All properties target the DATA FILE. |
| **B. System class** | *(v0.6, supervisor 2026-10-20)* **(1) PCE superplasticisers of any architecture** — backbone monomers (acrylic/methacrylic acid, maleic acid; protonated or deprotonated), PEO side chains of any number and length on ester (MPEG) or ether (APEG/HPEG/TPEG/VPEG) anchors, any sequence, any number of chains, Na⁺/K⁺/Ca²⁺ counter-ions; **(2) all INTERFACE FF 1.5 cement minerals** — C3S, C3A, ettringite, monosulfate, tobermorite 11/14 Å; unit cells, supercells, rectangular cells, surfaces; *(v0.7, supervisor 2026-10-26)* **(3) a PCE on a cement-mineral surface** — any architecture of (1) on any INTERFACE slab model of (2), at a chosen height, flat or as built (§7.17). | Supervisor: "let it learn about all [minerals]"; "it should be able to generate the structure of pce for any architecture, user defined number of side chains, main chains etc."; "PCE files have data and cement_minerals have structural file of minerals". | **DECIDED (supervisor)** | Builders `builders/pce.py`, `builders/minerals.py`, `builders/composite.py`; references per §7.8; eval set v3 (EVAL_SET.md). |
| **C. Force field + atom_style** | *(v0.6)* **Two force fields, one per class (project's choice, per the supervisor "F.F is our choice ... any 2 force field (class 1 and class 2)"): CVFF-INTERFACE (class I) and PCFF-INTERFACE (class II), INTERFACE FF 1.5** (`UGRP/INTERFACE_FF_1_5/FORCE_FIELDS`). `atom_style full`, `units real`, periodic, all coefficients in the DATA FILE. | The two files share the INTERFACE mineral parameterisation and the PCE chemistry (aliphatic, ester, ether, carboxylate, hydroxyl, ions); PCFF-INTERFACE adds tuned PEO parameters (INTERFACE documentation §2: PEO "currently supported in PCFF only"), so it is the higher-fidelity choice for PCE side chains. Coverage limits (documented, enforced by refusal): CVFF-INTERFACE supports only C3S and C3A among cement minerals; PCFF-INTERFACE defines no class II cross terms for INTERFACE mineral and PEO types (zero). | **DECIDED (choice delegated to the project; recorded here)** | Configurations `configs/interface_{pcff,cvff}_{pce,minerals}.yaml`; earlier `interface_pcff_tobermorite.yaml` kept. |
| **D. Input** | *(v0.6)* For PCE tasks: a natural-language request that the system maps to an architecture spec (`builders/pce.py` JSON: monomers, composition, sequence, chains, counter-ion, force field); for mineral tasks: model name + supercell + force field. A hidden structured spec is kept for checking. | Matches the builders' inputs; keeps task correctness checkable. | **PROVISIONAL DEFAULT** | TC layer: PCE equivalence must be position-free (random coil geometry) — to be defined in METRICS.md (22 Oct). |
| **E. Model output** | LLM → generation logic / tool calls (the builders) → deterministic writer (msi2lmp + LAMMPS) → DATA FILE | The plan's stated design intent. A DATA FILE for a C-S-H supercell can contain thousands of atom lines; token-by-token emission is slow, costly and error-prone. | **PROVISIONAL DEFAULT** (v0.5) | Writer bugs remain in scope for validation. If rejected (LLM emits raw text), the benchmark changes character. |

---

## 7.4 System boundary

**Scope rules below that are not owner decisions are labelled RECOMMENDATION (provisional) and require owner acceptance.**

### IN SCOPE
- Validating one DATA FILE per task against Tiers 0–3 (and TC once D and references exist).
- Systems in class B, written in atom_style C (once decided).
- Box kinds: orthogonal and restricted triclinic (RECOMMENDATION, provisional).
- Sections: Atoms, Velocities, Masses, Bonds, Angles, Dihedrals, Impropers, and the standard Coeff sections (Pair, PairIJ, Bond, Angle, Dihedral, Improper).
- Corruption introduced by converters or writers (ASE, pymatgen, in-house tools).
- Tier 3 in two distinct modes: structure-only (`read_data … nocoeff`) and full force-field (`run 0`).

### OUT OF SCOPE
- Generating or grading LAMMPS INPUT SCRIPTS.
- Production MD, equilibration, property calculation.
- Choosing, fitting, or modifying force fields.
- Multi-file assembly via `read_data … add` (OPEN whether needed later).

### SUPPORTED CASES
A future test case belongs in the benchmark only if **all** hold:
1. The artifact is exactly one DATA FILE (plain text, not compressed — RECOMMENDATION).
2. The system is in class B (conditional on OD-B).
3. Atoms rows use atom_style C (conditional on OD-C1).
4. The box is orthogonal or restricted triclinic.
5. A declared validation configuration exists (§7.10).
6. Every Tier 2/TC verdict uses a tolerance derived from a trusted reference or an explicit, documented requirement.

### UNSUPPORTED CASES (RECOMMENDATION, provisional)
- General-triclinic headers (`avec`, `bvec`, `cvec`, `abc origin`). *(v0.3a: these are accepted by LAMMPS 22 Jul 2025 Update 6; excluding them is a scope choice, not a LAMMPS limitation.)*
- atom_style hybrid, template, and finite-size/body styles.
- Type-label sections (`Atom Type Labels`, …) — OPEN (OD-K).
- Class 2 Coeff sections and reactive force fields, unless chosen under C.
- 2D simulations.
- `read_data … fix` sections.
- Compressed (.gz etc.) DATA FILEs (LAMMPS can read them via external tools — SRC `read_data.cpp:2469`).

### OPEN SCOPE QUESTIONS
- **S-Q1** Must Masses appear in the DATA FILE, or may they be set in the INPUT SCRIPT via `mass`? (Both are legal per read_data doc.) *(v0.3a: if in the DATA FILE, Tier 3a will not detect missing/duplicate rows — P1.4.)*
- **S-Q2** Do Coeffs belong in the DATA FILE or the INPUT SCRIPT? (Both legal.) *(v0.3a: a Pair Coeffs section requires `pair_style` to be defined before `read_data`, unless `nocoeff` is used — SRC `read_data.cpp:807`, PRB T30b.)*
- **S-Q3** Are image flags required, forbidden, or optional in generated files?
- **S-Q4** Boundary condition per dimension (p / f / s / m)?
- **S-Q5** Are slabs, pores, or interfaces in scope, or bulk only?
- **S-Q6** Maximum benchmark system size (affects runtime, neighbour search, and the Tier 3 timeout).
- **S-Q7** *(new)* Must generated DATA FILEs carry a `units = <style>` hint on line 1 (as `write_data` does)? It gives LAMMPS a units-mismatch warning (P1.15).

---

## 7.5 Non-goals

1. **No LAMMPS INPUT SCRIPT generation as a deliverable** — keeps the certified artifact unambiguous.
2. **No full MD workflow** — scope ends at the starting DATA FILE.
3. **No autonomous force-field discovery or parameter invention** — every parameter comes from an owner-chosen, cited source.
4. **No arbitrary materials** — class B only.
5. **No reactive force fields** unless explicitly included under C.
6. **No unrestricted system sizes** — bounded by S-Q6.
7. **No production cluster submission** — Tier 3 runs locally on small checks.
8. **No modification of trusted reference files** — read-only.
9. **No silent fallback** to a different force field, atom_style, or units — any mismatch is a reported failure.
10. **No claim that passing Tiers 0–3 implies scientific correctness.**
11. *(new)* **No reliance on LAMMPS diagnostics as proof of correctness** — absence of a LAMMPS error or warning is never a PASS (PROPERTIES §8.2 item 6, §8.8).

---

## 7.6 Prior-work positioning (source-supported only)

*Unchanged from v0.2 and not re-checked in the 2026-10-02 audit.* Figures below were extracted during the 2026-09-30 research pass from the cited papers. Re-check against the papers before quoting them to a supervisor.

| Work | Artifact | Validation | Relevant Idea | Difference From This Project |
|---|---|---|---|---|
| Holbrook, Verduzco, Strachan — arXiv 2603.20630 | LAMMPS INPUT SCRIPTS generated by multiple LLMs across prompts of increasing complexity | Normalisation → grammar-based parser → reduced-cost execution → prompt-specific accuracy checks. Reports only 1 of 80 hardest-prompt scripts fully correct as generated; packages the stages as an agent-callable skill. | Staged, model-independent validation; cheap execution as a stage; validator as an agent tool. | Artifact is the INPUT SCRIPT; structures built inside LAMMPS; no DATA FILE topology/charge/type validation. |
| MDGym — arXiv 2605.08941 | Agent workflows on a set of LAMMPS/GROMACS tasks | Final outputs compared with reference results under a relative tolerance; engine errors categorised (including a "data file and read" category). | Silent wrong simulations and fabricated outputs are real agent failure modes. | Scores outputs, not the DATA FILE. |
| Paimon — arXiv 2606.09422 | INPUT SCRIPTS / workflows via LAMMPS, ASE, PACKMOL executors | Mainly LLM critics and LLM rubric grading; a lightweight deterministic structure summary (composition, cell volume, unphysically close pairs). | Benign / loud / silent error taxonomy. | No deterministic DATA FILE validator; validation is largely LLM-based. |
| URSA LAMMPS agent — arXiv 2607.22596 | INPUT SCRIPTS; potential selection | Error-recovery loop until the run succeeds. | Human-in-the-loop override. | Success = runs; metals; no DATA FILE validation. *(v0.3a: FM31/FM32 show "it runs" is a weak criterion; FM08/FM17 show `run 0` can "succeed" with PE = inf.)* |
| PolyJarvis — arXiv 2604.02537 | Polymer MD; data files built by deterministic builders (EMC / RadonPy) | Property comparison with experiment. | Deterministic code owns simulation inputs. | Property-level validation; a DATA FILE validator is not described (UNVERIFIED). |
| DATA FILE builders: moltemplate, EMC, ClayCode | DATA FILEs (moltemplate, EMC); GROMACS inputs with ClayFF (ClayCode) | Builder-internal | These are writers whose output the validator must check. | Not independent validators. |
| LLM crystal generation (e.g. CrystaLLM) | CIF text | Deterministic structural checks (formula, bond lengths, space group) | Deterministic validity checks on LLM output are established practice. | No topology, atom types, charges, or image flags; their tolerances are not transferable. |

**Positioning statement (SOURCE-SUPPORTED, limited).** Among the works reviewed, deterministic validation of the LAMMPS DATA FILE itself is not provided. Deterministic checking of LLM outputs is not new (R18, CrystaLLM); the project's contribution is its application to DATA FILE structural/topological corruption. A broader search (DATA FILE validators, converter test suites) is outstanding before any novelty claim.

---

## 7.7 Silent vs loud errors

- **LOUD ERROR.** LAMMPS stops with an ERROR under the declared validation configuration, or the Tier 0 parser rejects the file.
- **CRASH** *(new)*. LAMMPS terminates on a signal with no ERROR line (observed: SIGSEGV, exit 139, FM28). Treated as a Tier 3 FAIL (P3.4), never as a pass.
- **SILENT ERROR.** LAMMPS accepts the file (possibly with a WARNING) and a simulation can run, but the encoded system differs from the intended one. **Warnings count as silent** unless the warning policy (P3.3) elevates them.
- **LOUD@RUN** *(new)*. Accepted by `read_data` (and therefore by Tier 3a) but rejected at run setup (e.g. missing per-type masses or coefficients). Counted as silent for Tier 3a.

**FACT — LAMMPS behaviours that allow silent errors** (RD/AM docs fetched 2026-09-30; **verified against source and probes on 2026-10-02**, build 22 Jul 2025 – Update 6):
- Characters beyond 254 per line are ignored — CONFIRMED (SRC `read_data.cpp:49`, `utils.cpp:316`; PRB T8).
- A missing box keyword silently takes its default (lo/hi = −0.5 / 0.5) — CONFIRMED, **with no warning** (SRC `read_data.cpp:505-506`; PRB T5).
- The line after a section keyword is always skipped, whatever it contains — CONFIRMED (SRC `read_data.cpp:2509`).
- Atom IDs "should also be unique, though LAMMPS does not check for this" (AM) — **REFINED:** LAMMPS errors `Duplicate atom IDs exist` only when max ID < natoms (SRC `atom.cpp:929`; PRB T3a/b).
- A style comment on `Atoms # style` or a Coeff section that mismatches the current style produces only a warning — **CORRECTED:** it produces a warning only when the names differ in length and neither is a prefix of the other. Equal-length mismatches (e.g. `charge` vs `atomic`) are silent (SRC `read_data.cpp:2647`; PRB T2a).
- Tilt factors skewing the box by more than half the parallel box length produce only a warning — **CORRECTED:** the warning uses \|xy\|/l_y and (\|xz\|+\|yz\|)/l_z, not the documented rule, so documented violations can be silent (SRC `domain.cpp:217-222`; PRB T1a/b).
- Non-zero image flags in non-periodic dimensions are reset to zero, with a warning — CONFIRMED (PRB T13).
- Coordinates outside the box in periodic dimensions are remapped into the box without error — CONFIRMED (PRB T16); coincident atoms can then give PE = inf with exit 0 (T16b).
- "It is up to you to ensure atoms do not end up overlapping unphysically" (RD, `shift` context) — CONFIRMED (no distance check in source).
- *(new)* Exactly one surplus row at the end of the file is ignored (FM27; PRB T18b, T18f).
- *(new)* A repeated header keyword silently takes its last value (FM34; PRB T35).
- *(new)* Duplicate bonds, negative molecule IDs, and velocity rows for absent or duplicated IDs are accepted (FM05, FM30, FM29).
- *(new)* Missing or duplicated Masses/Coeff type rows pass `read_data … nocoeff` (FM31, FM32).
- *(new)* Units are checked only via an optional `units = X` hint on line 1, and only with a warning (FM03, P1.15).
- *(new)* Charge neutrality is checked only when a kspace style is active, only as a warning by default, and at a hard-coded 1e-5 (FM06).

**FACT — LAMMPS behaviours that make errors loud:** atoms outside the box in a non-periodic dimension are lost and read_data errors (`Did not assign all atoms correctly`); out-of-range atom/topology types are rejected; topology atom IDs ≤ 0, > max ID, or repeated within an entry are rejected. **Topology IDs that are absent but ≤ max ID crash LAMMPS** (FM28). See `FAILURE_MODES.md` for per-mode detail and verified message strings.

**PROJECT DECISION.** The project does **not** assume LAMMPS detects silent errors.

---

## 7.8 Oracle / ground truth

- **RECOMMENDED methodology.** 2–3 trusted group DATA FILEs that have run successfully in production, each with its working INPUT SCRIPT, LAMMPS version/build, and force-field source.
- *(v0.6)* **References for the decided system class.** PCE: the group's EMC files REF-01..04, now identified by the supervisor as the group's PCE data ("PCE files have data"); the PCE builder reproduces their composition and full topology counts exactly (`PCE_BUILDER.md`). Minerals: every INTERFACE cement-mineral model converted in each supported force field (`MINERALS.md`, `data/reference/minerals/`). Ion–oxygen contact floors come from published INTERFACE structures in which the ions are coordinated (montmorillonite Na⁺/K⁺, tobermorite Ca²⁺).
- *(v0.5)* **Published-model references for the adopted system class.** REF-05..REF-08 (tobermorite 11 Å / 14 Å unit and rectangular cells) and the eval-set references t01–t14 are built from the INTERFACE FF 1.5 model database by a documented deterministic pipeline (`scripts/build_references.py`: msi2lmp → tilt reduction → `scripts/supercell.py` → LAMMPS read/write). In place of production-use evidence they carry self-generated evidence (`docs/REFERENCE_EVIDENCE.md`): short MD runs clean with the lattice within 1 % of the published cell, and the energy per unit cell agrees across all 18 tobermorite files to 0.011 %. They are labelled **published model + documented pipeline + self-generated evidence; supervisor confirmation pending**.
- *(v0.4)* **Candidate references found:** four EMC v9.4.4 builds of PCE superplasticisers in `UGRP/PCEs/` (REF-01..REF-04, `data/reference/provenance.md`), each with its EMC INPUT SCRIPT and `.params` coefficient file. They pass Tiers 0–3 under the provisional configuration. They are **CANDIDATES, not oracles**: creator, responsible person and production-use evidence are not recorded, and they are PCE polymers, not C-S-H. Synthetic triclinic fixtures (tobermorite 11 Å / 14 Å from the INTERFACE FF database via msi2lmp) exercise triclinic code paths only.
- **A reference is trustworthy only if** it has: documented provenance; construction method; responsible person; cited force field; atom_style; units; LAMMPS version/build; evidence of successful use; known limitations.
- **Similarity ≠ correctness.** References can contain defects. Any disagreement between a generated file and a reference is a *finding* to investigate, compared property by property with documented tolerances — never an automatic verdict in either direction.
- **Roles of references.** (1) Source for Tier 2 calibration; (2) positive controls (must pass); (3) seeds for deliberately corrupted negative controls (must fail; operators in FAILURE_MODES §9.4).
- *(new)* **References must pass the v0.3a checks too.** Production files can predate these rules. A reference that fails a new property (e.g. P0.10, P0.11, P1.14) is investigated before it is used: either the file has a latent defect, or the property needs an explicit allow-list entry.

---

## 7.9 Open decisions

| ID | Open Question | Why It Matters | Required Evidence / Person | Blocking? |
|---|---|---|---|---|
| OD-B | System class / C-S-H model family | Composition, charge target, bond types, density, references | Owner + supervisor; model literature (e.g. brick model / pyCSH) | **BLOCKING** — Tier 2, benchmark |
| OD-C1 | atom_style | Atoms columns, molecule IDs, charge column, type column position | Owner | **BLOCKING** — P0.4, P1.3, P1.8, P1.11 |
| OD-C2 | Force field (citation, version, modifications) | Coeffs, charges, masses, bonded terms; water model (e.g. whether a TIP4P-family water model is used affects the INPUT SCRIPT and Tier 3b — UNVERIFIED specifics) | Owner; original FF paper | **BLOCKING** — Tier 3b, Tier 2 charge/mass |
| OD-C3 | Units style | Interpretation of distance, mass, charge | Owner (follows from FF) | **BLOCKING** — Tier 2, Tier 3, P1.15 |
| OD-D | Input representation | Target for task correctness | Owner | Not for Tiers 0–3 |
| OD-E | Confirm generation design (§7.3 E); hosted API vs local model | Error sources, baseline design | Owner | Not for validator |
| OD-F | LAMMPS version / build / packages used for validation | Tier 3 verdicts are version- and build-dependent | Owner / group admin. *(v0.3a: a candidate exists — local Homebrew 22 Jul 2025 Update 6 with MOLECULE and KSPACE; the owner must declare whether it or the group/cluster build is authoritative.)* | **BLOCKING** — Tier 3 |
| OD-G | Boundary conditions per dimension | Containment and image-flag rules | Owner | **BLOCKING** — P1.9, P1.12 |
| OD-H | Is charge neutrality required; target net charge | Charge criterion is system-specific | Owner + FF source | **BLOCKING** — P2.1 |
| OD-I | 2–3 trusted reference files | Oracle, calibration, controls | Research group | **BLOCKING** — Tier 2, TC, negative controls |
| OD-J | Element ↔ atom-type map | Mass and composition checks | Owner / FF typing scheme | **BLOCKING** — P2.6, TC.1 |
| OD-K | Support type-label sections? | Changes Tier 0/1 parsing of type fields | Owner | Not blocking (default: unsupported) |
| **OD-L** *(new)* | Tier 3 run settings: serial vs MPI, process count, `newton_bond`, timeout | Some behaviours (duplicate detection, crash paths, bond assignment) depend on these; all probes so far are serial with `newton_bond on` | Owner | Blocking for Tier 3 reproducibility |
| **OD-M** *(new)* | Encoding and line-ending policy (P0.12) | Converters on Windows/WSL may emit CRLF; LAMMPS accepts CRLF | Owner | Not blocking (RECOMMENDED default: ASCII + LF) |
| **OD-N** *(new)* | Tilt policy: the documented bound (RD), the source warning criterion (SRC), or both (P2.8) | They disagree (FM10) | Owner | Not blocking until triclinic references exist |

**When the owner gives an answer:** update this table and §7.3, change the status to LOCKED with the evidence, propagate to `PROPERTIES.md` and `SPEC_SUMMARY.md`, and log it in `LOG.md`.

---

## 7.10 Declared validation configuration record (new in v0.3a)

Every Tier 3 verdict and every Tier 1/2 property marked BLOCKED needs a declared configuration. Field list only; **values are OPEN until the owner decides** (no defaults are implied).

| Field | Example of the *form* (not a value) | Decided by |
|---|---|---|
| `units` | one LAMMPS units keyword | OD-C3 |
| `atom_style` | one LAMMPS atom_style keyword | OD-C1 |
| `boundary` | three of p/f/s/m | OD-G / S-Q4 |
| `pair/bond/angle/dihedral/improper/kspace styles` + coefficient source | style names + file reference | OD-C2, S-Q2 |
| `masses_location` | DATA FILE / INPUT SCRIPT | S-Q1 |
| `image_flag_policy` | required / optional / forbidden | S-Q3 |
| `units_hint_policy` | required / optional | S-Q7 |
| `net_charge_target`, neutrality required? | number + yes/no | OD-H |
| `element_type_map` | type → element | OD-J |
| `lammps_executable` | absolute path | OD-F |
| `lammps_build` | `-h` output file + version string + source tag + commit | OD-F |
| `run_mode` | serial / MPI N processes, `newton_bond` | OD-L |
| `tier3_timeout_s` | seconds | OD-L, S-Q6 |
| `warning_allow_list` | list of exact message texts | P3.3 |
| `encoding_policy` | ASCII+LF / ASCII+LF-or-CRLF | OD-M |
| `tilt_policy` | doc / source / both | OD-N |

The record is versioned. A change to any field invalidates the Tier 3 verdicts made under the previous version.

## 7.11 LAMMPS build policy (new in v0.3a)

- **FACT.** Local install on the owner's Mac: Homebrew `lammps` 20250722-update6, built from GitHub release `stable_22Jul2025_update6`. Executables: **`lmp_serial`** and **`lmp_mpi`** (not `lammps_serial` / `lammps_mpi` as earlier notes said). Packages include MOLECULE and KSPACE (`lammps_build.txt`).
- **RECOMMENDATION.** Pin Tier 3 to one declared build (OD-F). Record the `-h` output, version string, source tag and commit with every verdict.
- **RECOMMENDATION.** Whenever the build changes, re-run the probe suite (`source_audit/probe*.py`) and the failure-mode experiments (CLAUDE.md §8), diff the outcomes and message strings, and log the differences before trusting Tier 3 verdicts on the new build.
- **FACT.** The source and the documentation disagree in at least one place (tilt warning, FM10). For behaviour claims, the order of authority is: probe on the declared build > source at the matching tag > documentation.

## 7.12 Evaluation design (RECOMMENDATION — new in v0.3a; not to be implemented before the validator gate)

Build order (CLAUDE.md §3): validator → evaluation set → single-call baseline → tool layer → agent loop → evaluation.

**Validator quality (before any agent work).**
- **Positive controls:** every reference passes Tiers 0–1 and Tier 3a under its declared configuration (false-alarm rate on references = 0 required).
- **Negative controls:** every corruption operator (FAILURE_MODES §9.4) applied to every reference is caught by its mapped property. Report the detection rate per FM and per tier. Report separately which corruptions LAMMPS alone catches (Tier 3 only), to quantify the validator's added value.

**Generator quality (agent and baseline).**
- Per task, run **3–5 repeats** (LLM outputs vary).
- Report per tier: the PASS rate, the NOT_CALIBRATED / NOT_EVALUATED share (never folded into PASS), and the first failing property.
- Attribute Tier 3b failures to DATA FILE vs configuration (§8.1 of PROPERTIES).
- Compare the single-call baseline and the agent loop on the same tasks and seeds where the API allows.
- Record model ID, API version, temperature and prompt version from the provider's documentation on the day of the run (no IDs or prices from memory).

## 7.13 Risks and threats to validity (new in v0.3a)

| Risk | Effect | Mitigation |
|---|---|---|
| Build dependence of LAMMPS behaviour and messages | Tier 3 verdicts and the "LAMMPS if violated" column change between builds | §7.11 pinning + probe re-run |
| Serial-only probes | MPI may detect or miss different defects (e.g. duplicate IDs across processes) | OD-L; re-probe under the declared run mode |
| References with latent defects | Calibration absorbs errors; negative controls are mislabelled | §7.8 rule: references must pass v0.3a checks first |
| Validator stricter than production practice | Real, working files may FAIL (e.g. comment rows, CRLF) | Allow-list with recorded justification; never silently relax a property |
| ASE/pymatgen claims not re-verified | FM01–FM03, FM09, FM15, FM23 evidence relies on a single research pass | Reproduce R13 (FAILURE_MODES §9.3) during the validator phase |
| Prior-work figures not re-checked | Novelty and positioning statements may be wrong | Re-read the papers before supervisor use (§7.6) |
| Small synthetic probes | Behaviour on large systems (chunked reading, CHUNK = 1024 lines) is untested | Repeat key probes with > 1024-row sections |

---

## 7.14 Validator-phase status and provisional values (v0.4; updated v0.5)

**Built (plan Days 5–16):** own parser, Tiers 0–3, TC layer, local/SSH/Docker backends, calibration records, 49 corruption operators, validation matrix. Results: `VALIDATOR_RESULTS.md` (v0.5: 24/24 positive controls pass; 448/448 corrupted files rejected, 439 by the validator's own Tier 0–2 checks, 9 only by TC.2; the validator fails exactly the 6 of 10 LAMMPS-replicated supercells that TC.2 shows to be wrong). Implementation map: PROPERTIES §8.10.

**Primary configuration `configs/interface_pcff_tobermorite.yaml` (PROVISIONAL DEFAULT, v0.5):** units real · atom_style full · boundary p p p · masses and all coefficients in the DATA FILE (class II sections allowed) · coordinates wrapped, image flags optional, no unwrapped-coordinate check (infinite bonded crystal) · tilt: documented bound and source criterion, FAIL · neutral, statistical charge floor · molecule-ID/bond policy: report · bonded-term consistency and completeness required · Tier 3b: class2 styles, `special_bonds lj/coul 0 0 1`, **Ewald 1e-4** (this build's PPPM segfaults on most tobermorite supercells, FAILURE_MODES §9.6) · build: Homebrew `lmp_serial` 22 Jul 2025 – Update 6.

**Secondary configuration `configs/emc_pcff_real_full.yaml`** (PCE candidates REF-01..04) is kept as a regression set; its v0.4 provisional values are unchanged except the statistical charge floor and the PPPM crash fallback:

| Open item | Provisional value | Evidence |
|---|---|---|
| OD-C1 atom_style | `full` | REF-0*.in |
| OD-C2 force field | PCFF-type class 2 (`lj/class2/coul/long`, class2 bonded styles, `pppm/cg`, fallback Ewald on a crash), coefficients in the EMC `.params` include | REF-0*.params (`field cff/basf/basf`) |
| OD-C3 units | `real` | REF-0*.in |
| OD-F build | local Homebrew `lmp_serial` 22 Jul 2025 – Update 6 (`docs/lammps_build.txt`) | installed build |
| OD-G boundary | `p p p` | REF-0*.in sets none → LAMMPS default |
| OD-H charge | neutrality required, target 0, τ_Q = statistical rounding floor (PROPERTIES §8.5 rule 3, v0.5) | references sum to 0.0000 e |
| OD-J type map | PCFF type names → elements (`type_name_elements`) | Masses values + comments |
| OD-L run mode | serial, `newton_bond on` (default) | — |
| OD-M encoding | ASCII + LF | RECOMMENDED default |
| OD-N tilt | both the documented bound and the source criterion; violations FAIL | — |
| S-Q1 masses | in the DATA FILE — **and** re-set by the `.params` `mass` commands (FAILURE_MODES §9.6) | REF-0*.params |
| S-Q2 coefficients | INPUT SCRIPT (include file) | REF-0*.params |
| S-Q3 image flags | optional; whole (unwrapped) molecules | REF-0*.data, EMC `unwrap -> true` |

**Observation relevant to OD-B / OD-C (not a decision).** The project folder pairs EMC/PCFF PCE models with the INTERFACE FF 1.5 cement-mineral database (PCFF-INTERFACE, the same class 2 functional form) and its tobermorite models. That is consistent with a PCE-on-tobermorite/C-S-H study in PCFF-INTERFACE, but the owner has not said so; B and C remain OPEN.

**Still blocking certification as "trusted":** OD-I (references with provenance and production evidence), OD-B (a C-S-H reference family to calibrate against), the ±2 % density placeholder (PROPERTIES §8.11), and owner review of the margins.

## 7.15 Default-unless-objection record (new in v0.5)

- **2026-10-17/18:** the supervisor did not respond to the questions on system class and references (LOG). Gate 1 and the eval-set start (19 Oct) required a choice.
- **2026-10-19:** the owner adopted the recommended defaults (B, C, D, E above; references per §7.8) and is to send the supervisor a "proceeding unless you object" note with a deadline.
- **Reversibility.** Every consequence is regenerated by scripts: a different system class means new models in `scripts/build_references.py`, a new declared configuration, `scripts/calibrate.py`, `scripts/mutate.py`, `scripts/run_matrix.py`. The validator code does not change. Group production files, if they appear, replace or join REF-05..08 as references (provenance.md §D rules apply).
- **What would change the choice:** the group uses CLAYFF/ERICA instead of INTERFACE FF; the target is C-S-H with defects (brick model) rather than crystalline tobermorite; the study needs surfaces or PCE adsorption in the first evaluation.

## 7.16 Supervisor directive, 2026-10-20 (new in v0.6)

Message forwarded by the owner on 2026-10-20 (verbatim): *"you have structural files of a couple of minerals that i have shared right ? let it learn about all. F.F is our choice , try to get a PCE lammps data for any 2 force filed (class 1 and class2) . it should be able to generate the structure of pce for any architecture, user defined number of side chains, main chains etc ....PCE files have data and cement_minerals have structural file of minerals"*

| Directive | How it is met (2026-10-20) | Evidence |
|---|---|---|
| Learn all minerals | `builders/minerals.py` builds any INTERFACE model (any supercell) in PCFF-INTERFACE and, where parameters exist, CVFF-INTERFACE; references for all 27 usable cement-mineral models | `MINERALS.md` |
| Force field is our choice; PCE data in a class I and a class II force field | CVFF-INTERFACE (class I) and PCFF-INTERFACE (class II); every example PCE built in both | `PCE_BUILDER.md` |
| PCE of any architecture (side chains, main chains, …) | `builders/pce.py`: architecture JSON (monomer kinds, side-chain number/length/anchor/end group, acid kind and protonation, sequence mode, number of chains, counter-ion, box); deterministic, seeded; refuses rather than writing missing parameters | `PCE_BUILDER.md`, `tests/test_builders.py` |
| PCE files have data; minerals have structure files | EMC PCE data = REF-01..04 (validation references; reproduced exactly by the builder); `CEMENT_MINERALS` = the INTERFACE model database | provenance.md |

"Main chains" was read as the number of polymer chains (`n_chains`) and the backbone length (sum of the composition); both are parameters. *(2026-10-26: the supervisor confirmed the backbone length; §7.17.)*

## 7.17 Supervisor replies, 2026-10-26 (new in v0.7)

Five questions were sent with a default for each (owner, 2026-10-26). Replies as relayed by the owner, with what was done:

| # | Question | Reply (verbatim where given) | Consequence |
|---|---|---|---|
| Q1 | Does "main chains" mean the number of chains or the backbone length? | **"b"** — the backbone length (monomer units per chain) | No code change: the backbone length is the composition (or `n_acid` + `n_side_chains`). Task wording uses "units"; `n_chains` stays a separate parameter. |
| Q2 | PCE adsorbed on a mineral surface in this evaluation, or future work? | **"yes a combined builder"** | `builders/composite.py` (PCE on any INTERFACE slab, both force fields; class I limited to C3S/C3A); configs `interface_{pcff,cvff}_composite.yaml`; calibration `composite_{ff}.json`; eval set v3 adds six composite tasks c01–c06 (split extended, existing assignments kept). |
| Q3 | Tier 2 tolerances (bond ±10 % beyond the reference range, overlap at 75 % of the closest contact, dense-PCE density ±2 %) | **Accepted**, "along with the given suggestion": *"After making PCE, it just have to be inside a box, let it be a box slightly bigger than the bounds of the atoms of PCE"* | The margins lose their PLACEHOLDER label (calibration basis text). `builders/pce.py` relaxes in a roomy box, then shrinks it to the atom bounds + 2 Å per face. New property **P2.10 box_margin** checks 1 Å ≤ margin ≤ 5 Å on every face for builder PCE files (window PROVISIONAL: the reading of "slightly"). Builder PCE density stays NOT_APPLICABLE (isolated molecule). |
| Q4 | Which LAMMPS build is the reference for Tier 3? | No reply | Default kept: Homebrew 22 Jul 2025 Update 6 (serial), Ewald where PPPM crashes; stated in the report (§7.11). |
| Q5 | Provenance of the EMC PCE files (c12e12p15, c6e18p15, c18e6p15, pce_1) | **"whether they were used in actual production simulations"** — read as: yes, they were used in production simulations | REF-01..04 trust status raised to "group production data" (REFERENCE_EVIDENCE.md); who built them remains undocumented. If the reply was a question back rather than a confirmation, revert this line. |

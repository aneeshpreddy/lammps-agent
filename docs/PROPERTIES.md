# PROPERTIES — Correctness Model for LAMMPS DATA FILEs

Version 0.4 (2026-10-16, validator phase). Supersedes v0.3a (2026-10-02). Tolerance-bearing properties now have **PROVISIONAL** calibrations derived from candidate references (§8.11); they remain provisional until the owner confirms the references as trusted (OD-I) and accepts the margins.

**Changes v0.3a → v0.4** (all driven by the validator-phase experiments in `VALIDATOR_RESULTS.md`; nothing silently relaxed):
- New **P1.16** topology-type signatures and **P1.17** bonded-term completeness (both configuration-gated); new clause **P2.1(b)** (a charged system must carry non-zero charges).
- New verdict **NOT_APPLICABLE** (§8.2) for properties that do not apply under the declared configuration; it is distinct from NOT_EVALUATED.
- P3.3: the zero-style warnings that `read_data … nocoeff` itself causes are recorded as Tier 3a mode artefacts, not DATA FILE warnings.
- P2.7: τ_img gains a floating-point floor (a writer printing 17 digits drove the derived τ below double-precision noise).
- TC.2 implemented: atoms are matched by position (renumbering is not a difference); Coeff sections written in the DATA FILE are compared too.
- §8.10 implementation status and §8.11 calibration record added.

**Sources.**
- *RD*: LAMMPS `read_data` doc (https://docs.lammps.org/read_data.html, fetched 2026-09-30).
- *AM*: `atom_modify` doc.
- *SRC*: LAMMPS source, tag `stable_22Jul2025_update6` (commit `9c5ab448c`), read 2026-10-02.
- *PRB*: probe experiments T1–T39 on `lmp_serial` 22 Jul 2025 – Update 6 (`source_audit/`).
- *PR*: project rule (stricter than LAMMPS, with a stated reason).

Where RD and SRC disagree, the property states both. LAMMPS-behaviour statements are build-dependent (SPEC §7.11).

**Totals:** 42 properties across Tiers 0–3 (Tier 0: 12 · Tier 1: 17 · Tier 2: 8 · Tier 3: 5) plus 2 task-correctness (TC) properties.
New in v0.4: P1.16, P1.17. New in v0.3a: P0.10, P0.11, P0.12, P1.15, P3.4. v0.2 had 34.

---

## 8.1 Tier definitions

- **Tier 0 — Parseable.** The file can be read into a well-defined structure: header, recognised sections, row syntax, numeric fields, Atoms columns for the declared atom_style, box representation.
- **Tier 1 — Internally consistent.** The parsed content agrees with itself: counts vs rows, unique IDs, types in range, Masses/Coeff consistency where present or required, topology references, image-flag structure. **No section is universally required**; requirements depend on atom_style and the declared configuration.
- **Tier 2 — Physically plausible.** System-specific criteria with tolerances derived from references or explicit requirements. **Plausible ≠ correct.**
- **Tier 3 — LAMMPS acceptance under the project's declared LAMMPS validation configuration.** A DATA FILE has no context-free notion of "LAMMPS acceptance". Acceptance depends on units, atom_style, boundary, force-field setup, package/style availability, coefficient handling, and LAMMPS version/build.
  - **Tier 3a — structure-only:** `read_data <file> nocoeff`. FACT (RD): with `nocoeff`, Coeff sections "are still read and have to have the correct number of lines, but they are not applied". FACT (SRC `read_data.cpp:429-470`, PRB T19): the pair/bond/… styles are temporarily replaced by `zero` styles, and Coeff row counts are still enforced. **FACT (SRC, PRB T11, T31): Tier 3a does not detect missing or duplicated Masses or Coeff type rows.** These are detected only at run setup, so P1.4 and P1.7 must cover them.
  - **Tier 3b — full force-field:** the declared INPUT SCRIPT plus `run 0`. FACT (LAMMPS run doc): with N = 0 only thermodynamics are computed and printed, without taking a timestep. FACT (PRB T16b): `run 0` can exit 0 with PE = inf.
  - **3a ≠ 3b.** In 3b every failure is attributed either to the **DATA FILE** (e.g. a wrong type count) or to the **force-field / INPUT SCRIPT configuration** (e.g. a missing package). Only DATA FILE failures count against the generator.
- **Task-correctness layer (TC).** Correctness relative to the request and trusted references. OPEN until OD-D and OD-I are resolved.

## 8.2 Evaluation order and verdicts

1. Tier 0 runs first. **A Tier 0 failure stops all further evaluation** (the file has no reliable parsed structure).
2. If Tier 0 passes, Tier 1 runs.
3. Tier 2 checks whose inputs depend on a failed Tier 1 structure return NOT_EVALUATED; independent Tier 2 checks still run.
4. **Tier 3 runs whenever Tier 0 passes**, regardless of Tier 1/2 outcomes, for diagnostic purposes.
5. Verdicts: PASS · FAIL · NOT_EVALUATED · NOT_CALIBRATED · NOT_APPLICABLE *(v0.4)*. **NOT_CALIBRATED never counts as PASS.** NOT_APPLICABLE means the declared configuration makes the property irrelevant (e.g. P1.12 when every dimension is periodic, P2.7 without a declared use of unwrapped coordinates); it is the only non-PASS verdict that does not block certification. A file is certified (`passed`) only if every Tier 0–3 check is PASS or NOT_APPLICABLE.
6. *(new)* **No property may be satisfied by "LAMMPS would catch it".** The column "LAMMPS if violated" in §8.3 is diagnostic information only. Tier 0–2 verdicts come from the validator's own parser.

---

## 8.3 Property table

Column "LAMMPS if violated" (new) records this build's behaviour: Silent · Warn · Loud · Loud@run (passes `read_data`, errors at run) · Crash (signal, no ERROR line).

| ID | Property | Tier | Deterministic Check | Dependencies | Required Inputs | Failure Meaning | LAMMPS if violated | Source | Calibration Status |
|---|---|---|---|---|---|---|---|---|---|
| P0.1 | Header structure | 0 | Line 1 is skipped unconditionally (but see P1.15). Each later line: strip a trailing comment beginning with `#` that is preceded by at least one blank; skip blank lines; each non-blank line until the first section keyword must match exactly one recognised header keyword with the correct number of leading values, followed by whitespace or end of line. The first non-header, non-blank line must be a section keyword. | — | DATA FILE | Header misread | Loud (`Unknown identifier in data file: …`, T6, T34) | RD; SRC `read_data.cpp:1263-1519`: LAMMPS strips from **any** `#` (1320), and its regexes need whitespace after the keyword, so `4 atoms#c` is Loud (T6). PR: require a blank before `#` | Exact |
| P0.2 | Section names | 0 | Every section keyword is in the recognised list, with exact capitalisation, single spaces between words, leading/trailing whitespace allowed, and an optional trailing `# style` comment. Recognised-but-unsupported sections (type labels, class 2, Ellipsoids/Lines/Triangles/Bodies) → FAIL "unsupported in scope". | P0.1 | DATA FILE | Section ignored or misparsed | Loud (T10, T28); trailing spaces accepted (T27) | RD; SRC list `read_data.cpp:61-71`, matched with `strcmp` after trimming (2543-2550); scope (SPEC §7.4) | Exact |
| P0.3 | Numeric syntax | 0 | Integer fields match `^[+-]?\d+$`; float fields match the LAMMPS float grammar (digits, optional `.`, optional `e/E` exponent; **no** `nan`, `inf`, `D` exponents, or decimal commas) and are finite. Which Atoms fields are integers depends on atom_style. | P0.2; OD-C1 for Atoms rows | DATA FILE | Garbage values | Loud (T7a, T7b, T37) | RD ("must be integers (1, not 1.0)"); SRC `utils.cpp:1697-1716` (`is_integer`, `is_double`); PR (finite) | Exact; Atoms part BLOCKED (OD-C1) |
| P0.4 | Atoms columns | 0 | Each Atoms row has exactly k or k+3 fields (after comment strip) for the declared style. atomic: `atom-ID atom-type x y z` (k=5); charge: `atom-ID atom-type q x y z` (6); molecular / bond / angle: `atom-ID molecule-ID atom-type x y z` (6); full: `atom-ID molecule-ID atom-type q x y z` (7). Image flags on all rows or none. Fields are separated by spaces or tabs. | OD-C1 | DATA FILE, atom_style | Wrong style or corrupt columns | Loud if the count differs from the **first** row; **Silent if counts are equal** and values are in range (FM07) | RD; SRC `fields_data_atom` in `atom_vec_atomic.cpp:32`, `atom_vec_charge.cpp:40`, `MOLECULE/atom_vec_bond.cpp:41`, `atom_vec_molecular.cpp:54`, `atom_vec_full.cpp:56`; `atom.cpp:1111,1199`; PRB T14, T26 | Exact; BLOCKED (OD-C1) |
| P0.5 | Box representation | 0 | Orthogonal (`xlo xhi`, `ylo yhi`, `zlo zhi`) or restricted triclinic (plus `xy xz yz`). General-triclinic keywords (`avec`, `bvec`, `cvec`, `abc origin`) → FAIL "unsupported" (scope). lo < hi in every dimension. | P0.1 | DATA FILE | Ill-defined cell | lo ≥ hi: Loud `Box bounds are invalid or missing` (T23). General triclinic: **accepted** by this build | RD; SRC `domain.cpp:210`, `read_data.cpp:537-545`; scope | Exact |
| P0.6 | Line length | 0 | Every line ≤ 254 characters (excluding the line terminator). | — | DATA FILE | Excess is silently ignored by LAMMPS | Silent (T8: `5.123456789` → `5.12`) | RD; SRC `read_data.cpp:49` (MAXLINE 256), `utils.cpp:316-345` | Exact |
| P0.7 | Line after section keyword | 0 | The line immediately after each section keyword is blank. | P0.2 | DATA FILE | LAMMPS skips that line unconditionally; a data row placed there would be discarded | Usually Loud (T9, T9b, T9c, T29); not guaranteed | RD; SRC `read_data.cpp:2509`; PR (require blank) | Exact |
| P0.8 | Explicit box keywords | 0 | `xlo xhi`, `ylo yhi`, `zlo zhi` lines are all present (and `xy xz yz` if the box is intended triclinic). | P0.1 | DATA FILE | LAMMPS would silently use defaults (lo/hi = −0.5 / 0.5) | **Silent, no warning** (T5) | RD; SRC `read_data.cpp:505-506` (flags never checked); PR | Exact |
| P0.9 | Section ordering | 0 | Bonds, Angles, Dihedrals, Impropers and Velocities appear after Atoms. | P0.2 | DATA FILE | Section cannot be read correctly | Loud (`Must read Atoms before …`) | RD; SRC `read_data.cpp:734-763` | Exact |
| **P0.10** | **Header keyword uniqueness** *(new)* | 0 | Each header keyword (`atoms`, `atom types`, `bonds`, `bond types`, …, each box line, tilt line) appears at most once. | P0.1 | DATA FILE | Conflicting header values | **Silent**: the last value wins (T35) | SRC header loop overwrites (`read_data.cpp:1343-1505`); PR | Exact |
| **P0.11** | **No surplus content after a section** *(new)* | 0 | After reading exactly *N* rows of a section (N from the header, or `atom types` etc. for Masses/Coeffs), every line up to the next section keyword or EOF is blank or a full-line comment. | P0.2, P0.10 | DATA FILE | Extra rows ignored or misread | **Silent** for exactly one surplus row at EOF (FM27, T18b, T18f); Loud otherwise (T18c–e) | SRC `read_data.cpp:2490-2521`; PR | Exact |
| **P0.12** | **Encoding and line endings** *(new)* | 0 | File is plain ASCII text (no BOM, no NUL, no non-ASCII bytes outside comments); line endings LF or CRLF, consistently; final line terminated. | — | DATA FILE | Tool-chain disagreement on content | CRLF and tabs accepted (T25, T26); non-ASCII not tested | SRC (`\r` treated as whitespace in `parse_keyword`, tokenizer); PR | Exact; **policy OPEN (OD-M)**: RECOMMENDED default is ASCII + LF |
| P1.1 | Counts vs rows | 1 | For atoms, bonds, angles, dihedrals and impropers: header count = number of section rows. Count > 0 with section absent → FAIL. Section present with count 0 → FAIL. The Atoms section must exist if natoms > 0. | P0.*, P0.11 | Parsed file | Missing or extra entries | Loud (`Bonds section for N bonds not found`, `Invalid data file section: Bonds` T24, `No valid atoms found`, `Did not assign all atoms correctly`), except FM27 (Silent) | RD; SRC `read_data.cpp:742,1056,1076-1081,1599` | Exact |
| P1.2 | Unique positive atom IDs | 1 | All atom IDs are positive integers and pairwise distinct. (IDs need not be contiguous or start at 1.) | P1.1 | Atoms | Duplicate or invalid IDs | Zero/negative: Loud. Duplicates: **Loud only if max ID < natoms**, else Silent (T3a/b). Non-contiguous IDs accepted (T36) | AM; SRC `atom.cpp:907-931` | Exact |
| P1.3 | Atom types in range | 1 | 1 ≤ atom-type ≤ `atom types` for every Atoms row; declared-but-unused types → WARN. Type column position depends on atom_style. | P1.1, OD-C1 | Atoms | Type corruption | Loud (`Invalid atom type …`); unused types: Silent | RD; SRC `atom.cpp:1273-1294` | Exact; BLOCKED (OD-C1) |
| P1.4 | Masses | 1 | If present: exactly one row per type 1…N (each type ID exactly once), 2 fields per row, each mass finite and > 0. If S-Q1 requires Masses in the DATA FILE: absence → FAIL. | P1.3, S-Q1 | Masses | Wrong or missing masses | Bad format / type / mass ≤ 0: Loud. **Duplicated or missing type rows: Loud@run only** (`Not all per-type masses are set`, T11), invisible to Tier 3a | RD; SRC `atom.cpp:1952-2006`, `2084-2091`, `782` | Exact; requirement OPEN (S-Q1) |
| P1.5 | Topology references | 1 | Every atom ID referenced in Bonds/Angles/Dihedrals/Impropers **exists in Atoms**; no atom repeated within one entry; topology type within 1…N of its kind. | P1.2 | Topology | Dangling or malformed topology | ID ≤ 0 or > max, or repeated: Loud. **Absent ID ≤ max ID: Crash (SIGSEGV) or `Bonds assigned incorrectly`** (FM28, T4a/b) | RD; SRC `atom.cpp:1399-1403,1497,1610,1738`; `special.cpp:217` | Exact |
| P1.6 | Topology uniqueness | 1 | Topology entry IDs distinct within each section; no duplicate entry under canonical order: bond {i,j}; angle (i,j,k) ≡ (k,j,i); dihedral (i,j,k,l) ≡ (l,k,j,i). Improper equivalence depends on improper style → OPEN. | P1.5 | Topology | Double-counted interactions | Silent (T4c) | PR; SRC (no check) | Exact; impropers OPEN |
| P1.7 | Coeff sections | 1 | Row count per section: Pair Coeffs = N_atomtypes; PairIJ Coeffs = N(N+1)/2 with I ≤ J; Bond/Angle/Dihedral/Improper Coeffs = one per type of that kind. **Each type ID (or I,J pair) appears exactly once.** Parameter count per row matches the declared style (full mode only). | P1.3; OD-C2; S-Q2 | Coeffs, declared styles | Coefficients misaligned | Row count: Loud even with `nocoeff` (T19). **Duplicated/missing type rows: Silent under `nocoeff` (T31), Loud@run** (`All pair/bond coeffs are not set`, T30', T31'). Permuted values: Silent | RD; SRC `read_data.cpp:2149-2330` | Row counts exact; parameter counts BLOCKED (OD-C2) |
| P1.8 | Molecule IDs | 1 | Where the style carries molecule IDs: integer ≥ 0 (RD: 0 allowed for non-bonded atoms). Bonds crossing molecule IDs → reported; policy OPEN. | P0.4, OD-C1 | Atoms, Bonds | Molecule bookkeeping corrupt | **Silent for negative IDs** (T21) | RD; SRC (no sign check found); PR | Partly OPEN |
| P1.9 | Image-flag structure | 1 | If present: three integers on every Atoms row; zero in every non-periodic dimension of the declared boundary. | P0.4, OD-G | Atoms, boundary | LAMMPS would reset non-periodic flags | Warn (`Non-zero imageflag(s) in z direction for non-periodic boundary reset to zero`, T13); partial rows: Loud (T14) | RD; SRC `atom.cpp:1208-1216`, `read_data.cpp:1575-1588` | Exact; BLOCKED (OD-G) |
| P1.10 | Bonded-term consistency | 1 | Angle (i,j,k) has bonds i–j and j–k; dihedral (i,j,k,l) has bonds i–j, j–k, k–l — **only if** the declared FF convention requires it. | P1.5, OD-C2 | Topology | Inconsistent angles/dihedrals | Silent (no check) | PR | Applicability OPEN |
| P1.11 | Style comments | 1 | If `Atoms # <style>` or Coeff `# <style>` comments are present, they **exactly** equal the declared styles (after removing the accelerator suffixes LAMMPS ignores: `/gpu`, `/opt`, `/omp`, `/kk`, …). | P0.2, OD-C1 | DATA FILE, declared styles | Mislabelled file | **Warn or Silent**: LAMMPS treats equal-length or prefix names as matching (FM33, T2a) | RD; SRC `read_data.cpp:2630-2648`, suffix list `75-77`; PR | Exact |
| P1.12 | Non-periodic containment | 1 | In every non-periodic dimension (`f`, `s`, `m`): lo ≤ coordinate < hi. Triclinic boxes use fractional coordinates: 0 ≤ s < 1 (§8.4). | P0.5, OD-G | Atoms, box, boundary | Atoms would be lost; read_data errors | Loud `Did not assign all atoms correctly` (T17, T17b, T32, T33, T33b) | RD; SRC `atom.cpp:1254-1261` (lamda coordinates for triclinic) | Exact (orthogonal: PRB; triclinic: SRC + T32; shrink-wrapped: PRB T33/T33b) |
| P1.13 | Topology type counts | 1 | Max topology type used ≤ header type count; header type count > 0 if entries of that kind exist. | P1.5 | Parsed file | Header corrupted | Loud (`Invalid bond type …`, `Bonds defined but no bond types`) | RD; SRC `atom.cpp:1402`, header checks | Exact |
| P1.14 | Velocities | 1 | If present: exactly natoms rows, one row per atom ID, each ID once, each ID existing in Atoms. | P1.2 | Velocities | Velocity misassignment | **Silent** for absent IDs ≤ max and duplicates (T20a, T20b); too few rows at EOF: Loud (T39) | RD; SRC `atom.cpp:1307-1334` | Exact |
| **P1.15** | **Units hint consistency** *(new)* | 1 | If line 1 contains `units = <style>`, `<style>` equals the declared units (OD-C3). Whether generated files must carry the hint is S-Q7. | OD-C3, S-Q7 | Line 1, declared units | Unit mismatch signalled by the writer | Warn (`Inconsistent units in data file: …`, T12) | SRC `read_data.cpp:1287-1292`, `write_data.cpp:288` | Exact; BLOCKED (OD-C3) |
| **P1.16** | **Topology-type signatures** *(v0.4)* | 1 | (a) Each bond/angle/dihedral/improper type ID joins exactly one canonical atom-type signature (bond {a,b}; angle/dihedral up to reversal; improper as a multiset). (b) Where coefficient rows carry type-name comments (EMC `.params` `# c3',c43`; msi2lmp Coeff sections `# sc2-oc12`), the observed signature equals the commented one. Type names come from the Masses `# name` comments or the declared configuration. | P1.5, OD-C2 | Topology, Masses comments, coefficient comments | Atom types or Coeff rows relabelled; same-element type swaps | Silent | PR; holds on REF-01..04 and FIX-T11/T14 (96 / 95 commented signatures matched on the references) | Exact; configuration-gated (`topology_signature_policy`) |
| **P1.17** | **Bonded-term completeness** *(v0.4)* | 1 | Converse of P1.10, for writers that derive bonded terms from the bond graph: every bonded triple has an angle; every bonded path i–j–k–l (i ≠ l) has a dihedral; every atom with n ≥ 3 neighbours has the C(n,3) impropers (central atom at the declared index). | P1.5, OD-C2 | Topology | Angles/dihedrals/impropers dropped (e.g. ASE round trip) with a consistent header | Silent | PR; exact on all six parents (e.g. REF-01: 2724 / 3309 / 1664) | Exact; configuration-gated (`bonded_term_completeness`) |
| P2.1 | Net charge (system-specific) | 2 | (a) \|ΣQ − Q_target\| ≤ τ_Q. Q_target and whether neutrality is required are defined by OD-H. (b) *(v0.4)* If the declared configuration describes a charged system, at least one charge is non-zero (zeroing every charge keeps ΣQ = 0). | P0.4, OD-H | Charges | Charge loss or unintended net charge | Warn at setup with kspace only, at a hard-coded 1e-5 (T15a). **Do not reuse 1e-5 as τ_Q** (§8.5 rule 7) | Methodology (§8.5); SRC `kspace.cpp:32,326-331` | NOT CALIBRATED |
| P2.2 | Cell / coordinate consistency | 2 | Fractional coordinates s = H⁻¹(r − origin). Report atoms with s outside [0,1) per periodic dimension; FAIL per declared wrapping policy or beyond τ_cell. | P0.5, OD-G | Box, coordinates | Scaling, shift, or unit errors | Silent remap (T16) | RD; Howto_triclinic; SRC `atom.cpp:1250` | NOT CALIBRATED |
| P2.3 | Atom overlap | 2 | Minimum-image distance d_ij ≥ d_min(type_i, type_j) for all pairs (periodic neighbour search). | P2.2, OD-I, OD-J | Coordinates, box, type map | Overlaps or duplicated sites | Silent at read_data; PE = inf possible at run (T16b) | RD | NOT CALIBRATED |
| P2.4 | Bond lengths | 2 | Minimum-image bond length ℓ ∈ [ℓ_lo, ℓ_hi] per bond type. | P1.5, OD-C2, OD-I | Bonds, coordinates, box | Wrong partners or broken bonds | Silent at read_data; run-time `Bond atoms … missing` if beyond the communication cutoff | Methodology; SRC `ntopo_bond_all.cpp:59,81` | NOT CALIBRATED |
| P2.5 | Density | 2 | ρ = Σm / V with V = det H = l_x·l_y·l_z; convert per declared units; compare to the reference range. | P1.4, OD-C3, OD-I | Masses, box | Scaling, missing atoms, unit error | Silent | Howto_triclinic (V) | NOT CALIBRATED |
| P2.6 | Mass-to-element | 2 | \|m_t − m_ref(E(t))\| ≤ τ_m for each atom type t, using the FF's mass table and the OD-J type map. | P1.4, OD-J | Masses, type map | Wrong mass/type mapping | Silent | Methodology | NOT CALIBRATED |
| P2.7 | Bond image consistency | 2 | **Only if a declared downstream use needs unwrapped coordinates** (e.g. rigid bodies, `replicate`, unwrapped analysis; RD examples): for each bond, the unwrapped bond vector (using H·n) equals the minimum-image vector within τ_img. Otherwise NOT_EVALUATED. | P1.9, P2.4 | Coordinates, image flags, bonds | Bonds stretched on unwrap | Warn at run setup `Inconsistent image flags` (T38) | RD (incl. "If your system is an infinite periodic crystal with bonds then it is impossible to have fully consistent image flags"); SRC `domain.cpp:960-1060` | NOT CALIBRATED; applicability OPEN |
| P2.8 | Tilt bound | 2 | \|xy\| ≤ l_x/2; \|xz\| ≤ l_x/2; \|yz\| ≤ l_y/2 (documented bound). | P0.5 | Box | Strongly skewed cell | **Warns on a different criterion**: \|xy\|/l_y > 0.5 (y periodic) or (\|xz\|+\|yz\|)/l_z > 0.5 (z periodic). T1a: doc bound broken, no warning; T1b: doc bound met, warning | RD / Howto_triclinic (bound); SRC `domain.cpp:217-222` (warning) | Exact bound; WARN vs FAIL policy OPEN; **whether the project uses the doc bound, the source criterion, or both is OPEN** |
| P3.1 | Tier 3a acceptance | 3 | Run `read_data <file> nocoeff` under the declared configuration: P3.4 outcome = clean exit; no line beginning "ERROR"; atom/topology counts in the log (`  N atoms`, `  N bonds`, …) equal the header counts. | P0.* (P1 for diagnostics); OD-C1, OD-C3, OD-F, OD-G | File, declared config, LAMMPS executable | Rejected by LAMMPS | — | RD; SRC `read_data.cpp:429-470`; PRB | BLOCKED |
| P3.2 | Tier 3b acceptance | 3 | Run the declared INPUT SCRIPT with `run 0`: P3.4 outcome = clean exit; no "ERROR"; **every thermodynamic value finite** (PE = inf with exit 0 observed, T16b). Attribute each failure to DATA FILE vs configuration (§8.1). | P3.1, OD-C2, OD-F | File, INPUT SCRIPT, FF files | FF setup fails on this file | — | LAMMPS run doc; PRB T16b | BLOCKED |
| P3.3 | Warning policy | 3 | Every captured WARNING (from `log.lammps` and the screen output) is matched against an allow-list. *(v0.4)* The `<Kind> style X in data file differs from currently defined <kind> style zero` warnings that `nocoeff` itself provokes in Tier 3a are recorded as mode artefacts, not counted (style comments are judged by P1.11). The style-comment, image-flag reset, inconsistent image flags, tilt, units-hint, non-neutral-charge and no-charge warnings → FAIL unless allow-listed. **Absence of a warning is never evidence of correctness** (FM10, FM33). | P3.1 | LAMMPS log | Defect visible only as a warning | — | SRC; PRB. Message strings verified on Update 6 (§8.9) | Allow-list OPEN |
| **P3.4** | **Process outcome classification** *(new)* | 3 | Each Tier 3 run is classified as CLEAN (exit 0, no ERROR), ERROR (non-zero exit with an ERROR line), **CRASH** (terminated by a signal, e.g. exit 139 / −11, or no ERROR line with non-zero exit), or TIMEOUT (wall-clock limit exceeded). CRASH and TIMEOUT → FAIL, attributed to the DATA FILE unless the same configuration crashes on a reference. stdout, stderr, log, exit status and signal are recorded verbatim. | — | Process result | Undiagnosed rejection | — | PRB T4a/T4a' (SIGSEGV in `read_data`); PR | Timeout value OPEN (depends on S-Q6) |
| TC.1 | Composition vs request | TC | Atom counts per element (via OD-J) equal the requested counts or ratios. | OD-D, OD-J | File, request | Wrong structure | Silent | Methodology | OPEN |
| TC.2 | Reference comparison | TC | Compare against a trusted reference: counts, type map, canonical topology multiset, charge per type, cell; geometry within τ_ref. *(v0.4)* Atoms are matched by minimum-image position (not ID), so a consistent renumbering is not a difference; Coeff sections written in the DATA FILE are compared row by row. Disagreement = finding (SPEC §7.8). | OD-I | File, reference | Disagreement to investigate | Silent | SPEC §7.8 | NOT CALIBRATED |

---

## 8.4 Triclinic box handling

- **FACT (RD).** A restricted triclinic box has origin (xlo, ylo, zlo) and edge vectors
  **A** = (xhi−xlo, 0, 0), **B** = (xy, yhi−ylo, 0), **C** = (xz, yz, zhi−zlo).
  **A** lies along +x; **B** lies in the xy plane with positive y-component; **C** has positive z-component. An orthogonal box is the special case xy = xz = yz = 0.
- **Cell matrix.** H = [**A** **B** **C**] (edge vectors as columns). Fractional coordinates s = H⁻¹(r − origin). Volume V = det H = l_x · l_y · l_z (tilt does not change the determinant).
- **Tilt (RD vs SRC — corrected in v0.3a).** RD: LAMMPS warns if a tilt factor skews the box by more than half the parallel box length (the first dimension in the tilt name, e.g. x for xz). **SRC (`domain.cpp:217-222`) and PRB (T1a/b) disagree:** the warning fires when \|xy\|/l_y > 0.5 with y periodic, or (\|xz\|+\|yz\|)/l_z > 0.5 with z periodic. P2.8 therefore cannot rely on the warning.
- **Periodicity of tilted dimensions (FACT, RD).** The domain should normally be periodic in the second dimension of each non-zero tilt factor (y for xy; z for xz and yz). "LAMMPS does not require this periodicity, but you may lose atoms if this is not the case." → Any non-zero tilt in a non-periodic dimension is reported (policy OPEN).
- **General triclinic (FACT, RD + SRC).** Arbitrary right-handed **A**, **B**, **C** (`avec`/`bvec`/`cvec`/`abc origin`) are rotated to restricted form on read. This build supports them. **Out of scope** (P0.5).
- **Boundary dependence (FACT, RD + SRC + PRB).**
  - Periodic dimension: coordinates outside the box are remapped into it. Not an error; P2.2 reports it.
  - Non-periodic dimension (`f`, `s`, `m`): atoms outside lo…hi are lost and read_data errors `Did not assign all atoms correctly` (T17, T33, T33b). Ownership is `lo ≤ c < hi`, so a coordinate exactly at hi is lost (T17b).
  - **Tilted box, non-periodic dimension (resolved in v0.3a):** containment is tested in fractional (lamda) coordinates, 0 ≤ s < 1 (`atom.cpp:1254-1261`). An atom at s_z = 1.0 with `p p f` is lost (T32).
- **Image flags (FACT, RD + SRC).** An image flag n shifts an atom by H·n. Flags are meaningful only in periodic dimensions; non-zero flags in non-periodic dimensions are reset to zero with a warning. Bonds whose atoms' flags disagree trigger `Inconsistent image flags` at run setup (T38). For infinite periodic bonded crystals, fully consistent image flags are impossible (P2.7 applicability).
- **Implementation rule (no naive x/y/z comparisons).** Distances use fractional differences: Δs ← Δs − round(Δs) in each periodic dimension, then d = |H·Δs|. For strongly tilted or small cells, search the 27 neighbouring images to guarantee the true minimum. Axis-wise wrapping with l_x, l_y, l_z is **forbidden** for triclinic cells.

---

## 8.5 Tolerance policy (mandatory)

1. Each tolerance records: what is measured · why a tolerance is needed · how it is derived · data needed · calibration status.
2. **Tier 0 and Tier 1 checks are exact.** They have no tolerances.
3. **Representation floors are derived, not chosen.** Charges written with d decimal places can shift the sum |ΣQ| by up to N × 0.5 × 10⁻ᵈ through rounding alone (N = number of atoms). τ_Q may not be set below this floor; any value above it requires justification from the FF paper or references. *(This is a derivation method, not a value.)*
4. **Physical tolerances come only from** trusted references, the cited FF/model paper, or an explicit owner requirement. Otherwise the property returns NOT_CALIBRATED.
5. **No universal limits.** No universal geometry, density, or charge limits exist. Charge neutrality is system-specific (OD-H).
6. **Traceability.** Every calibration cites the reference IDs used, the derivation version, and the date. Changing a reference invalidates every calibration derived from it.
7. **No borrowed tolerances.** Tolerances used in other works (e.g. relative-error thresholds in MDGym, bond-length thresholds in CrystaLLM) **and internal LAMMPS constants** (e.g. the kspace neutrality threshold 1e-5, `EPSILON` in atom ownership) are not adopted without derivation for this system.

| Tolerance | Measured quantity | Why needed | Derivation method | Data needed | Status |
|---|---|---|---|---|---|
| τ_Q | \|ΣQ − Q_target\| | Printed charges are rounded | ≥ rounding floor (item 3); upper bound from FF / references | FF charges, references, OD-H | NOT CALIBRATED |
| d_min(t_i,t_j) | Minimum pair distance per type pair | Distinguish overlap from close contact | Lower tail of distance distributions in references | References, OD-J | NOT CALIBRATED |
| ℓ_lo, ℓ_hi | Bond length per bond type | Detect wrong partners | Reference distributions and/or FF equilibrium values | References, OD-C2 | NOT CALIBRATED |
| ρ range | Bulk density | Detect scaling, missing atoms, units | References + model literature | References, OD-B, OD-C3 | NOT CALIBRATED |
| τ_m | Mass deviation per type | Detect wrong type map | Precision of the FF mass table | FF, OD-J | NOT CALIBRATED |
| τ_cell | Out-of-cell extent | Detect scaling/shift | References' wrapping convention | References | NOT CALIBRATED |
| τ_img | Unwrapped vs minimum-image bond vector | Floating-point noise | Numeric analysis + references | References | NOT CALIBRATED |
| τ_ref | Deviation from a reference | Writer precision | Writer and reference precision | References | NOT CALIBRATED |

---

## 8.6 Implementation implications (written before the validator phase; see §8.10 for what was built)

The validator phase will need:
- its **own parser** implementing §8.3 and §8.7 (ASE/pymatgen provide cross-check readings only, never verdicts);
- a **declared-configuration record** (SPEC §7.10): units, atom_style, boundary per dimension, LAMMPS executable and build (`-h` output, source tag, commit), FF setup, warning allow-list, Tier 3 timeout;
- a **calibration record** keyed to reference IDs, holding every τ with its derivation;
- a **probe suite** (`source_audit/probe*.py`) re-run whenever the LAMMPS build changes, with differences recorded (SPEC §7.11);
- *(new)* a **negative-control set** built from the corruption operators in FAILURE_MODES §9.4.

## 8.7 Parser grammar derived from LAMMPS source (new in v0.3a)

FACT (SRC) unless marked PR. The validator may be stricter than LAMMPS, never looser.

1. **Line reading.** At most 254 content characters per line; the rest is discarded by LAMMPS (P0.6). `\r` counts as whitespace (CRLF accepted, T25).
2. **Line 1.** Skipped, except that LAMMPS scans it for `units = <word>` (P1.15).
3. **Header lines.** LAMMPS cuts the line at the first `#`, then skips it if blank, else matches `^\s*<int>\s+atoms\s` (and analogous patterns, including `\f+` float fields for box and tilt lines). The first line that matches no header pattern ends the header and must be a section keyword. The project rule (PR) requires whitespace before `#`.
4. **Section keyword lines.** Blank lines and lines whose first non-blank character is `#` are skipped before a keyword. The keyword line is cut at `#` (the remainder is the style comment), trimmed at both ends, and matched exactly against the list. **The next line is always consumed.**
5. **Data rows (Atoms, Bonds, …, Masses).** Tokenised on whitespace. A token that *starts* with `#` begins a comment. Blank rows and rows whose first token starts with `#` are skipped **but still count towards the N lines read** (because LAMMPS reads N lines, then parses them).
6. **Coeff rows.** Cut at the first `#` anywhere. An empty row is an error (`Unexpected empty line in … section`).
7. **Atoms field count.** Fixed by the first data row (k or k+3); every later row must have the same count.
8. **Numbers.** Integers `^[+-]?\d+$`; floats as P0.3; no `nan`/`inf`/`D` exponents.
9. **End of section.** After N lines, LAMMPS looks for the next keyword. One leftover row immediately followed by EOF is silently ignored (P0.11).

Note on rule 5: a comment or blank row inside a section consumes one of the N slots (SRC: `nread += nchunk` counts lines, not parsed rows), so one real row is left unread. That row then falls to the count checks (`Did not assign all atoms correctly`, `Bonds assigned incorrectly`) or to keyword parsing. Only the Atoms case has been exercised (T9b). The validator should **FAIL comment or blank rows inside sections** (PR), because LAMMPS's outcome depends on what follows.

## 8.8 Do not rely on LAMMPS for (new in v0.3a)

The validator must implement these itself, because this LAMMPS build gives no usable signal for them:
- duplicate atom IDs when max ID ≥ natoms (P1.2);
- topology references to absent IDs below max ID (P1.5: crash, not error);
- duplicate topology entries (P1.6);
- duplicated or missing Masses / Coeff type rows under Tier 3a (P1.4, P1.7);
- negative molecule IDs (P1.8);
- style-comment mismatches of equal length (P1.11);
- velocity coverage (P1.14);
- missing box lines (P0.8), duplicate header keywords (P0.10), one surplus row at EOF (P0.11), line truncation (P0.6);
- the documented tilt bound (P2.8);
- every Tier 2 and TC property.

## 8.9 LAMMPS message strings verified on 22 Jul 2025 – Update 6 (new in v0.3a)

Messages are followed by `(src/<file>.cpp:<line>)` in this build. Match on the text only.

**Errors:** `Unknown identifier in data file: <text>` · `Did not assign all atoms correctly` · `Duplicate atom IDs exist` · `Invalid atom type N in Atoms section of data file: …` · `Invalid line in Atoms section of data file: …` · `Incorrect format in Atoms section of data file: …` · `Expected floating point parameter instead of '<x>' in input script or data file` · `Bonds assigned incorrectly` · `Invalid atom ID in Angles section of data file: …` · `Invalid data file section: Bonds` · `Invalid format in Masses section of data file: …` · `Not all per-type masses are set. Type N is missing.` · `All pair coeffs are not set. Status:` · `All bond coeffs are not set. Status:` · `Unexpected empty line in PairCoeffs section. Expected N lines.` · `Unexpected end of data file` · `Box bounds are invalid or missing` · `Must define pair_style before Pair Coeffs` · `Must use 'kspace_modify gewald' for uncharged system`.

**Warnings:** `Inconsistent units in data file: current = X, data file = Y` · `Atom style in data file X differs from currently defined atom style Y` · `Triclinic box skew is large. LAMMPS will run inefficiently.` · `Non-zero imageflag(s) in {x,y,z} direction for non-periodic boundary reset to zero` · `Inconsistent image flags` · `System is not charge neutral, net charge = Q` · `Using kspace solver on system with no charge`.

**From source, not triggered:** `Bond atoms {i} {j} missing on proc {p} at step {n}` · `Bond atoms missing at step {n}` · `Bond atom missing in image check` · `Bond atom missing in box size check`.

---

## 8.10 Implementation status — validator v1.0 (new in v0.4)

Code: `lammps-agent/validator/`. Every property returns a `CheckResult` (plan Appendix B). Unit tests: `tests/` (74 tests). Negative controls: `docs/VALIDATOR_RESULTS.md`.

| Property | Implemented in | Unit test(s) | Negative-control operators (`scripts/mutate.py`) | Status |
|---|---|---|---|---|
| P0.1–P0.12 | `tier0.py` (`p0_1_header` … `p0_12_encoding`); grammar in `parser.py` | `test_tier0.py` (one malformed file per rule) | FM07, FM10 (tilt line dropped), FM20, FM21, FM24, FM25, FM26, FM27, FM34, FM35 | Implemented. P0.12 policy OPEN (OD-M): default `ascii_lf`; `ascii_lf_or_crlf` available |
| P1.1–P1.15 | `tier1.py` | `test_tier1.py` | FM03 (hint), FM04, FM05, FM13, FM14, FM28–FM33 | Implemented. P1.7 parameter counts only where `coeff_param_counts` is declared; P1.6 improper permutations reported, not failed (OPEN); P1.8 crossing-bond policy per configuration |
| P1.16, P1.17 | `tier1.py` | `test_p1_16_*`, `test_p1_17_*` | FM01, FM04 (angles dropped), FM11, FM22 (rows relabelled) | Implemented, configuration-gated |
| P2.1 | `tier2.py` | `test_p2_1_*` | FM06, FM12 | Implemented; τ_Q = rounding floor (§8.5 rule 3). See note 1 |
| P2.2 | `tier2.py` | `test_p2_2_*` | FM08, FM10, FM19, FM23 | Implemented: `wrapped` (s ∈ [0,1) up to printed precision) and `unwrapped_clusters` (bonded-cluster centroids within τ_centroid) |
| P2.3 | `tier2.py` + `geometry.pairs_within` (linked cells in fractional space; brute force over 27 images for small/strongly tilted cells) | `test_p2_3_*`; geometry tests against brute force | FM03, FM13, FM17 | Implemented; excludes 1-2 bonded pairs (covered by P2.4) |
| P2.4–P2.8 | `tier2.py` | `test_p2_4_*` … `test_p2_8_*` | FM02, FM03, FM09, FM10, FM15, FM18, FM19 | Implemented. P2.8 FAILs on the documented bound **and** the source criterion (`tilt_policy: both`; OD-N OPEN) |
| P3.1–P3.4 | `tier3.py`, `backends.py` | `test_tier3_tc.py` (clean run, captured ERROR text, SIGSEGV classification, missing executable) | all | Implemented. `LocalBackend` tested; `SSHBackend` / `DockerBackend` written but **untested** (no cluster account, no Docker) |
| TC.1 | `tc.py` | — | — | Implemented; NOT_EVALUATED until a request format exists (OD-D) |
| TC.2 | `tc.py` | `test_tc2_*` | all (each corrupted file is compared with its parent) | Implemented |

**Note 1 (for OD-H).** The rounding floor N·0.5·10⁻ᵈ is a worst case. For REF-01 (N = 1478, d = 4) it is 0.074 e — looser than LAMMPS's own 1e-5 warning. Removing one hydrogen (q = 0.053 e) is therefore caught only by LAMMPS's warning (P3.3) and TC.2, not by P2.1 (`VALIDATOR_RESULTS.md`, FM12). The references themselves sum to exactly 0.0000 e. A statistical floor (independent rounding errors: σ_ΣQ = √N·10⁻ᵈ/√12 ≈ 0.0011 e for REF-01) would catch it; changing rule 3 is an owner decision.

## 8.11 Calibration record (new in v0.4)

Built by `scripts/calibrate.py` into `calibration/pce_emc.json` (status **PROVISIONAL**, from candidate references REF-01..REF-04) and `calibration/tobermorite_fixture.json` (status **SYNTHETIC**, from FIX-T11/T14; for code-path tests only). Each record stores the reference IDs and SHA-256, date, derivation version and a basis text per tolerance. Re-run the script whenever a reference changes (§8.5 rule 6).

| Tolerance | Derivation (calibrate.py v1) | PCE/EMC values | Basis / status |
|---|---|---|---|
| ℓ_lo, ℓ_hi | [min·0.9, max·1.1] of minimum-image bond lengths per atom-type-name pair | 15 pairs, e.g. c4o–h1 [0.897, 1.327] Å (n = 2168) | References spread σ ≈ 3 % around r0. Checked automatically: every widened window stays below the closest non-bonded contact of that element pair (tightest: C–C 1.921 < 2.038 Å) |
| d_min | 0.75 × closest non-bonded contact (all pairs except 1-2) per element pair, searched to 4 Å | 13 element pairs, e.g. H–H 0.889, C–H 1.311, O–O 1.595 Å | Targets gross overlaps only; references are unrelaxed builds |
| ρ range | [min, max] of the family × (1 ∓ 0.02) | `pce_emc_dense` [0.98, 1.02] g/cm³ (REF-01, REF-02 both 1.0000); `pce_emc_dilute` NOT_APPLICABLE | **The ±2 % is a placeholder, not reference-derived** (two identical values): §8.5 rule 4 needs an owner requirement |
| τ_m | 0.01 amu | — | FF tables vs IUPAC editions differ by ≤ 0.002 amu for H, C, O, Na, Si, Ca; any element swap differs by > 0.9 amu |
| τ_centroid (P2.2) | max(0.02, ceil₀.₀₁(3 × largest observed centroid excursion)) | 0.05 (observed 0.0137) | EMC writes whole molecules with centroids near the cell |
| τ_Q, τ_img, τ_ref | derived per file from printed precision (§8.5 rule 3) | — | exact derivations; τ_img has a 1e-12 relative floating-point floor |

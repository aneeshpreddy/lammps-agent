# FAILURE MODES — LAMMPS DATA FILE Corruption Taxonomy

Version 0.5 (2026-10-19). **Correction:** §9.6 item 2 of v0.4 was wrong — see item 2 below. New items 9–11 (PPPM crash, LAMMPS `replicate … bond/periodic` wrong images, `write_data` drops type names).

Version 0.4 (2026-10-16, validator phase). Supersedes v0.3a (2026-10-02). Changes: §9.3 now records an experimental ASE round trip; §9.4 operators are implemented (`scripts/mutate.py`); new §9.6 lists LAMMPS behaviours observed while building the negative controls. The table in §9.1 is unchanged except where §9.6 refines it.
"Silent/Loud" refers to LAMMPS `read_data` behaviour (and `run 0` where stated) under a matching configuration.

**Evidence base for v0.3a.**
- **Source:** LAMMPS tag `stable_22Jul2025_update6` (commit `9c5ab448c78a14fd534619622162ba418d6a1fb1`), read directly. Line references below are to that tag.
- **Experiments:** synthetic DATA FILEs probed against `lmp_serial`, 22 Jul 2025 – Update 6 (Homebrew, macOS arm64), serial, `newton_bond on`. Probe IDs (T1…T39) refer to `source_audit/probe*.py` and `source_audit/probe*_results.txt`.
- Full verdict trail: `source_audit/SOURCE_AUDIT.md`.
- **Behaviour and message strings are build-dependent.** Re-run the probe suite on any other build (SPEC §7.11).

**Silent/Loud vocabulary (v0.3a).**
- **Silent:** accepted, no warning.
- **Warn:** accepted with a WARNING only.
- **Loud:** ERROR, non-zero exit.
- **Loud@run:** passes `read_data` and errors only at `run`/setup, so Tier 3a does not see it.
- **Crash:** the process dies on a signal with no ERROR line.

**Totals:** 35 failure modes. 33 are IN SCOPE, 1 is OPEN (FM16) and 1 is OUT OF SCOPE (FM24). v0.2 had 26; FM27–FM35 are new in v0.3a.

---

## 9.1 Failure-mode table

| ID | Failure Mode | Description | How It Arises | LAMMPS behaviour (this build) | Earliest Detection | Property | Tier | Severity | Evidence | Reproduced? | Scope |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FM01 | Atom-type permutation | Type IDs swapped between species | Converter re-orders species | **Silent**: rows carry no element; only the type range is checked (`atom.cpp:1273`) | Tier 2 / TC | P2.6, TC.1, TC.2 | 2 | Critical | ASE writer orders types alphabetically when `specorder` is not given (ASE source, not re-checked); R13 reports a 1↔2 swap | No (needs ASE) | IN |
| FM02 | Element/type mis-identification | Wrong element inferred for a type | Atomic number guessed from masses, or Z = type index | **Silent** (LAMMPS has no element concept in `read_data`) | Tier 2 / TC | P2.6, TC.1 | 2 | High | ASE reader when `Z_of_type` is None (ASE source, not re-checked) | No (needs ASE) | IN |
| FM03 | Unit mismatch | Values written in a different units style | Converter default units (ASE default `metal`) differ from project units | **Silent** unless line 1 contains `units = X`. Then **Warn**: `Inconsistent units in data file: current = X, data file = Y` (`read_data.cpp:1287-1292`). `write_data` writes this hint (`write_data.cpp:288`) | Tier 1 (hint) / Tier 2 | P1.15, P2.3, P2.4, P2.5 | 1 / 2 | Critical | Source; T12 | **Yes** (T12, hint case) | IN |
| FM04 | Dropped bonds | Bonds missing | Writer/converter omits topology | **Silent** if the header is adjusted (only counts are compared, `read_data.cpp:1741`). **Silent** if exactly one surplus row is at EOF (FM27). Loud otherwise | Tier 1 / TC | P1.1, P0.11, P1.10, TC.2 | 1 | Critical | Source; T18f; ASE writes bonds only for `full` (ASE source) | **Yes** (T18f) | IN |
| FM05 | Duplicated bonds | Same atom pair listed twice | Writer visits (i,j) and (j,i) | **Silent**: no duplicate check in `Atom::data_bonds` (`atom.cpp:1343-1427`) | Tier 1 | P1.6 | 1 | High | Source; T4c | **Yes** (T4c) | IN |
| FM06 | Charge loss | Charges zeroed, missing, or rounded | Style without q; default charges | **Silent** at `read_data`. With a kspace style only: **Warn** `System is not charge neutral, net charge = Q` if \|Σq\| > 1e-5 (hard-coded, `kspace.cpp:32,326-331`), and **Warn** `Using kspace solver on system with no charge` if all q = 0 (ewald then errors `Must use 'kspace_modify gewald' for uncharged system`). **No check at all without kspace** | Tier 0 / 2 | P0.4, P2.1, P3.3 | 0 / 2 | Critical | Source; T15a, T15b | **Yes** (T15a/b) | IN |
| FM07 | Atom-style mismatch | Columns written for a different style | Wrong writer setting; field-count guessing | The field count is taken from the **first** row and must be k or k+3 (`atom.cpp:1111`). **Loud** if it differs. **Silent** if equal (charge vs molecular/bond, both 6), provided every value lands in a valid range: molecule IDs become types, types become charges. **Loud** (`Invalid atom type`) if a molecule ID > `atom types`. The style-comment warning is unreliable (FM33) | Tier 0 | P0.4, P1.11 | 0 | Critical | Source; T2c, T2d | **Yes** (loud variant T2c/d; silent variant per CLAUDE.md §7, not re-run) | IN |
| FM08 | Coordinate scaling/corruption | Coordinates scaled or shifted | Fractional/Cartesian confusion; unit scaling | Periodic dimensions: **Silent** remap (`atom.cpp:1250`); coincident atoms are possible, and `run 0` exits 0 with **PE = inf**. Non-periodic (`f`, `s`, `m`): **Loud** `Did not assign all atoms correctly` | Tier 2 (Tier 3b sees inf) | P2.2, P2.3, P2.5, P1.12, P3.2 | 2 | Critical | Source; T16, T16b, T17, T33, T33b | **Yes** | IN |
| FM09 | Image-flag inconsistency | Wrong or partial image flags | Wrapping without updating flags | Periodic: **Silent** at `read_data`; **Warn** at run setup `Inconsistent image flags` (`domain.cpp:1052`) when a bond's flags disagree. Non-periodic non-zero flags: **Warn** `Non-zero imageflag(s) in z direction for non-periodic boundary reset to zero`. Flags on some rows only: **Loud** `Incorrect format in Atoms section` | Tier 1 / 2 | P1.9, P2.7, P3.3 | 1 / 2 | High | Source; T13, T14, T38; ASE `write_image_flags` default False (ASE source) | **Yes** (T13, T14, T38) | IN |
| FM10 | Triclinic tilt corruption | Tilt lost, sign-flipped, or rescaled | Box treated as orthogonal | **Silent** for the tilt value. The warning `Triclinic box skew is large. LAMMPS will run inefficiently.` fires on `|xy|/ly > 0.5` (y periodic) or `(|xz|+|yz|)/lz > 0.5` (z periodic) (`domain.cpp:217-222`). **This is not the documented `|xy| ≤ lx/2` rule**, so the warning cannot stand in for P2.8 | Tier 0 / 2 | P0.5, P2.8, P2.2, P2.4 | 0 / 2 | Critical | Source; T1a (doc bound broken, no warning), T1b (doc bound met, warning); Howto_triclinic | **Yes** (T1a/b) | IN |
| FM11 | ID renumbering without topology update | Topology references stale IDs that **point to another existing atom** | Sorting/renumbering atoms only | **Silent** (no geometry check). For references to IDs that do *not* exist, see FM28 | Tier 1 / 2 | P1.5, P2.4, TC.2 | 1 / 2 | Critical | Source | No (silent by construction) | IN |
| FM12 | Missing atoms | Atoms absent, header adjusted to match | Filtering, failed insertion | **Silent**: only the count is checked (`read_data.cpp:1599`) | Tier 2 / TC | P1.1, P2.1, P2.5, TC.1 | 2 | Critical | Source | No (silent by construction) | IN |
| FM13 | Duplicate atoms | Atom written twice (same or new ID) | Merging overlapping blocks | Duplicated ID: **Loud** `Duplicate atom IDs exist` **only if** max ID < natoms (`atom.cpp:929-930`), otherwise **Silent** (IDs 1,2,3,4,6,6 accepted). Same position with a new ID: **Silent** | Tier 1 / 2 | P1.2, P2.3 | 1 / 2 | Critical | Source; T3a, T3b; AM doc | **Yes** (T3a/b) | IN |
| FM14 | Header/body count mismatch | Header count ≠ rows | Hand edits; writer bugs | Count > rows: **Loud** (`Did not assign all atoms correctly`, `Unexpected end of data file`). Count < rows: **Loud** `Unknown identifier in data file: <row>`, **except** the silent case FM27 | Tier 0 / 1 | P1.1, P0.11, P1.13, P1.14 | 1 | High | Source; T18, T18b–e | **Yes** | IN |
| FM15 | Wrong mass/type mapping | Masses assigned to wrong types | Masses taken from another type ordering | **Silent**: only mass > 0 and the type range are checked (`atom.cpp:1999-2003`) | Tier 2 | P1.4, P2.6, P2.5 | 2 | High | Source; ASE `masses` default False (ASE source) | No (silent by construction) | IN |
| FM16 | Valid but semantically wrong structure | Wrong polytype, composition, or bonding | Wrong generation logic | **Silent** | TC | TC.1, TC.2 | TC | Critical | General agent failure mode (Paimon, MDGym) | No | **OPEN** (depends on OD-D, OD-I) |
| FM17 | Atom overlap | Unphysically close atoms | Bad insertion | **Silent** at `read_data` (no distance check); Tier 3b may show PE = inf | Tier 2 | P2.3, P3.2 | 2 | High | Source; T16b; RD | **Yes** (T16b, coincident case) | IN |
| FM18 | Implausible bond lengths | Bonds between distant atoms | Wrong IDs; image handling | **Silent** at `read_data`. At run: `Bond atoms {i} {j} missing on proc … at step …` (error) / `Bond atoms missing at step N` (warning) (`ntopo_bond_all.cpp:59,81`); `Bond atom missing in image check` / `… in box size check` (warnings, `domain.cpp:1058,1149`) | Tier 2 | P2.4, P2.7 | 2 | High | Source (wording verified) | No (not triggered) | IN |
| FM19 | Implausible density | Mass/volume inconsistent | Box scaling, missing atoms, units | **Silent** | Tier 2 | P2.5 | 2 | High | Source (no check) | No (silent by construction) | IN |
| FM20 | Line truncation | Content beyond 254 characters | Very long lines | **Silent**: `MAXLINE = 256` (`read_data.cpp:49`); `fgets_trunc` keeps 254 characters (`utils.cpp:316-345`). `5.123456789` was read as `5.12` | Tier 0 | P0.6 | 0 | Medium | Source; T8 | **Yes** (T8) | IN |
| FM21 | Mis-spelled, mis-cased or mis-spaced keyword; misplaced header line | e.g. `Bond  Coeffs`, `atoms`, a header line after a section | Formatting | **Loud** `Unknown identifier in data file: <text>`. Matching is exact and case-sensitive after trimming both ends (`read_data.cpp:2543-2550`); trailing spaces are tolerated | Tier 0 | P0.1, P0.2 | 0 | Medium | Source; T10, T28, T34, T27 (trailing spaces OK) | **Yes** | IN |
| FM22 | Coeff misalignment | Coefficients attached to wrong types | Types renumbered, Coeffs not | Row count wrong: **Loud** `Unexpected empty line in PairCoeffs section. Expected N lines.` (even with `nocoeff`). **Silent** if permuted (each row carries its own type ID). For duplicated/missing type rows see FM32 | Tier 1 / TC | P1.7, TC.2 | 1 | High | Source; T19 | **Yes** (T19) | IN (full mode BLOCKED) |
| FM23 | Box origin lost | lo values reset to 0 | Converter writes box from origin | **Silent** in periodic dimensions | Tier 2 | P2.2, TC.2 | 2 | Medium | ASE writer; R13 | No (silent by construction) | IN |
| FM24 | General-triclinic mishandling | avec/bvec/cvec misread by tools | Converter gaps | This LAMMPS **supports** general triclinic (`read_data.cpp:537-545,618`). Mixing ABC vectors with lo/hi or tilt is **Loud** | Tier 0 | P0.5 (rejected by project scope) | 0 | — | Source | No | **OUT** |
| FM25 | Missing box keyword | A box line (e.g. `zlo zhi`) omitted | Writer bug; truncated header | **Silent, no warning**: defaults −0.5/0.5 (`read_data.cpp:505-506`); the presence flags are never checked. With periodic z, all atoms fold into a 1-unit slab | Tier 0 | P0.8 | 0 | Critical | Source; T5 | **Yes** (T5) | IN |
| FM26 | Data row after section keyword | First data row written directly after the keyword line | Writer omits the blank line | The row is always discarded (`read_data.cpp:2509`). Observed **Loud** for Atoms (T9, T9b), Masses (T9c) and Bonds (T29). Not guaranteed in general: the outcome depends on what follows | Tier 0 | P0.7, P1.1 | 0 | High | Source; T9, T9b, T9c, T29 | **Yes** | IN |
| **FM27** | **Surplus final row ignored** | Section has exactly one more row than its header count, is last in the file, and has no trailing blank line | Off-by-one writer; header not updated after appending | **Silent**: the extra row is taken as a section keyword, the next read hits EOF, and parsing stops (`read_data.cpp:2490-2521`). Two surplus rows, a trailing blank line or a following section make it **Loud** | Tier 0 | P0.11, P1.1 | 0 | High | Source; T18b (atom dropped), T18f (bond dropped) | **Yes** | IN |
| **FM28** | **Topology references a non-existent atom ID** | Bond/angle/… names an ID that no atom has | Deleted atoms without topology clean-up; renumbering | ID ≤ 0 or > max ID, or an atom repeated within the entry: **Loud** `Invalid atom ID in Bonds section of data file: …` (`atom.cpp:1399-1401`; angles `1497`; dihedrals `1610`; impropers `1738`). Absent ID ≤ max ID: **Crash** (SIGSEGV, exit 139 / −11, no ERROR line) in `Special::onetwo_build_newton()` (`special.cpp:217`) when the first atom exists; **Loud** `Bonds assigned incorrectly` when the first atom is the missing one | Tier 1 | P1.5, P3.4 | 1 | Critical | Source; T4a, T4a', T4b, T22; lldb backtrace | **Yes** | IN |
| **FM29** | **Velocities coverage defects** | Velocity rows for absent IDs, duplicated IDs, or atoms with no row | Writer reuses an old ID list | **Silent**: exactly natoms rows are read; an ID absent but ≤ max ID is ignored; duplicates are accepted (`atom.cpp:1327-1330`). Fewer rows than natoms (section last) is **Loud** `Unexpected end of data file` | Tier 1 | P1.14 | 1 | Medium | Source; T20a, T20b, T39 | **Yes** | IN |
| **FM30** | **Invalid molecule IDs** | Negative molecule IDs, or molecule IDs inconsistent with bonding | Signed-integer overflow; converter defaults | **Silent**: no sign check found (T21: ID −1 accepted) | Tier 1 | P1.8 | 1 | Medium | Source (no check found); T21 | **Yes** (T21) | IN |
| **FM31** | **Masses rows duplicated or missing a type** | A type appears twice in Masses; another has none | Masses copied from another type list | **Loud@run**: `read_data` enforces only the per-row format, type range and mass > 0. `check_mass` errors `Not all per-type masses are set. Type N is missing.` at run/velocity setup (`atom.cpp:782,2084-2091`). **Tier 3a misses it** | Tier 1 | P1.4 | 1 | High | Source; T11 | **Yes** (T11) | IN |
| **FM32** | **Coeff rows duplicated or missing a type** | A type appears twice in a Coeff section; another has none | As FM22 | **Silent** under `nocoeff` (Tier 3a) (T31). **Loud@run** `All pair coeffs are not set` / `All bond coeffs are not set` (T30', T31') | Tier 1 | P1.7 | 1 | High | Source; T30', T31, T31' | **Yes** | IN |
| **FM33** | **Misleading style comment** | `Atoms # <style>` or `… Coeffs # <style>` disagrees with the columns or the declared style | Header template copied from another system | The warning `Atom style in data file X differs from currently defined atom style Y` is **not issued** when the two names have equal length, or the comment is a prefix of the current style (`style_match`, `read_data.cpp:2630-2648`). `# charge` under `atomic` is **Silent** | Tier 1 | P1.11 | 1 | Medium | Source; T2a (silent), T2b (warns) | **Yes** | IN |
| **FM34** | **Duplicate header keyword** | The same header line appears twice with different values (e.g. `4 atoms`, then `3 atoms`) | Concatenated or hand-edited headers | **Silent**: the last value wins. With the remaining rows this then looks like FM27/FM14 (T35: 3 atoms read, exit 0) | Tier 0 | P0.10 | 0 | High | Source (header loop overwrites, `read_data.cpp:1343-1505`); T35 | **Yes** (T35) | IN |
| **FM35** | **Non-standard numeric format** | Fortran `D` exponents, `nan`/`inf`, `1.0` in integer fields, locale decimal commas | Fortran/locale-dependent writers | **Loud**: `Expected floating point parameter instead of '1.0D0' …`, `Invalid line in Atoms section …` (`utils.cpp:1697-1716`) | Tier 0 | P0.3 | 0 | Low | Source; T7a, T7b, T37 | **Yes** | IN |

---

## 9.2 Silent-failure analysis

Y = yes · N = no · P = partly. The "LAMMPS detects?" column now uses the vocabulary above.

| ID | Parser detects? | Internal consistency detects? | Physical validation required? | LAMMPS detects? (this build) | Trusted reference required? | Could look superficially valid? |
|---|---|---|---|---|---|---|
| FM01 | N | N | Y | Silent | Y | Y |
| FM02 | N | N | Y | Silent | Y | Y |
| FM03 | P (units hint) | P (P1.15) | Y | Silent / Warn if hint present | P | Y |
| FM04 | P (FM27 case) | P | P | Silent if header adjusted | Y | Y |
| FM05 | N | Y | N | Silent | N | Y |
| FM06 | P | N | Y | Warn at setup (kspace only) | Y | Y |
| FM07 | P | P | P | Loud or Silent (value-dependent) | N | P |
| FM08 | N | P | Y | Silent (periodic) / Loud (non-periodic) | P | Y |
| FM09 | P | Y | Y | Warn | P | Y |
| FM10 | P | N | Y | Warn on a different criterion | Y | Y |
| FM11 | N | P | Y | Silent | P | Y |
| FM12 | N | N | Y | Silent | Y | Y |
| FM13 | N | Y | Y | Partial (Loud only if max ID < natoms) | N | Y |
| FM14 | P | Y | N | Loud, except FM27 | N | P |
| FM15 | N | N | Y | Silent | Y | Y |
| FM16 | N | N | Not sufficient | Silent | Y | Y |
| FM17 | N | N | Y | Silent (read_data); PE = inf at run possible | P | Y |
| FM18 | N | N | Y | Silent (read_data) | P | Y |
| FM19 | N | N | Y | Silent | Y | Y |
| FM20 | Y | — | — | Silent | N | Y |
| FM21 | Y | — | — | Loud | N | N |
| FM22 | P | Y | N | Loud (count) / Silent (permuted) | Y | Y |
| FM23 | N | N | P | Silent | Y | Y |
| FM24 | Y (rejected by scope) | — | — | Accepted by LAMMPS | — | — |
| FM25 | Y | — | — | Silent | N | Y |
| FM26 | Y | P | — | Loud in tested cases | N | P |
| FM27 | Y | Y | N | Silent | N | Y |
| FM28 | N | Y | N | Loud or Crash | N | N |
| FM29 | N | Y | N | Silent | N | Y |
| FM30 | N | Y | N | Silent | N | Y |
| FM31 | N | Y | N | Loud@run only | N | Y |
| FM32 | N | Y | N | Silent (nocoeff) / Loud@run | N | Y |
| FM33 | N | Y | N | Silent or Warn | N | Y |
| FM34 | Y | — | — | Silent | N | Y |
| FM35 | Y | — | — | Loud | N | N |

---

## 9.3 ASE and pymatgen — documented vs configuration-dependent vs reported vs reproduced

*Unchanged from v0.2; not re-checked in the source audit (ASE not installed). Status of every statement below: as recorded on 2026-09-30.*

These libraries are **not** characterised as unreliable. The behaviours below are documented design choices, configuration-dependent effects, or third-party reports.

### Documented behaviour (ASE source `ase/io/lammpsdata.py`, per research pass 2026-09-30)
- `read_lammps_data` with `Z_of_type=None`: if a Masses section exists, atomic numbers are guessed from the masses; otherwise types 1, 2, … are assigned atomic numbers 1 (H), 2 (He), ….
- With `atom_style=None`, the style is inferred from the Atoms comment, then from the field count.
- `write_lammps_data` defaults (per research pass): `atom_style='atomic'`, `masses=False`, `write_image_flags=False`, `units='metal'`; species ordered alphabetically unless `specorder` is given; bonds written only for `full`.

### Documented behaviour (pymatgen docs, per research pass)
- LAMMPS I/O supports point-particle styles only: angle, atomic, bond, charge, full, molecular.
- `LammpsData.from_structure` builds data without force-field parameters and topologies.

### Configuration-dependent
FM01, FM02, FM03, FM09, FM15 and FM23 follow from **default arguments**. Explicit `specorder`, `Z_of_type`, `units`, `atom_style`, `masses=True` and `write_image_flags=True` may avoid them. → **Every converter call's arguments and library version must be recorded.**

### Reported — R13 (matsci.org thread "ASE read/write lammps-data") — CANDIDATE failure case, not a confirmed bug
- Input: a 10-atom, 2-type atomic file, read and rewritten with default `ase.io.read` / `ase.io.write` calls.
- Reported output: types 1↔2 swapped; Masses section absent; xlo/ylo written as 0.0; x/y coordinates changed; z unchanged.
- The type swap and missing masses are consistent with documented alphabetical ordering, mass-based guessing, and `masses=False`. **The coordinate change is not explained by the reviewed source (UNVERIFIED).**

### Reproduction plan (validator phase or later — not performed)
1. Save the exact `in.data` from the thread with a SHA-256 checksum.
2. Test the ASE release current at the post date and the current release (the post does not state a version).
3. Run the default call; then explicit `atom_style='atomic'`, `units`, `Z_of_type`, `specorder`, `masses=True`, `write_image_flags=True`, changing one argument at a time.
4. Box variants: orthogonal with non-zero lo and no image flags; then triclinic; then with image flags.
5. Expected: identical types, masses and positions, allowing for any documented origin shift. Record observed differences per property (P1.3, P1.4, P2.2, P2.6, TC.2).

### Experimentally reproduced (v0.4, ASE 3.26.0 — `docs/R13_ASE_ROUNDTRIP.md`)
The R13 thread's own file was **not** used; the group's REF-04 (40 atoms) and REF-01 (1478 atoms) were round-tripped with `ase.io.read` / `ase.io.write(format="lammps-data")`, changing one argument at a time:
- **Defaults** (and `atom_style='full'` on read only): ASE writes `atom_style atomic` rows (5 fields) — charges, molecule IDs and all topology are gone. Rejected by P0.4 (Loud in LAMMPS under `atom_style full`).
- **`atom_style='full'` on read and write**: Masses section absent (`masses=False` default) → P1.4; the **15 force-field types collapse into 4 element types** (C, H, O, Na), and **every angle, dihedral and improper is dropped** while bonds are kept (REF-01: 2724 / 3309 / 1664 lost) → P1.17, P3.2 (`Numeric index 5 is out of bounds (1-4)` when the original coefficient file is applied), TC.2.
- **+ `units='real'`, + `masses=True`, + `specorder`**: Masses restored; type collapse and topology loss remain. No combination of the tested arguments preserved the force-field typing or the higher topology.
- Coordinates and box were preserved within printing precision in every case (ASE prints 17 significant digits). The R13 report of changed coordinates was **not** reproduced on these orthogonal, lo = 0 boxes.
These are documented ASE behaviours (element-based typing; topology beyond bonds not carried), not bugs: they show why converter output must be validated (FM01, FM04, FM15).

---

## 9.4 Corruption operators for negative controls (new in v0.3a; **implemented in v0.4**: `scripts/mutate.py`, 49 operator variants, 264 files from 6 parents; results in `VALIDATOR_RESULTS.md`)

Every IN-scope mode needs at least one deterministic **corruption operator**. An operator takes a reference DATA FILE that passes Tiers 0–1 and produces a variant that must FAIL the mapped property. Variants are stored in `data/corrupted/`, named `<REF-ID>__<FM-ID>__<variant>.data`, with a sidecar `.json` recording the parent reference ID and SHA-256, the operator name and parameters, the expected failing property IDs, and the expected LAMMPS behaviour from §9.1.

| FM | Operator (sketch) | Expected failing property |
|---|---|---|
| FM01 | Swap two atom-type IDs in Atoms (Masses unchanged) | P2.6 / TC |
| FM03 | Scale coordinates and box by a unit factor; optionally write a wrong `units =` hint | P2.5, P1.15 |
| FM04 | Delete k bond rows and lower the header count | P1.10 (if applicable), TC.2 |
| FM05 | Append a reversed copy of an existing bond | P1.6 |
| FM06 | Zero all charges / round them to d decimals | P2.1 |
| FM07 | Rewrite Atoms rows in another style's column order | P0.4 |
| FM08 | Multiply coordinates by a factor; keep the box | P2.2, P2.3 |
| FM09 | Set random non-zero image flags | P1.9 / P2.7 |
| FM10 | Flip the sign of / drop the tilt line | P0.8 (if intended triclinic), P2.2 |
| FM11 | Permute atom IDs without updating topology | P2.4, TC.2 |
| FM13 | Duplicate one Atoms row (same ID) and raise natoms | P1.2 |
| FM14 / FM27 | Header count ±1 | P1.1, P0.11 |
| FM15 | Permute Masses rows' values | P2.6 |
| FM17 | Move one atom onto another | P2.3 |
| FM20 | Pad a row beyond 254 characters | P0.6 |
| FM21 | Insert a double space / change case in a keyword | P0.2 |
| FM22 / FM32 | Permute Coeff values / duplicate a Coeff type row | P1.7, TC.2 |
| FM23 | Shift box lo to 0 without shifting atoms | P2.2 |
| FM25 | Delete one box line | P0.8 |
| FM26 | Remove the blank line after a keyword | P0.7 |
| FM28 | Point one bond at a non-existent ID ≤ max ID | P1.5 |
| FM29 | Duplicate one Velocities ID | P1.14 |
| FM30 | Set one molecule ID negative | P1.8 |
| FM31 | Duplicate one Masses type row, dropping another | P1.4 |
| FM33 | Change the `Atoms #` comment to an equal-length wrong style | P1.11 |
| FM34 | Repeat a header keyword with a different value | P0.10 |
| FM35 | Rewrite one float with a `D` exponent | P0.3 |

FM02, FM12, FM16, FM18 and FM19 need reference-dependent or physics-dependent operators. They are designed after OD-B, OD-I and OD-J.

---

## 9.5 Failure-to-property mapping check

- Every IN SCOPE mode (FM01–FM15, FM17–FM23, FM25–FM35) maps to ≥ 1 property in `PROPERTIES.md` v0.3a.
- FM16 (OPEN) maps to TC.1 / TC.2, which are OPEN until OD-D and OD-I are resolved.
- FM24 (OUT) is rejected as unsupported by P0.5, although this LAMMPS build accepts it.
- Modes where **LAMMPS gives no usable signal** (Silent, unreliable Warn, or Loud@run invisible to Tier 3a): FM01–FM05, FM10–FM12, FM15, FM17, FM19, FM20, FM23, FM25, FM27, FM29–FM34 (21 of 33 in-scope modes; FM16, which is OPEN, is also silent). These are the validator's core value; their properties must not depend on Tier 3.

---

## 9.6 LAMMPS behaviours observed in the validator phase (new in v0.4)

Build: `lmp_serial` 22 Jul 2025 – Update 6 (Homebrew, macOS arm64), serial. All from `scripts/run_matrix.py` (per-file outcomes in `docs/validator_matrix.csv`) or `tests/test_tier3_tc.py`.

1. **FM28 reproduced through the validator pipeline.** A bond whose *second* atom is an absent ID < max ID → SIGSEGV (exit 139, no ERROR line) at `read_data`; classified CRASH by P3.4 (unit test). When the absent atom also appears *first* in some entry (as in all six matrix parents), LAMMPS errors instead: `Bonds assigned incorrectly` / `Angles assigned incorrectly`. Both are caught by P1.5.
2. ~~New crash path: bonds stretched beyond the communication cutoff crash `run 0`.~~ **Withdrawn in v0.5 (misattributed).** The same two files run to completion when only the kspace solver is changed from PPPM to Ewald; the SIGSEGV is the PPPM defect of item 9, not a consequence of the stretched bonds. The corruptions themselves are still caught by P2.4/P2.5.
3. **T16b reproduced.** An atom duplicated under a new ID at the same position (FM13) passes `read_data` and `run 0` exits 0 with non-finite energy (all 6 parents); P3.2 FAILs on the non-finite thermo values, P2.3 FAILs first.
4. **EMC coefficient files re-set the masses.** The EMC `.params` include contains `mass` commands for every type, so in the EMC Tier 3b configuration the DATA FILE Masses are overridden at run time: a duplicated or wrong Masses row (FM31, FM15, FM02) is silent even at `run 0`. Only P1.4 / P2.6 see it. Relevant to S-Q1.
5. **msi2lmp leaves the tilt unreduced.** INTERFACE-FF tobermorite (γ = 123.25°) converted by msi2lmp v3.9.11 has |xy| = 4.05 > lx/2 = 3.37: the documented bound is broken and LAMMPS warns `Triclinic box skew is large` (FIX-T11-raw, FIX-T14-raw — natural FM10/P2.8 cases). The same lattice with xy + lx passes.
6. **Molecule IDs in mineral models do not follow bonds.** In the msi2lmp tobermorite 11 Å file, 8 bonds join atoms with different molecule IDs (Materials Studio residues); in the EMC files none do. The P1.8 crossing-bond policy must be decided per system class (OD-B).
7. **Charge-tolerance floor vs LAMMPS.** For large systems the P2.1 rounding floor (0.074 e for 1478 atoms at 4 decimals) is looser than LAMMPS's hard-coded 1e-5 kspace warning, so removing one 0.053 e hydrogen (FM12) is caught only by P3.3/TC.2 (PROPERTIES §8.10 note 1).
8. **Silent in LAMMPS, caught by the validator.** v0.4: of 264 corrupted files, LAMMPS alone was Silent/Warn on 151 and Tiers 0–2 caught 144 of them. v0.5 (448 files, 10 parents incl. tobermorite): Silent/Warn on 259, Tiers 0–2 catch 250; the other 9 are caught by TC.2 only (`VALIDATOR_RESULTS.md`).
9. **PPPM segfaults on valid boxes (v0.5; observed, not root-caused).** With `kspace_style pppm` (accuracy 1e-4 or 1e-5, any order tried) this build dies with SIGSEGV and no message at the first force evaluation for many valid tobermorite cells — every 1×1×2 cell, including the orthogonal rectangular cell, tob11 3×3×1, tob14 2×2×2 … — while 2×2×1 works. `kspace_style ewald 1.0e-4` runs every case, with energies consistent to 0.01 %. Which boxes crash looks grid-size dependent (an FFT issue is plausible). Consequences: the tobermorite Tier 3b configuration uses Ewald; any configuration with PPPM declares an Ewald `crash_fallback_kspace`, and P3.4 attributes the crash to the build when the fallback is clean. Candidate LAMMPS/Homebrew bug report; re-test on the group or cluster build (OD-F).
10. **LAMMPS `replicate … bond/periodic` joins the wrong periodic image (v0.5; observed, not root-caused).** On the tilt-reduced tobermorite cells (xy > 0, atoms wrapped), replicating along *a* gives Si–O "bonds" of 5.87 Å to a far image while the true partner (1.64 Å) is left unbonded: 6 of the 10 eval supercells (t04, t05, t07, t11, t13, t14), with or without image flags in the input. Replication along *b* or *c*, orthogonal cells and the raw (not tilt-reduced) msi2lmp cell are correct. The command exits 0 with no warning. The documentation lists no restriction for triclinic boxes. **Caught by P2.3 + P2.4 in every case**; an independent replicator (`scripts/supercell.py`) produces the correct cells, and where LAMMPS is right the two agree exactly (TC.2). These outputs are the matrix's "real tool" natural negatives. Candidate LAMMPS bug report.
11. **`write_data` drops type names.** Masses and Coeff rows lose their `# name` comments, so a LAMMPS-written file cannot be checked for element/type identity (P1.16(b), P2.3, P2.4, P2.6 return NOT_EVALUATED or NOT_CALIBRATED) unless names are restored or declared (`type_names` in the configuration). The reference pipeline copies the comments back by type ID and verifies that data tokens are unchanged.
12. **msi2lmp writes `nan` silently (v0.6).** For the hydroxylated C3A surfaces in CVFF-INTERFACE, the zero-constant wildcard torsions `* ac1 oc3/oc4 *` come out as `nan` force constants with no "Unable to find" message. The builders now scan every msi2lmp output for non-finite values and refuse; the validator's P0.3 would also reject such a file. CVFF-INTERFACE is therefore reported as unavailable for hydrated C3A.
13. **msi2lmp takes the molecule ID from the `.car` residue-number column (v0.6).** A `.car` that numbers residues per monomer gives every monomer its own molecule ID, so bonds cross molecule IDs (P1.8 caught this in the first PCE build). The PCE builder writes the molecule index in that column.
14. **LAMMPS's skew warning fires on every reduced hexagonal cell (v0.6).** For γ = 120° (ettringite, monosulfate), |xy|/ly = 1/√3 > 0.5 even at the documented bound |xy| = lx/2. The mineral configurations use the documented bound (`tilt_policy: doc`) and allow-list this efficiency warning.
15. **Database defect (v0.6).** `CEMENT_MINERALS/c3s_unit_cell` has .car and .mdf atom lists that differ (ND vs CA2); msi2lmp stops. `c3s_unit_cell_minimized` is the usable C3S cell.
16. **Validator on the system class of 2026-10-20 (v0.6).** Corruption matrix rerun with 20 parents, adding builder PCEs in class I and class II plus C3S, C3A, ettringite and monosulfate: 870 corrupted files, **0 missed**; 848 caught by Tiers 0–2, 22 only by TC.2 (14 × FM22 coefficient values swapped with comments intact; 7 × FM19/FM23 box size or origin of vacuum boxes, task parameters; 1 × FM06 on monosulfate). All 168 class I corruptions rejected. Corruption operators that change nothing in a given parent (e.g. rounding C3S charges that are already one-decimal) are skipped and listed in the manifest, not counted.
17. **Vacuum relaxation stretches polyanion backbones (v0.7; builder defect found by the new P2.9 measurement).** The PCE builder's relaxation in vacuum with full charges stretched backbone C–C bonds to a mean of 1.60–1.69 Å (r0 1.53 Å, up to +11 %); unscreened carboxylate repulsion was the cause (a Coulomb-free minimisation gives the same result as dielectric 80). Fixed: the soft stage excludes 1-4 pairs, the force-field stage uses a relative dielectric of 80 for geometry only. The remaining +2–4 % on crowded quaternary methacrylate carbons is the PCFF/CVFF minimum itself.
18. **Supervisor replies of 2026-10-26 (v0.8): tight PCE boxes and PCE on mineral surfaces.** Builder PCE files now sit in a box 2 Å larger than the atoms on every face (new P2.10). Composite parents CP-01 (PCE oligomer on C3S (040), class I and II) were added. Matrix: 948 corrupted files from 22 parents, **0 missed**, 942 caught by Tiers 0–2, 6 only by TC.2 (3 × FM19/FM23 on the EMC vacuum boxes REF-03/04, which declare no box margin; 2 × FM22 near-equal r0 on PB-02; 1 × FM06 on monosulfate); 36/36 positive controls pass. P2.10 FAILs 24 corrupted files (box scaled, shifted, units or image-flag corruptions on tight-box parents): FM19/FM23 on builder PCEs are no longer TC-only. The first run found a gap: a Na⁺ counter-ion moved 0.3 Å from a slab Ca was only NOT_CALIBRATED, because no reference holds a Ca–Na contact; the composite calibration now gives such cross pairs a fallback floor (PROPERTIES §8.14).
19. **Tangled random-coil conformations (2026-10-27; builder defect found by the harness's spec corrupter and caught by P2.9).** A TPEG chain grown with 31 EO units relaxed into a tangle: all 18 quaternary-carbon backbone bonds (c–c2) sat at 1.57–1.81 Å for r0 1.53 Å (type mean +8.6 %). Forcing the minimiser to force convergence (FIRE + CG, etol 0) lowered the energy but left the stretch: it is a trapped conformation, not an unconverged minimisation. Fix: `builders/pce.py` checks every relaxed structure (each bond type's mean within 5 % of its r0, no bond beyond 1.10 r0; all earlier builds lie at ≤ 4.2 % and ≤ 1.065) and regrows the conformations with a new deterministic seed, keeping the sequence, up to 5 times, else refuses. The TPEG-31 case passes on the third conformation; every existing reference rebuilds byte-identically (all passed on the first).

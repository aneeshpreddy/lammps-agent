# Reference Inventory and Provenance

Version 0.4 (2026-10-16). Change from v0.3a: four **candidate** references registered (REF-01..REF-04) and two synthetic fixtures (FIX-T11, FIX-T14); the template (§A, §B) and rules (§D) are unchanged.

## STATUS: CANDIDATES REGISTERED — TRUST NOT YET ESTABLISHED

The files below were found in `UGRP/PCEs/` and copied here read-only (`chmod 444`), with SHA-256 checksums in their sidecars (`REF-0x.json`). Everything stated is read from the files themselves. **Creator, responsible person and production-use evidence are not recorded anywhere in the folder**, so none of them qualifies as an oracle under SPEC §7.8 yet. They are used as positive controls, calibration sources (status PROVISIONAL) and parents for the negative controls.

**Owner action needed (OD-I):** for each REF, confirm who built it, whether it ran in production (log, thesis, paper, or supervisor attestation), and whether the PCE system is in the project's system class (OD-B).

---

## A. What must be collected for each reference

1. The production **LAMMPS DATA FILE**, stored read-only, with its SHA-256 checksum.
2. The **working LAMMPS INPUT SCRIPT** used with it, plus any included settings files and potential/coefficient files.
3. **LAMMPS version and build**: output of `<lammps executable> -h`, plus the version string, the source tag or release archive, and the commit if known. On a Homebrew install the executables are **`lmp_serial` / `lmp_mpi`**; on clusters usually `lmp` or `lmp_<machine>`. Record the run mode (serial/MPI, process count) used in production.
4. **Force-field source**: original citation(s), the exact parameter file used, and any modifications with their justification.
5. **Construction record**: tool and version (e.g. brick-model/pyCSH generator, in-house script), generation script or settings, any manual edits.
6. **Creator** and **current responsible person**.
7. **Production-use evidence**: simulation logs, a publication or thesis that used it, or supervisor attestation.
8. **Element ↔ atom-type map** and the **molecule-ID convention**.
9. **Boundary conditions** per dimension and **units** style.
10. **Known caveats**: image-flag convention, charge adjustments, wrapping convention, line endings / encoding, anything unusual.

---

## B. Per-reference records

Common to REF-01..REF-04: built by **EMC** (Enhanced Monte Carlo, P.J. in 't Veld; `emc.pl` setup scripts) from SMILES-like monomer definitions of a polycarboxylate-ether (PCE) superplasticiser: methacrylic-acid units `*C(C(=O)O)C*`, PEG side-chain units `*C(CCO(CCO)4)C*` / `*C(C(=O)O(CCO)n)C*`, deprotonated carboxylate `*C(C(:O):O)C*`, end group `*C`, plus counter-ions. Force field: EMC `cff/basf` (PCFF-type class 2; `lj/class2/coul/long`, class2 bonded styles, `special_bonds lj/coul 0 0 1`, `pppm/cg` when `flag_charged` = 1). `units real`, `atom_style full`, no `boundary` command (→ `p p p`). Masses carry PCFF type names as comments; coordinates are whole (unwrapped) molecules with **no image flags** (`build.out`: `unwrap -> true`); molecule ID = bonded cluster; no Coeff sections in the DATA FILE (coefficients and `mass` commands are in the `.params` include). Charges at 4 decimals summing to exactly 0.0000 e. Validated under `configs/emc_pcff_real_full.yaml` v0.1: **Tiers 0–3 PASS** (Tier 3 on `lmp_serial` 22 Jul 2025 – Update 6, serial).

| Field | REF-01 | REF-02 | REF-03 | REF-04 |
|---|---|---|---|---|
| Source path | `UGRP/PCEs/c12e12p15/pce_mono.*` | `UGRP/PCEs/c6e18p15/pce_mono.*` | `UGRP/PCEs/c18e6p15/pce_mono.*` | `UGRP/PCEs/c18e6p15/pce_1.*` |
| SHA-256 (DATA FILE, first 16) | `61112aef3b5bcdf5` | `c676d14287eef2fc` | `eb94b804964cdd57` | `d6402a0d49b1b1ef` |
| Atoms / bonds / angles / dihedrals / impropers | 1478 / 1471 / 2724 / 3309 / 1664 | 2111 / 2108 / 3900 / 4671 / 2384 | 845 / 836 / 1548 / 1947 / 944 | 40 / 38 / 69 / 89 / 42 |
| Content | one PCE chain (1472 atoms) + 6 Ca²⁺ | one PCE chain (2108 atoms) + 3 Ca²⁺ | one PCE chain (836 atoms) + 9 Ca²⁺ | short PCE oligomer (39 atoms) + 1 Na⁺ |
| Box | cubic 25.442 Å | cubic 28.382 Å | 46 × 60 × 29 Å | cubic 20 Å |
| Density / family | 1.0000 g/cm³ — `pce_emc_dense` | 1.0000 g/cm³ — `pce_emc_dense` | 0.126 g/cm³ — `pce_emc_dilute` | 0.059 g/cm³ — `pce_emc_dilute` |
| EMC build / emc.pl | v9.4.4 (19 Nov 2025) / v5.2.2 | v9.4.4 (19 Nov 2025) / v5.2.2 | v9.4.4 (19 Nov 2025) / v5.2.2 | v9.4.4 (25 Sep 2025) / v5.2.1 |
| Generated | 2025-11-23 | 2025-11-23 | 2025-11-21 | 2025-10-16 |
| Paired INPUT SCRIPT / coefficient file | `REF-01.in` / `REF-01.params` | `REF-02.in` / `REF-02.params` | `REF-03.in` / `REF-03.params` | `REF-04.in` / `REF-04.params` |
| Creator / responsible person | NOT YET AVAILABLE | NOT YET AVAILABLE | NOT YET AVAILABLE | NOT YET AVAILABLE |
| LAMMPS build used in production | NOT YET AVAILABLE (EMC paths point to `/gpfs/projects/emc/…`, a cluster) | same | same | same |
| Production-use evidence | NOT YET AVAILABLE | NOT YET AVAILABLE | NOT YET AVAILABLE | NOT YET AVAILABLE |
| Allow-list entries needed | none (template warning "No fixes with time integration" only) | none | none | none |
| Known caveats | Masses also re-set by `.params` `mass` commands (DATA FILE values overridden at run time); unwrapped coordinates extend to −0.43…1.31 in fractional units | same | box differs from EMC `lphase` (dilute) | different EMC version; Na⁺ counter-ion |
| Qualifies as oracle? | **No — candidate** (no creator / production evidence) | No — candidate | No — candidate | No — candidate |

### Synthetic fixtures (`data/fixtures/`) — not references

| ID | Source | Construction | Use |
|---|---|---|---|
| FIX-T11-raw / FIX-T14-raw | `UGRP/CEMENT_MINERALS/tob11_unit_cell`, `tob14_avg_cell` (.car/.mdf, INTERFACE FF 1.5 model database) | `msi2lmp` v3.9.11 (LAMMPS tools, compiled from the Homebrew share directory) `-class II -frc pcff_interface_v1_5.frc -ignore` (the .frc lacks some class 2 cross terms for tobermorite; `-ignore` zeros them) | natural negatives: tilt not reduced (P2.8) |
| FIX-T11 / FIX-T14 | the raw fixtures | `scripts/make_fixtures.py`: tilt reduced by a lattice change of basis (B′ = B + A), atoms wrapped, image flags updated so r + H·n is unchanged | triclinic positive controls (configuration `configs/interface_pcff_fixture.yaml`, status SYNTHETIC) |

---

## C. Inventory

| Reference ID | Filename | System | Status |
|---|---|---|---|
| REF-01 | `REF-01.data` | PCE (EMC, PCFF-type) + Ca²⁺, dense | CANDIDATE — provenance incomplete |
| REF-02 | `REF-02.data` | PCE (EMC, PCFF-type) + Ca²⁺, dense | CANDIDATE — provenance incomplete |
| REF-03 | `REF-03.data` | PCE (EMC, PCFF-type) + Ca²⁺, dilute | CANDIDATE — provenance incomplete |
| REF-04 | `REF-04.data` | PCE oligomer (EMC) + Na⁺, dilute | CANDIDATE — provenance incomplete |
| C-S-H reference(s) | — | — | **REFERENCE COLLECTION REQUIRED** (OD-B) |

---

## D. Rules

- References are **read-only**. Derived or deliberately corrupted variants are stored separately in `data/corrupted/`, named `<REF-ID>__<FM-ID>__<variant>.data` with a sidecar `.json` recording the parent reference ID and SHA-256 (FAILURE_MODES §9.4).
- **Similarity to a reference is not proof of correctness.** Disagreements are findings to investigate.
- Every Tier 2 calibration cites the reference IDs used. Replacing or editing a reference invalidates its dependent calibrations.
- A reference must itself pass Tiers 0–1 and Tier 3a under its declared configuration before it is used for calibration. If it fails, investigate whether the reference or the property is wrong before proceeding.
- Because production files can predate the v0.3a properties (e.g. P0.10 duplicate header keywords, P0.11 surplus rows, P0.12 encoding, P1.14 velocity coverage), any failure on such a property is recorded as either a **latent defect** or an **allow-list entry with justification**. A property is never silently relaxed.
- Run Tier 3 checks on references with the same build and run mode that will be used for generated files (SPEC §7.10–7.11).

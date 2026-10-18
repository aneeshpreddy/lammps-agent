# Eval set — task instances (plan Days 17–19)

14 tasks inside the declared system family (bulk tobermorite 11 Å / 14 Å, PCFF-INTERFACE; SPEC §7.3). Each `eval/tasks/tNN.json` holds the natural-language **input** given to the system, a hidden structured **spec** used for checking, the failure modes it **exercises**, and the **reference** output built by `scripts/build_references.py` (not by the agent). All 14 references PASS Tiers 0–3; their evidence is in `REFERENCE_EVIDENCE.md`.

Difficulty: {'easy': 3, 'representative': 8, 'hard': 3} (plan: 2–3 easy, 7–9 representative, 2–3 hard).

**Known trap (FAILURE_MODES §9.6 item 10).** LAMMPS `replicate … bond/periodic` silently builds wrong bonds for t04, t05, t07, t11, t13 and t14 (triclinic, replicated along *a*). A system that delegates replication to that command will fail those tasks — the validator catches it (P2.3, P2.4).

**Not yet done (plan Days 20–21, 22–23 Oct):** dev/test split with a frozen hash, `METRICS.md`, and the harness. Do not tune anything on the test tasks once the split is frozen.

| Task | Difficulty | Model | Supercell | Box | Atoms | Bonds / angles / dihedrals / impropers | Exercises | Note |
|---|---|---|---|---|---|---|---|---|
| t01 | easy | tob11_unit_cell | 1×1×1 | triclinic | 88 | 72 / 100 / 96 / 48 | FM01, FM02, FM06, FM10, FM15, FM22 | unit cell, triclinic |
| t02 | easy | tob14_avg_cell | 1×1×1 | triclinic | 104 | 80 / 102 / 84 / 48 | FM01, FM02, FM06, FM10, FM15, FM22 | unit cell, triclinic, 10 atom types |
| t03 | easy | tob11_rectangular_cell | 1×1×1 | orthogonal | 176 | 144 / 200 / 192 / 96 | FM01, FM02, FM06, FM15, FM22 | orthogonal cell |
| t04 | representative | tob11_unit_cell | 2×1×1 | triclinic | 176 | 144 / 200 / 192 / 96 | FM01, FM02, FM06, FM10, FM15, FM18, FM22 | supercell along a |
| t05 | representative | tob11_unit_cell | 2×2×1 | triclinic | 352 | 288 / 400 / 384 / 192 | FM01, FM02, FM06, FM10, FM15, FM18, FM22 | supercell in the layer plane |
| t06 | representative | tob11_unit_cell | 1×1×2 | triclinic | 176 | 144 / 200 / 192 / 96 | FM01, FM02, FM06, FM10, FM15, FM18, FM22 | supercell across layers |
| t07 | representative | tob14_avg_cell | 2×2×1 | triclinic | 416 | 320 / 408 / 336 / 192 | FM01, FM02, FM06, FM10, FM15, FM18, FM22 | 14 Å supercell in the layer plane |
| t08 | representative | tob14_avg_cell | 1×1×2 | triclinic | 208 | 160 / 204 / 168 / 96 | FM01, FM02, FM06, FM10, FM15, FM18, FM22 | 14 Å supercell across layers |
| t09 | representative | tob11_rectangular_cell | 2×1×1 | orthogonal | 352 | 288 / 400 / 384 / 192 | FM01, FM02, FM06, FM15, FM18, FM22 | orthogonal supercell |
| t10 | representative | tob14_avg_rectangular_cell | 1×1×1 | orthogonal | 208 | 160 / 204 / 168 / 96 | FM01, FM02, FM06, FM15, FM22 | orthogonal 14 Å cell |
| t11 | representative | tob14_avg_cell | 2×1×1 | triclinic | 208 | 160 / 204 / 168 / 96 | FM01, FM02, FM06, FM10, FM15, FM18, FM22 | 14 Å supercell along a |
| t12 | hard | tob11_unit_cell | 1×2×1 | triclinic | 176 | 144 / 200 / 192 / 96 | FM01, FM02, FM06, FM10, FM15, FM18, FM22 | replication along b pushes xy beyond lx/2: tilt must be reduced |
| t13 | hard | tob14_avg_cell | 3×3×1 | triclinic | 936 | 720 / 918 / 756 / 432 | FM01, FM02, FM06, FM10, FM14, FM15, FM18, FM22 | large triclinic supercell (936 atoms) |
| t14 | hard | tob11_unit_cell | 3×3×2 | triclinic | 1584 | 1296 / 1800 / 1728 / 864 | FM01, FM02, FM06, FM10, FM14, FM15, FM18, FM22 | large triclinic supercell (1584 atoms) |

Example input (t05):

> Build a LAMMPS data file for a 2x2x1 supercell of the tobermorite 11 Å unit cell from the INTERFACE FF 1.5 model database (tob11_unit_cell) with the PCFF-INTERFACE force field (pcff_interface_v1_5.frc): atom_style full, real units, periodic in x, y and z, all force-field coefficients and masses written in the data file, triclinic tilt within LAMMPS's documented bound.

**Success (draft, to be fixed in `METRICS.md` on 22 Oct):** the generated file passes Tiers 0–3 under `configs/interface_pcff_tobermorite.yaml` **and** TC.2 finds it equivalent to the reference (same atoms by position, types, charges, full topology, coefficients and cell).

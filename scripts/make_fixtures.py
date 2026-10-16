"""Build the triclinic tobermorite fixtures from the raw msi2lmp output.

FIX-T11-raw / FIX-T14-raw: msi2lmp v3.9.11 (LAMMPS tools, compiled from the Homebrew share
directory) applied to the INTERFACE FF 1.5 models UGRP/CEMENT_MINERALS/tob11_unit_cell and
tob14_avg_cell with pcff_interface_v1_5.frc, `-class II -ignore` (the .frc lacks some class-2
cross terms for tobermorite; -ignore sets them to zero). These are SYNTHETIC FIXTURES for
exercising triclinic code paths — not oracle references (SPEC §7.8).

FIX-T11 / FIX-T14 (this script): the same lattice with the tilt reduced into the documented bound
(|xy| <= lx/2, |xz| <= lx/2, |yz| <= ly/2) by a change of basis B' = B - kA, C' = C - mB' - nA,
then every atom wrapped into the cell with its image flags updated so that the unwrapped position
r + H.n is unchanged. Cartesian coordinates of the lattice sites are not altered.

Usage: python scripts/make_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from dataedit import DataText, split_comment  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "data", "fixtures")


def reduce_and_wrap(src: str, dst: str) -> dict:
    d = DataText.read(src)
    xlo, xhi = map(float, d.header_values("xlo xhi"))
    ylo, yhi = map(float, d.header_values("ylo yhi"))
    zlo, zhi = map(float, d.header_values("zlo zhi"))
    xy, xz, yz = map(float, d.header_values("xy xz yz"))
    lx, ly, lz = xhi - xlo, yhi - ylo, zhi - zlo
    # change of basis; record the integer shifts for the image-flag update
    m = round(yz / ly)
    yz2, xz2 = yz - m * ly, xz - m * xy
    k = round(xy / lx)
    xy2 = xy - k * lx
    xz2 = xz2  # xz is reduced after yz (C' = C - mB)
    n = round(xz2 / lx)
    xz3 = xz2 - n * lx
    H = np.array([[lx, xy2, xz3], [0, ly, yz2], [0, 0, lz]])
    Hinv = np.linalg.inv(H)
    origin = np.array([xlo, ylo, zlo])
    rows = d.section_rows("Atoms")
    moved = 0
    for i, line in rows:
        toks, com = split_comment(line)
        x = np.array([float(t) for t in toks[4:7]])
        img = np.array([int(t) for t in toks[7:10]]) if len(toks) >= 10 else np.zeros(3, int)
        # old basis A, B, C -> new basis: B = B' + kA ; C = C'' + mB' + (n + m k) A  (see docstring)
        ia, ib, ic = img
        ia2 = ia + k * ib + (n + m * k) * ic
        ib2 = ib + m * ic
        img2 = np.array([ia2, ib2, ic])
        s = Hinv @ (x - origin)
        shift = np.floor(s).astype(int)
        if shift.any():
            moved += 1
        x2 = x - H @ shift
        img2 = img2 + shift
        toks[4:7] = [f"{v:.9f}" for v in x2]
        toks = toks[:7] + [str(int(v)) for v in img2]
        d.lines[i] = "  ".join(f"{t:>6}" for t in toks[:3]) + f"  {toks[3]}  " + "  ".join(f"{t:>15}" for t in toks[4:7]) \
            + "  " + " ".join(f"{t:>3}" for t in toks[7:]) + (f" {com}" if com else "")
    hi = d.header_index("xy xz yz")
    d.lines[hi] = f"  {xy2:15.9f} {xz3:15.9f} {yz2:15.9f} xy xz yz"
    d.lines[0] = d.lines[0] + " | tilt reduced + wrapped by scripts/make_fixtures.py"
    d.write(dst)
    return {"tilt_before": [xy, xz, yz], "tilt_after": [xy2, xz3, yz2], "basis_shift": {"k": k, "m": m, "n": n},
            "atoms_rewrapped": moved}


def main():
    elements = {"sc2": "Si", "sc3": "Si", "oc12": "O", "oc13": "O", "oc14": "O", "oc22": "O", "o*": "O",
                "ca+t": "Ca", "h*": "H", "hoy": "H"}
    for tag, model in (("T11", "tob11_unit_cell"), ("T14", "tob14_avg_cell")):
        raw = os.path.join(FIX, f"FIX-{tag}-raw.data")
        out = os.path.join(FIX, f"FIX-{tag}.data")
        info = reduce_and_wrap(raw, out)
        for fid, path, extra in ((f"FIX-{tag}-raw", raw, {"note": "msi2lmp output as written: tilt not reduced"}),
                                 (f"FIX-{tag}", out, dict(info, parent="FIX-%s-raw" % tag))):
            sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
            meta = {"id": fid, "role": "SYNTHETIC_FIXTURE", "file": os.path.relpath(path, ROOT), "sha256": sha,
                    "source": f"UGRP/CEMENT_MINERALS/{model}.car/.mdf + INTERFACE_FF_1_5 pcff_interface_v1_5.frc "
                              f"via msi2lmp v3.9.11 -class II -ignore",
                    "declared_config": "configs/interface_pcff_fixture.yaml",
                    "overrides": {"density_family": "tobermorite_interface"},
                    "trust_status": "SYNTHETIC - for code-path tests only, not an oracle"}
            meta.update(extra)
            with open(os.path.join(FIX, f"{fid}.json"), "w") as fh:
                json.dump(meta, fh, indent=2)
        print(tag, info)
    print("element map used:", elements)


if __name__ == "__main__":
    main()

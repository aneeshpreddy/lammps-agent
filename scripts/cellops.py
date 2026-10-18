"""Lattice operations on DATA FILE text, shared by the fixture and reference builders.

reduce_and_wrap: bring a restricted-triclinic tilt into the documented bound (|xy| <= lx/2,
|xz| <= lx/2, |yz| <= ly/2) by a change of lattice basis, B' = B - kA, C' = C - mB (- nA), then wrap
every atom into the new cell and update its image flags so that the unwrapped position r + H.n is
unchanged. Cartesian coordinates of the lattice sites are not altered; only the choice of cell is.
"""
from __future__ import annotations

import numpy as np

from dataedit import DataText, split_comment


def _fmt(v: float) -> str:
    return f"{v:.9f}"


def reduce_and_wrap(d: DataText, note: str = "tilt reduced + wrapped by scripts/cellops.py") -> dict:
    xlo, xhi = map(float, d.header_values("xlo xhi"))
    ylo, yhi = map(float, d.header_values("ylo yhi"))
    zlo, zhi = map(float, d.header_values("zlo zhi"))
    try:
        xy, xz, yz = map(float, d.header_values("xy xz yz"))
        has_tilt = True
    except KeyError:
        xy = xz = yz = 0.0
        has_tilt = False
    lx, ly, lz = xhi - xlo, yhi - ylo, zhi - zlo
    m = round(yz / ly)
    yz2, xz2 = yz - m * ly, xz - m * xy
    k = round(xy / lx)
    xy2 = xy - k * lx
    n = round(xz2 / lx)
    xz3 = xz2 - n * lx
    H = np.array([[lx, xy2, xz3], [0, ly, yz2], [0, 0, lz]])
    Hinv = np.linalg.inv(H)
    origin = np.array([xlo, ylo, zlo])
    moved = 0
    for i, line in d.section_rows("Atoms"):
        toks, com = split_comment(line)
        x = np.array([float(t) for t in toks[4:7]])
        img = np.array([int(t) for t in toks[7:10]]) if len(toks) >= 10 else np.zeros(3, int)
        ia, ib, ic = img
        # old basis A, B, C -> new basis: B = B' + kA ; C = C'' + mB' + (n + m k) A
        img2 = np.array([ia + k * ib + (n + m * k) * ic, ib + m * ic, ic])
        shift = np.floor(Hinv @ (x - origin)).astype(int)
        if shift.any():
            moved += 1
        x2 = x - H @ shift
        img2 = img2 + shift
        toks = toks[:4] + [_fmt(v) for v in x2] + [str(int(v)) for v in img2]
        d.lines[i] = " ".join(toks) + (f" {com}" if com else "")
    if has_tilt:
        d.lines[d.header_index("xy xz yz")] = f"{_fmt(xy2)} {_fmt(xz3)} {_fmt(yz2)} xy xz yz"
    if note:
        d.lines[0] = d.lines[0] + f" | {note}"
    return {"tilt_before": [xy, xz, yz], "tilt_after": [xy2, xz3, yz2],
            "basis_shift": {"k": int(k), "m": int(m), "n": int(n)}, "atoms_rewrapped": moved}


def tilt_within_bound(d: DataText) -> bool:
    xlo, xhi = map(float, d.header_values("xlo xhi"))
    ylo, yhi = map(float, d.header_values("ylo yhi"))
    try:
        xy, xz, yz = map(float, d.header_values("xy xz yz"))
    except KeyError:
        return True
    lx, ly = xhi - xlo, yhi - ylo
    return abs(xy) <= lx / 2 + 1e-12 and abs(xz) <= lx / 2 + 1e-12 and abs(yz) <= ly / 2 + 1e-12

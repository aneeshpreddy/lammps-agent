"""Deterministic supercell builder for periodic bonded crystals (reference pipeline, step 4).

Independent cross-check of LAMMPS `replicate ... bond/periodic`, which builds the references (written
separately so the two implementations do not share bugs). Copy (a, b, c) of atom i sits at r_i + H.(a, b, c); every topology entry is placed by
walking its bonds (consecutive atoms for bonds/angles/dihedrals, centre -> others for impropers) and
choosing, for each step, the integer image that gives the shortest vector (27-image search, so it is
safe for tilted cells). scripts/build_references.py crosscheck requires TC.2 equivalence.
"""
from __future__ import annotations

import itertools

import numpy as np

from dataedit import DataText, split_comment

TOPO = {"Bonds": 2, "Angles": 3, "Dihedrals": 4, "Impropers": 4}
COUNT_KEY = {"Bonds": "bonds", "Angles": "angles", "Dihedrals": "dihedrals", "Impropers": "impropers"}


def _cell(d: DataText):
    xlo, xhi = map(float, d.header_values("xlo xhi"))
    ylo, yhi = map(float, d.header_values("ylo yhi"))
    zlo, zhi = map(float, d.header_values("zlo zhi"))
    try:
        xy, xz, yz = map(float, d.header_values("xy xz yz"))
    except KeyError:
        xy = xz = yz = 0.0
    H = np.array([[xhi - xlo, xy, xz], [0, yhi - ylo, yz], [0, 0, zhi - zlo]])
    return np.array([xlo, ylo, zlo]), H


def make_supercell(d: DataText, rep) -> DataText:
    na, nb, nc = rep
    origin, H = _cell(d)
    Hinv = np.linalg.inv(H)
    imgs = np.array(list(itertools.product((-1, 0, 1), repeat=3)))
    rows = [(split_comment(line)) for _, line in d.section_rows("Atoms")]
    ids = [int(t[0]) for t, _ in rows]
    idx = {a: k for k, a in enumerate(ids)}
    xyz = np.array([[float(v) for v in t[4:7]] for t, _ in rows])
    s = (xyz - origin) @ Hinv.T
    if (s < -1e-9).any() or (s >= 1 + 1e-9).any():
        raise ValueError("make_supercell expects atoms wrapped into the cell (run cellops.reduce_and_wrap first)")
    n, maxid = len(ids), max(ids)
    maxmol = max(int(t[1]) for t, _ in rows)
    copies = list(itertools.product(range(na), range(nb), range(nc)))
    cindex = {c: k for k, c in enumerate(copies)}

    def step(a, b):
        """Integer image offset to add to a's copy to reach the nearest image of b."""
        ds = s[idx[b]] - s[idx[a]]
        cand = ds[None, :] - imgs - np.round(ds)[None, :]
        k = int(np.argmin(np.linalg.norm(cand @ H.T, axis=1)))
        return -(np.round(ds).astype(int) + imgs[k])

    out = DataText(d.text())
    # header
    out.set_header("atoms", [n * len(copies)])
    for name, key in COUNT_KEY.items():
        try:
            out.set_header(key, [out.header_int(key) * len(copies)])
        except KeyError:
            pass
    x0, y0, z0 = origin
    out.set_header("xlo xhi", [f"{x0:.9f}", f"{x0 + na * H[0, 0]:.9f}"])
    out.set_header("ylo yhi", [f"{y0:.9f}", f"{y0 + nb * H[1, 1]:.9f}"])
    out.set_header("zlo zhi", [f"{z0:.9f}", f"{z0 + nc * H[2, 2]:.9f}"])
    if out.header_index("xy xz yz") is not None:
        out.set_header("xy xz yz", [f"{nb * H[0, 1]:.9f}", f"{nc * H[0, 2]:.9f}", f"{nc * H[1, 2]:.9f}"])
    # atoms
    new_atoms = []
    for c in copies:
        k = cindex[c]
        shift = H @ np.array(c)
        for (t, com), r in zip(rows, xyz):
            p = r + shift
            new_atoms.append(" ".join([str(int(t[0]) + k * maxid), str(int(t[1]) + k * maxmol), t[2], t[3]]
                                      + [f"{v:.9f}" for v in p] + ["0", "0", "0"]) + (f" {com}" if com else ""))
    _replace_rows(out, "Atoms", new_atoms)
    # topology
    for name, arity in TOPO.items():
        trows = [line.split("#")[0].split() for _, line in d.section_rows(name)]
        if not trows:
            continue
        new, eid = [], 0
        for c in copies:
            for t in trows:
                ttype, ats = t[1], [int(x) for x in t[2:2 + arity]]
                pos = {ats[0]: np.array(c)} if name != "Impropers" else {ats[1]: np.array(c)}
                if name == "Impropers":
                    for o in (ats[0], ats[2], ats[3]):
                        pos[o] = pos[ats[1]] + step(ats[1], o)
                else:
                    for a, b in zip(ats, ats[1:]):
                        pos[b] = pos[a] + step(a, b)
                eid += 1
                mapped = []
                for a in ats:
                    cc = tuple(int(v) % m for v, m in zip(pos[a], rep))
                    mapped.append(str(a + cindex[cc] * maxid))
                new.append(" ".join([str(eid), ttype] + mapped))
        _replace_rows(out, name, new)
    return out


def _replace_rows(d: DataText, name: str, rows):
    old = d.section_rows(name)
    first, last = old[0][0], old[-1][0]
    d.lines[first:last + 1] = rows

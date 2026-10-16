"""Cell geometry for orthogonal and restricted-triclinic boxes (PROPERTIES §8.4).

Convention (RD): origin (xlo, ylo, zlo); edge vectors A=(lx,0,0), B=(xy,ly,0), C=(xz,yz,lz).
H = [A B C] with the edge vectors as *columns*; fractional s = H^-1 (r - origin).
Distances use fractional differences with Δs -= round(Δs) in periodic dimensions, then the
27 neighbouring images are searched so the true minimum is found even in strongly tilted cells.
Axis-wise wrapping with lx, ly, lz is never used.
"""
from __future__ import annotations

import itertools
from typing import Dict, Optional, Sequence, Tuple

import functools

import numpy as np

AMU_PER_A3_TO_G_PER_CM3 = 1.66053906660   # 1 amu/Å^3 in g/cm^3


def _quiet(fn):
    """NumPy 2.0 wheels on macOS/Accelerate raise spurious FP warnings inside matmul even for
    finite inputs; results are unaffected. Silence them here; callers check finiteness explicitly."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        with np.errstate(all="ignore"):
            return fn(*a, **k)
    return wrapper


class Cell:
    def __init__(self, xlo, xhi, ylo, yhi, zlo, zhi, xy=0.0, xz=0.0, yz=0.0,
                 periodic: Sequence[bool] = (True, True, True)):
        self.origin = np.array([xlo, ylo, zlo], dtype=float)
        self.lengths = np.array([xhi - xlo, yhi - ylo, zhi - zlo], dtype=float)
        self.tilt = np.array([xy, xz, yz], dtype=float)
        lx, ly, lz = self.lengths
        self.H = np.array([[lx, xy, xz],
                           [0.0, ly, yz],
                           [0.0, 0.0, lz]])
        self.Hinv = np.linalg.inv(self.H)
        self.periodic = np.array(periodic, dtype=bool)

    @property
    def triclinic(self) -> bool:
        return bool(np.any(self.tilt != 0.0))

    @property
    def volume(self) -> float:
        return float(np.prod(self.lengths))     # det H; tilt does not change it

    def perpendicular_widths(self) -> np.ndarray:
        """Distance between opposite faces of the cell (bounds safe neighbour-cell sizes)."""
        a, b, c = self.H[:, 0], self.H[:, 1], self.H[:, 2]
        v = self.volume
        return np.array([v / np.linalg.norm(np.cross(b, c)),
                         v / np.linalg.norm(np.cross(c, a)),
                         v / np.linalg.norm(np.cross(a, b))])

    @_quiet
    def fractional(self, xyz: np.ndarray) -> np.ndarray:
        return (np.asarray(xyz, float) - self.origin) @ self.Hinv.T

    @_quiet
    def cartesian(self, s: np.ndarray) -> np.ndarray:
        return np.asarray(s, float) @ self.H.T + self.origin

    def image_offsets(self) -> np.ndarray:
        """The 27 (or fewer, for non-periodic dims) integer image shifts."""
        rng = [(-1, 0, 1) if p else (0,) for p in self.periodic]
        return np.array(list(itertools.product(*rng)), dtype=float)

    @_quiet
    def min_image_vectors(self, dr: np.ndarray) -> np.ndarray:
        """Minimum-image versions of Cartesian difference vectors dr (n,3)."""
        dr = np.atleast_2d(np.asarray(dr, float))
        ds = dr @ self.Hinv.T
        ds[:, self.periodic] -= np.round(ds[:, self.periodic])
        best = ds @ self.H.T
        bestd = np.einsum("ij,ij->i", best, best)
        for off in self.image_offsets():
            if not off.any():
                continue
            cand = (ds + off) @ self.H.T
            d = np.einsum("ij,ij->i", cand, cand)
            better = d < bestd
            if better.any():
                best[better] = cand[better]
                bestd[better] = d[better]
        return best

    @_quiet
    def min_image_distances(self, dr: np.ndarray) -> np.ndarray:
        v = self.min_image_vectors(dr)
        return np.sqrt(np.einsum("ij,ij->i", v, v))


@_quiet
def pairs_within(cell: Cell, xyz: np.ndarray, cutoff: float,
                 max_pairs: int = 5_000_000) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All atom pairs (i<j) with minimum-image distance < cutoff.

    Uses a linked-cell search in fractional space when every periodic dimension can hold at least
    three bins of width >= cutoff (then the minimum image is unique and only neighbouring bins
    need to be searched). Small or strongly tilted cells fall back to an all-pairs search over the
    27 images, done in chunks.
    """
    xyz = np.asarray(xyz, float)
    n = len(xyz)
    if n < 2:
        e = np.zeros(0, dtype=int)
        return e, e, np.zeros(0)
    widths = cell.perpendicular_widths()
    # Bins must be at least `cutoff` wide; cap their number so tiny cutoffs stay cheap.
    nb = np.minimum(np.maximum(1, np.floor(widths / cutoff).astype(int)), 48)
    use_bins = all((nb[k] >= 3) or not cell.periodic[k] for k in range(3)) and n > 64
    if not use_bins:
        return _pairs_bruteforce(cell, xyz, cutoff)

    s = cell.fractional(xyz)
    s_w = s.copy()
    s_w[:, cell.periodic] -= np.floor(s_w[:, cell.periodic])
    # Non-periodic dims: bin over the actual coordinate range.
    lo = np.zeros(3)
    span = np.ones(3)
    for k in range(3):
        if not cell.periodic[k]:
            lo[k] = s_w[:, k].min()
            span[k] = max(s_w[:, k].max() - lo[k], 1e-12)
            nb[k] = min(48, max(1, int(np.floor(span[k] * widths[k] / cutoff))))
    idx = np.floor((s_w - lo) / span * nb).astype(int)
    idx = np.minimum(np.maximum(idx, 0), nb - 1)
    flat = (idx[:, 0] * nb[1] + idx[:, 1]) * nb[2] + idx[:, 2]
    order = np.argsort(flat, kind="stable")
    flat_sorted = flat[order]
    nbins = int(np.prod(nb))
    starts = np.searchsorted(flat_sorted, np.arange(nbins), side="left")
    ends = np.searchsorted(flat_sorted, np.arange(nbins), side="right")

    I, J, D = [], [], []
    offsets = list(itertools.product((-1, 0, 1), repeat=3))
    cutoff2 = cutoff * cutoff
    for bx in range(nb[0]):
        for by in range(nb[1]):
            for bz in range(nb[2]):
                b = (bx * nb[1] + by) * nb[2] + bz
                ai = order[starts[b]:ends[b]]
                if len(ai) == 0:
                    continue
                seen = set()
                for ox, oy, oz in offsets:
                    nbx, nby, nbz = bx + ox, by + oy, bz + oz
                    ok = True
                    coords = []
                    for k, v in enumerate((nbx, nby, nbz)):
                        if 0 <= v < nb[k]:
                            coords.append(v)
                        elif cell.periodic[k]:
                            coords.append(v % nb[k])
                        else:
                            ok = False
                            break
                    if not ok:
                        continue
                    b2 = (coords[0] * nb[1] + coords[1]) * nb[2] + coords[2]
                    if b2 < b or b2 in seen:
                        continue
                    seen.add(b2)
                    aj = order[starts[b2]:ends[b2]]
                    if len(aj) == 0:
                        continue
                    dr = xyz[aj][None, :, :] - xyz[ai][:, None, :]
                    dr = dr.reshape(-1, 3)
                    ds = dr @ cell.Hinv.T
                    ds[:, cell.periodic] -= np.round(ds[:, cell.periodic])
                    v = ds @ cell.H.T
                    d2 = np.einsum("ij,ij->i", v, v).reshape(len(ai), len(aj))
                    ii, jj = np.nonzero(d2 < cutoff2)
                    gi, gj = ai[ii], aj[jj]
                    keep = gi < gj if b2 == b else np.ones(len(gi), bool)
                    if b2 != b:
                        # canonical order for cross-bin pairs
                        gi, gj = np.minimum(gi, gj), np.maximum(gi, gj)
                    I.append(gi[keep]); J.append(gj[keep]); D.append(np.sqrt(d2[ii, jj][keep]))
                    if sum(len(x) for x in I) > max_pairs:
                        raise MemoryError("too many close pairs; cutoff too large")
    if not I:
        e = np.zeros(0, dtype=int)
        return e, e, np.zeros(0)
    I = np.concatenate(I); J = np.concatenate(J); D = np.concatenate(D)
    # A pair can be found twice only if nb==3 wraps a bin onto itself from both sides; dedupe.
    key = I.astype(np.int64) * n + J
    _, uniq = np.unique(key, return_index=True)
    return I[uniq], J[uniq], D[uniq]


@_quiet
def _pairs_bruteforce(cell: Cell, xyz: np.ndarray, cutoff: float, chunk: int = 256):
    n = len(xyz)
    I, J, D = [], [], []
    for a in range(0, n, chunk):
        ai = np.arange(a, min(a + chunk, n))
        dr = xyz[None, :, :] - xyz[ai][:, None, :]
        flat = dr.reshape(-1, 3)
        d = cell.min_image_distances(flat).reshape(len(ai), n)
        ii, jj = np.nonzero(d < cutoff)
        gi, gj = ai[ii], jj
        keep = gi < gj
        I.append(gi[keep]); J.append(gj[keep]); D.append(d[ii, jj][keep])
    return np.concatenate(I), np.concatenate(J), np.concatenate(D)


def tilt_checks(cell: Cell) -> Dict[str, Dict[str, object]]:
    """Documented bound (RD) and LAMMPS source warning criterion (domain.cpp:217-222)."""
    lx, ly, lz = cell.lengths
    xy, xz, yz = cell.tilt
    doc = {
        "xy": (abs(xy), lx / 2), "xz": (abs(xz), lx / 2), "yz": (abs(yz), ly / 2),
    }
    doc_viol = {k: {"value": v, "bound": b} for k, (v, b) in doc.items() if v > b + 1e-12}
    src_viol = {}
    if cell.periodic[1] and ly > 0 and abs(xy) / ly > 0.5:
        src_viol["xy/ly"] = abs(xy) / ly
    if cell.periodic[2] and lz > 0 and (abs(xz) + abs(yz)) / lz > 0.5:
        src_viol["(xz+yz)/lz"] = (abs(xz) + abs(yz)) / lz
    return {"doc": doc_viol, "source": src_viol}

"""Tier 1 — internally consistent (PROPERTIES §8.3, P1.1–P1.15, plus P1.16 added in v0.4).

All checks are exact (§8.5 rule 2). They run on the typed Model built after Tier 0 passed.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

from .config import declared, periodic_flags, resolve
from .model import TOPOLOGY_ARITY, Model
from .parser import SECTIONS_COEFF, ParsedFile
from .result import FAIL, NOT_APPLICABLE, NOT_EVALUATED, PASS, CheckResult

MAXEX = 10
ACCEL_SUFFIXES = ("/kk/device", "/kk/host", "/gpu", "/intel", "/kk", "/omp", "/opt")
TOPO_KIND = {"Bonds": "bond", "Angles": "angle", "Dihedrals": "dihedral", "Impropers": "improper"}
COEFF_STYLE_KEY = {"Pair Coeffs": "pair", "PairIJ Coeffs": "pair", "Bond Coeffs": "bond",
                   "Angle Coeffs": "angle", "Dihedral Coeffs": "dihedral", "Improper Coeffs": "improper"}


def _c(name, prop, verdict, msg="", details=None, warnings=None):
    return CheckResult(name, prop, 1, verdict, msg, details or {}, warnings or [])


def _ok(name, prop, ok, msg, details=None, warnings=None):
    return _c(name, prop, PASS if ok else FAIL, "" if ok else msg, details, warnings)


# ----------------------------------------------------------------------------------------------
def p1_1_counts(pf: ParsedFile, m: Model, cfg) -> CheckResult:
    problems = []
    for key, sec in (("atoms", "Atoms"), ("bonds", "Bonds"), ("angles", "Angles"),
                     ("dihedrals", "Dihedrals"), ("impropers", "Impropers")):
        n = pf.header_int(key, 0) or 0
        s = pf.section(sec)
        if s is None:
            if n > 0:
                problems.append(f"header declares {n} {key} but there is no {sec} section")
            continue
        if n == 0:
            problems.append(f"{sec} section present (line {s.lineno}) but header declares 0 {key}")
        elif len(s.rows) != n:
            problems.append(f"{sec}: header declares {n}, section has {len(s.rows)} rows")
    return _ok("header_counts_match", "P1.1", not problems, "; ".join(problems), {"problems": problems})


def p1_2_atom_ids(pf, m: Model, cfg) -> CheckResult:
    ids = m.ids
    nonpos = [int(x) for x in ids[ids <= 0]]
    cnt = Counter(ids.tolist())
    dups = sorted(k for k, v in cnt.items() if v > 1)
    msg = []
    if nonpos:
        msg.append(f"{len(nonpos)} non-positive atom ID(s), e.g. {nonpos[:5]}")
    if dups:
        msg.append(f"{len(dups)} duplicated atom ID(s), e.g. {dups[:5]}")
    return _ok("atom_ids_unique_positive", "P1.2", not msg, "; ".join(msg),
               {"duplicates": dups[:MAXEX], "non_positive": nonpos[:MAXEX],
                "max_id": int(ids.max()) if len(ids) else 0, "natoms": int(len(ids))})


def p1_3_atom_types(pf, m: Model, cfg) -> CheckResult:
    nt = m.n_atom_types
    bad = [(m.atom_linenos[i], int(t)) for i, t in enumerate(m.types) if t < 1 or t > nt]
    used = set(m.types.tolist())
    unused = [t for t in range(1, nt + 1) if t not in used]
    warns = [f"atom type(s) declared but unused: {unused[:MAXEX]}"] if unused else []
    return _ok("atom_types_in_range", "P1.3", not bad,
               f"{len(bad)} Atoms row(s) with type outside 1..{nt}; first: line {bad[0][0]} type {bad[0][1]}" if bad else "",
               {"atom_types": nt, "out_of_range": bad[:MAXEX], "unused_types": unused}, warns)


def p1_4_masses(pf, m: Model, cfg) -> CheckResult:
    loc = declared(cfg).get("masses_location")
    sec = pf.section("Masses")
    if sec is None:
        if loc == "data_file":
            return _c("masses", "P1.4", FAIL, "no Masses section, but the declared configuration requires masses in the DATA FILE (S-Q1)")
        return _c("masses", "P1.4", PASS if loc else NOT_EVALUATED,
                  "no Masses section" + ("" if loc else "; masses_location not declared (S-Q1)"))
    nt = m.n_atom_types
    problems = []
    rows = Counter()
    for r in sec.rows:
        t = int(r.tokens[0])
        rows[t] += 1
        mass = float(r.tokens[1])
        if t < 1 or t > nt:
            problems.append(f"line {r.lineno}: type {t} outside 1..{nt}")
        if not (mass > 0):
            problems.append(f"line {r.lineno}: mass {mass} is not > 0")
    dup = sorted(t for t, c in rows.items() if c > 1)
    missing = [t for t in range(1, nt + 1) if rows.get(t, 0) == 0]
    if dup:
        problems.append(f"type(s) with more than one Masses row: {dup}")
    if missing:
        problems.append(f"type(s) with no Masses row: {missing[:MAXEX]}")
    return _ok("masses", "P1.4", not problems, "; ".join(problems),
               {"duplicated_types": dup, "missing_types": missing, "rows": len(sec.rows), "atom_types": nt})


def p1_5_topology_refs(pf, m: Model, cfg) -> CheckResult:
    idset = set(m.ids.tolist())
    problems = []
    nmax = {"Bonds": pf.header_int("bond types", 0), "Angles": pf.header_int("angle types", 0),
            "Dihedrals": pf.header_int("dihedral types", 0), "Impropers": pf.header_int("improper types", 0)}
    for name, topo in m.topology.items():
        for k in range(len(topo.ids)):
            ats = topo.atoms[k].tolist()
            ln = topo.linenos[k]
            missing = [a for a in ats if a not in idset]
            if missing:
                problems.append({"line": ln, "section": name, "reason": f"atom ID(s) {missing} not in Atoms"})
            if len(set(ats)) != len(ats):
                problems.append({"line": ln, "section": name, "reason": f"atom repeated within entry {ats}"})
            t = int(topo.types[k])
            if t < 1 or t > (nmax[name] or 0):
                problems.append({"line": ln, "section": name, "reason": f"type {t} outside 1..{nmax[name]}"})
    return _ok("topology_references", "P1.5", not problems,
               f"{len(problems)} bad topology reference(s); first: line {problems[0]['line'] if problems else ''} "
               f"({problems[0]['section'] if problems else ''}): {problems[0]['reason'] if problems else ''}",
               {"problems": problems[:MAXEX], "n_problems": len(problems)})


def _canon(name: str, ats: Tuple[int, ...]) -> Tuple[int, ...]:
    if name == "Bonds":
        return tuple(sorted(ats))
    if name in ("Angles", "Dihedrals"):
        return min(ats, tuple(reversed(ats)))
    return ats   # impropers: exact tuple (equivalence depends on improper style — OPEN)


def p1_6_topology_unique(pf, m: Model, cfg) -> CheckResult:
    problems, warns = [], []
    for name, topo in m.topology.items():
        idc = Counter(topo.ids.tolist())
        dup_ids = sorted(k for k, v in idc.items() if v > 1)
        if dup_ids:
            problems.append(f"{name}: duplicated entry ID(s) {dup_ids[:5]}")
        seen = {}
        for k in range(len(topo.ids)):
            key = _canon(name, tuple(topo.atoms[k].tolist()))
            if key in seen:
                problems.append(f"{name}: entry at line {topo.linenos[k]} duplicates line {seen[key]} {list(key)}")
            else:
                seen[key] = topo.linenos[k]
        if name == "Impropers":
            perm = {}
            for k in range(len(topo.ids)):
                a = topo.atoms[k].tolist()
                key = (a[1], tuple(sorted([a[0], a[2], a[3]])))
                if key in perm and _canon(name, tuple(a)) != perm[key][1]:
                    warns.append(f"Impropers: line {topo.linenos[k]} is a permutation of line {perm[key][0]} "
                                 f"(same central atom {a[1]}); equivalence is style-dependent (OPEN)")
                perm.setdefault(key, (topo.linenos[k], _canon(name, tuple(a))))
    return _ok("topology_unique", "P1.6", not problems,
               f"{len(problems)} duplicate topology entr(ies); first: {problems[0] if problems else ''}",
               {"problems": problems[:MAXEX]}, warns[:MAXEX])


def p1_7_coeffs(pf, m: Model, cfg) -> CheckResult:
    dec = declared(cfg)
    problems, notes = [], []
    param_counts = dec.get("coeff_param_counts") or {}
    for s in pf.sections:
        if s.name not in SECTIONS_COEFF:
            continue
        n = pf.expected_rows(s.name)
        if len(s.rows) != n:
            problems.append(f"{s.name}: {len(s.rows)} rows, expected {n}")
        ids = Counter()
        for r in s.rows:
            if s.name == "PairIJ Coeffs":
                i, j = int(r.tokens[0]), int(r.tokens[1])
                if i > j:
                    problems.append(f"{s.name} line {r.lineno}: I={i} > J={j}")
                ids[(i, j)] += 1
            else:
                ids[int(r.tokens[0])] += 1
        if s.name == "PairIJ Coeffs":
            nt = m.n_atom_types
            want = {(i, j) for i in range(1, nt + 1) for j in range(i, nt + 1)}
        else:
            want = set(range(1, (n or 0) + 1))
        dup = sorted(k for k, v in ids.items() if v > 1)
        missing = sorted(want - set(ids))
        extra = sorted(set(ids) - want)
        if dup:
            problems.append(f"{s.name}: type(s) listed more than once {dup[:5]}")
        if missing:
            problems.append(f"{s.name}: type(s) with no row {missing[:5]}")
        if extra:
            problems.append(f"{s.name}: type(s) outside the declared range {extra[:5]}")
        if s.name in param_counts:
            nid = 2 if s.name == "PairIJ Coeffs" else 1
            want_p = param_counts[s.name]
            badp = [r.lineno for r in s.rows if len(r.tokens) - nid != want_p]
            if badp:
                problems.append(f"{s.name}: {len(badp)} row(s) without {want_p} parameters (first line {badp[0]})")
        elif s.rows:
            notes.append(f"{s.name}: parameter count not checked (no declared count; OD-C2)")
    if dec.get("coeffs_location") == "data_file":
        for req in dec.get("required_coeff_sections", []):
            if pf.section(req) is None:
                problems.append(f"required section '{req}' missing (coeffs_location: data_file)")
    return _ok("coeff_sections", "P1.7", not problems, "; ".join(problems[:5]),
               {"problems": problems, "notes": notes})


def p1_8_molecules(pf, m: Model, cfg) -> CheckResult:
    if m.mol is None:
        return _c("molecule_ids", "P1.8", NOT_APPLICABLE, f"atom_style {m.atom_style} has no molecule IDs")
    policy = declared(cfg).get("molecule_bond_policy", "report")
    problems, warns = [], []
    neg = [(m.atom_linenos[i], int(v)) for i, v in enumerate(m.mol) if v < 0]
    if neg:
        problems.append(f"{len(neg)} negative molecule ID(s); first: line {neg[0][0]} mol {neg[0][1]}")
    crossing = []
    b = m.topology.get("Bonds")
    if b is not None and len(b.ids):
        idx = m.index_of()
        for k, (i, j) in enumerate(b.atoms):
            if int(i) in idx and int(j) in idx and m.mol[idx[int(i)]] != m.mol[idx[int(j)]]:
                crossing.append(b.linenos[k])
    if crossing:
        text = f"{len(crossing)} bond(s) join atoms with different molecule IDs (first: line {crossing[0]})"
        if policy == "within_molecule":
            problems.append(text)
        else:
            warns.append(text + " — policy OPEN, reported only")
    return _ok("molecule_ids", "P1.8", not problems, "; ".join(problems),
               {"negative": neg[:MAXEX], "crossing_bond_lines": crossing[:MAXEX], "policy": policy}, warns)


def p1_9_image_flags(pf, m: Model, cfg) -> CheckResult:
    policy = declared(cfg).get("image_flag_policy", "optional")
    periodic = periodic_flags(cfg)
    if m.image is None:
        if policy == "required":
            return _c("image_flags", "P1.9", FAIL, "image flags required by the declared configuration (S-Q3) but absent")
        return _c("image_flags", "P1.9", PASS, "no image flags", {"policy": policy})
    if policy == "forbidden":
        return _c("image_flags", "P1.9", FAIL, "image flags present but forbidden by the declared configuration (S-Q3)")
    bad = []
    for d in range(3):
        if not periodic[d]:
            nz = np.nonzero(m.image[:, d])[0]
            if len(nz):
                bad.append(f"{len(nz)} non-zero {'xyz'[d]} image flag(s) in a non-periodic dimension "
                           f"(first: line {m.atom_linenos[nz[0]]})")
    return _ok("image_flags", "P1.9", not bad, "; ".join(bad), {"policy": policy})


def p1_10_bonded_consistency(pf, m: Model, cfg) -> CheckResult:
    pol = declared(cfg).get("bonded_term_consistency", "unknown")
    if pol != "required":
        return _c("bonded_term_consistency", "P1.10", NOT_APPLICABLE if pol == "not_required" else NOT_EVALUATED,
                  f"applicability depends on the force-field convention (declared: {pol}; OD-C2)")
    bonds = set()
    b = m.topology.get("Bonds")
    if b is not None:
        bonds = {tuple(sorted(x)) for x in b.atoms.tolist()}
    problems = []
    for name, need in (("Angles", [(0, 1), (1, 2)]), ("Dihedrals", [(0, 1), (1, 2), (2, 3)])):
        t = m.topology.get(name)
        if t is None:
            continue
        for k, ats in enumerate(t.atoms.tolist()):
            miss = [(ats[a], ats[c]) for a, c in need if tuple(sorted((ats[a], ats[c]))) not in bonds]
            if miss:
                problems.append({"section": name, "line": t.linenos[k], "missing_bonds": miss})
    return _ok("bonded_term_consistency", "P1.10", not problems,
               f"{len(problems)} angle/dihedral entr(ies) without the bonds they imply; first: "
               f"{problems[0]['section'] if problems else ''} line {problems[0]['line'] if problems else ''} "
               f"missing {problems[0]['missing_bonds'] if problems else ''}",
               {"problems": problems[:MAXEX], "n_problems": len(problems)})


def _strip_suffix(style: str) -> str:
    for suf in ACCEL_SUFFIXES:
        if style.endswith(suf):
            return style[: -len(suf)]
    return style


def p1_11_style_comments(pf, m: Model, cfg) -> CheckResult:
    dec = declared(cfg)
    styles = dict(dec.get("styles") or {})
    styles["atom"] = dec.get("atom_style")
    problems, unchecked = [], []
    for s in pf.sections:
        if not s.style_comment:
            continue
        key = "atom" if s.name == "Atoms" else COEFF_STYLE_KEY.get(s.name)
        if key is None:
            continue
        want = styles.get(key)
        got = s.style_comment.split()[0]
        if not want:
            unchecked.append(s.name)
            continue
        if _strip_suffix(got) != _strip_suffix(want):
            problems.append(f"line {s.lineno}: '{s.name} # {got}' but the declared {key} style is '{want}'")
    if unchecked and not problems:
        return _c("style_comments", "P1.11", NOT_EVALUATED, f"declared style missing for {unchecked} (OD-C1/OD-C2)")
    return _ok("style_comments", "P1.11", not problems, "; ".join(problems), {"unchecked": unchecked})


def p1_12_nonperiodic_containment(pf, m: Model, cfg) -> CheckResult:
    periodic = periodic_flags(cfg)
    if all(periodic):
        return _c("nonperiodic_containment", "P1.12", NOT_APPLICABLE, "all dimensions periodic")
    if m.cell is None:
        return _c("nonperiodic_containment", "P1.12", NOT_EVALUATED, "box not defined")
    s = m.cell.fractional(m.xyz)
    bad = []
    for d in range(3):
        if not periodic[d]:
            out = np.nonzero((s[:, d] < 0.0) | (s[:, d] >= 1.0))[0]
            if len(out):
                bad.append(f"{len(out)} atom(s) outside [lo, hi) in non-periodic {'xyz'[d]} "
                           f"(first: line {m.atom_linenos[out[0]]}, s={s[out[0], d]:.6f})")
    return _ok("nonperiodic_containment", "P1.12", not bad, "; ".join(bad))


def p1_13_topology_type_counts(pf, m: Model, cfg) -> CheckResult:
    problems = []
    for name, topo in m.topology.items():
        key = f"{TOPO_KIND[name]} types"
        nt = pf.header_int(key, 0) or 0
        if len(topo.types) and nt == 0:
            problems.append(f"{name} present but header declares 0 {key}")
        elif len(topo.types) and int(topo.types.max()) > nt:
            problems.append(f"{name}: max type {int(topo.types.max())} > header {key} = {nt}")
    return _ok("topology_type_counts", "P1.13", not problems, "; ".join(problems))


def p1_14_velocities(pf, m: Model, cfg) -> CheckResult:
    if m.velocity_ids is None:
        return _c("velocities", "P1.14", NOT_APPLICABLE, "no Velocities section")
    ids = set(m.ids.tolist())
    vc = Counter(m.velocity_ids.tolist())
    problems = []
    if len(m.velocity_ids) != m.natoms:
        problems.append(f"{len(m.velocity_ids)} Velocities rows for {m.natoms} atoms")
    dup = sorted(k for k, v in vc.items() if v > 1)
    absent = sorted(set(vc) - ids)
    nov = sorted(ids - set(vc))
    if dup:
        problems.append(f"atom ID(s) with more than one velocity row: {dup[:5]}")
    if absent:
        problems.append(f"velocity rows for atom ID(s) not in Atoms: {absent[:5]}")
    if nov:
        problems.append(f"atom(s) with no velocity row: {nov[:5]}")
    return _ok("velocities", "P1.14", not problems, "; ".join(problems))


def p1_15_units_hint(pf, m: Model, cfg) -> CheckResult:
    units = declared(cfg).get("units")
    pol = declared(cfg).get("units_hint_policy", "optional")
    hint = pf.units_hint
    if hint is None:
        if pol == "required":
            return _c("units_hint", "P1.15", FAIL, "line 1 has no 'units = <style>' hint, required by the declared configuration (S-Q7)")
        return _c("units_hint", "P1.15", PASS, "no units hint on line 1")
    if not units:
        return _c("units_hint", "P1.15", NOT_EVALUATED, f"units hint '{hint}' present but units not declared (OD-C3)")
    return _ok("units_hint", "P1.15", hint == units,
               f"line 1 declares units = {hint}, declared configuration uses {units}", {"hint": hint, "declared": units})


# ---- P1.16 (new in v0.4) ----------------------------------------------------------------------
def _signature(kind: str, names: Tuple[str, ...]) -> Tuple[str, ...]:
    if kind == "Bonds":
        return tuple(sorted(names))
    if kind in ("Angles", "Dihedrals"):
        return min(names, tuple(reversed(names)))
    return tuple(sorted(names))    # impropers: permutation-invariant multiset (weak but convention-free)


def _parse_signature_comment(comment: str, arity: int, known: set) -> Optional[Tuple[str, ...]]:
    if not comment or not comment.split():
        return None
    text = comment.split()[0]
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        return tuple(parts) if len(parts) == arity and all(p in known for p in parts) else None
    # hyphen-separated (msi2lmp). Names may themselves contain '-' (e.g. 'o1-'), so try every
    # split into known type names and accept it only if exactly one split works.
    toks = text.split("-")
    results = []

    def rec(i, acc):
        if len(acc) > arity:
            return
        if i == len(toks):
            if len(acc) == arity:
                results.append(tuple(acc))
            return
        for j in range(i + 1, len(toks) + 1):
            cand = "-".join(toks[i:j])
            if cand in known:
                rec(j, acc + [cand])

    rec(0, [])
    return results[0] if len(results) == 1 else None


COEFF_LINE_RE = re.compile(r"^\s*(bond|angle|dihedral|improper)_coeff\s+(\d+)\s+(.*?)#\s*(\S+)\s*$")


def expected_signatures(pf: ParsedFile, m: Model, cfg) -> Dict[str, Dict[int, Tuple[str, ...]]]:
    """Expected type signatures from coefficient-row comments (DATA FILE Coeff sections, or the
    declared coefficient file). Rows with class-2 cross-term keywords (bb, ba, mbt, ...) are skipped."""
    known = set(m.type_names.values())
    out: Dict[str, Dict[int, Tuple[str, ...]]] = defaultdict(dict)
    sec_map = {"Bond Coeffs": "Bonds", "Angle Coeffs": "Angles", "Dihedral Coeffs": "Dihedrals",
               "Improper Coeffs": "Impropers"}
    for sname, kind in sec_map.items():
        s = pf.section(sname)
        if not s:
            continue
        for r in s.rows:
            sig = _parse_signature_comment(r.comment or "", TOPOLOGY_ARITY[kind], known)
            if sig:
                out[kind][int(r.tokens[0])] = sig
    cf = declared(cfg).get("coeff_file")
    if cf:
        path = resolve(cf)
        try:
            with open(path) as fh:
                for line in fh:
                    mm = COEFF_LINE_RE.match(line)
                    if not mm:
                        continue
                    kind = {"bond": "Bonds", "angle": "Angles", "dihedral": "Dihedrals", "improper": "Impropers"}[mm.group(1)]
                    params = mm.group(3).split()
                    if params and params[0].isalpha():
                        continue      # class-2 cross terms: 'bb', 'ba', 'mbt', 'ebt', 'at', 'aat', 'bb13', 'aa'
                    sig = _parse_signature_comment(mm.group(4), TOPOLOGY_ARITY[kind], known)
                    if sig:
                        out[kind].setdefault(int(mm.group(2)), sig)
        except OSError:
            pass
    return out


def p1_16_topology_signatures(pf, m: Model, cfg) -> CheckResult:
    pol = declared(cfg).get("topology_signature_policy", "off")
    if pol == "off":
        return _c("topology_type_signatures", "P1.16", NOT_APPLICABLE, "disabled in the declared configuration")
    if not m.type_names:
        names = {t: str(t) for t in range(1, m.n_atom_types + 1)}
        have_names = False
    else:
        names = m.type_names
        have_names = True
    idx = m.index_of()
    tmap = {int(a): names.get(int(t), f"?{t}") for a, t in zip(m.ids, m.types)}
    expected = expected_signatures(pf, m, cfg) if have_names else {}
    problems = []
    observed: Dict[str, Dict[int, Counter]] = {}
    for kind, topo in m.topology.items():
        per = defaultdict(Counter)
        for k in range(len(topo.ids)):
            ats = topo.atoms[k].tolist()
            if not all(a in idx for a in ats):
                continue
            sig = _signature(kind, tuple(tmap[a] for a in ats))
            per[int(topo.types[k])][sig] += 1
        observed[kind] = per
        for t, sigs in per.items():
            if len(sigs) > 1:
                problems.append(f"{kind} type {t} joins {len(sigs)} different atom-type signatures: "
                                f"{[list(s) for s, _ in sigs.most_common(3)]}")
            exp = expected.get(kind, {}).get(t)
            if exp is not None:
                exp_c = _signature(kind, exp)
                wrong = {s: c for s, c in sigs.items() if s != exp_c}
                if wrong:
                    s0, c0 = next(iter(wrong.items()))
                    problems.append(f"{kind} type {t}: coefficient comment says {list(exp_c)}, "
                                    f"but {c0} entr(ies) join {list(s0)}")
    n_exp = sum(len(v) for v in expected.values())
    return _ok("topology_type_signatures", "P1.16", not problems,
               f"{len(problems)} topology-type/atom-type inconsistenc(ies); first: {problems[0] if problems else ''}",
               {"problems": problems[:MAXEX], "n_problems": len(problems), "policy": pol,
                "expected_signatures_found": n_exp, "type_names_available": have_names})


# ---- P1.17 (new in v0.4) ----------------------------------------------------------------------
def p1_17_bonded_completeness(pf, m: Model, cfg) -> CheckResult:
    """Converse of P1.10: with force fields whose writer derives angles, dihedrals and impropers from
    the bond graph (EMC/PCFF, msi2lmp), every bonded triple must have an angle, every bonded path
    i-j-k-l (i != l) a dihedral, and every atom with n >= 3 neighbours C(n,3) impropers."""
    pol = declared(cfg).get("bonded_term_completeness", "unknown")
    if pol != "required":
        return _c("bonded_term_completeness", "P1.17", NOT_APPLICABLE if pol == "not_required" else NOT_EVALUATED,
                  f"applicability depends on the force-field / writer convention (declared: {pol}; OD-C2)")
    from itertools import combinations
    nb = defaultdict(set)
    b = m.topology.get("Bonds")
    if b is not None:
        for i, j in b.atoms.tolist():
            nb[i].add(j)
            nb[j].add(i)
    problems = []
    want_a = {min((i, j, k), (k, j, i)) for j in nb for i, k in combinations(sorted(nb[j]), 2)}
    got_a = {min(tuple(x), tuple(x[::-1])) for x in m.topology["Angles"].atoms.tolist()} if "Angles" in m.topology else set()
    miss_a = want_a - got_a
    if miss_a:
        problems.append(f"{len(miss_a)} bonded triple(s) without an angle, e.g. {sorted(miss_a)[0]}")
    want_d = set()
    for j in nb:
        for k in nb[j]:
            for i in nb[j] - {k}:
                for l in nb[k] - {j}:
                    if i != l:
                        t = (i, j, k, l)
                        want_d.add(min(t, t[::-1]))
    got_d = {min(tuple(x), tuple(x[::-1])) for x in m.topology["Dihedrals"].atoms.tolist()} if "Dihedrals" in m.topology else set()
    miss_d = want_d - got_d
    if miss_d:
        problems.append(f"{len(miss_d)} bonded path(s) i-j-k-l without a dihedral, e.g. {sorted(miss_d)[0]}")
    ci = int(declared(cfg).get("improper_center_index", 1))
    want_i = {(j, frozenset(c)) for j in nb if len(nb[j]) >= 3 for c in combinations(nb[j], 3)}
    got_i = set()
    if "Impropers" in m.topology:
        for x in m.topology["Impropers"].atoms.tolist():
            got_i.add((x[ci], frozenset(x[:ci] + x[ci + 1:])))
    miss_i = want_i - got_i
    if miss_i:
        j, others = sorted(miss_i, key=lambda t: t[0])[0]
        problems.append(f"{len(miss_i)} improper(s) missing (centre atom index {ci}), e.g. centre {j} with {sorted(others)}")
    return _ok("bonded_term_completeness", "P1.17", not problems, "; ".join(problems),
               {"expected": {"angles": len(want_a), "dihedrals": len(want_d), "impropers": len(want_i)},
                "missing": {"angles": len(miss_a), "dihedrals": len(miss_d), "impropers": len(miss_i)}})


TIER1_CHECKS = [p1_1_counts, p1_2_atom_ids, p1_3_atom_types, p1_4_masses, p1_5_topology_refs,
                p1_6_topology_unique, p1_7_coeffs, p1_8_molecules, p1_9_image_flags,
                p1_10_bonded_consistency, p1_11_style_comments, p1_12_nonperiodic_containment,
                p1_13_topology_type_counts, p1_14_velocities, p1_15_units_hint, p1_16_topology_signatures,
                p1_17_bonded_completeness]


def run_tier1(pf: ParsedFile, m: Model, cfg) -> List[CheckResult]:
    return [fn(pf, m, cfg) for fn in TIER1_CHECKS]

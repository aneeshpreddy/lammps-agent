"""Tier 0 — parseable (PROPERTIES §8.3, P0.1–P0.12). All checks are exact."""
from __future__ import annotations

from typing import Any, Dict, List

from .config import declared
from .parser import (ATOM_STYLE_COLUMNS, HEADER_FLOAT_KEYWORDS, HEADER_INT_KEYWORDS, HEADER_UNSUPPORTED,
                     INT_COLUMNS, SECTION_BODY_STYLES, SECTION_COEFF_CLASS1, SECTION_COEFF_CLASS2,
                     SECTION_TYPE_LABELS, SECTIONS_ALL, SECTIONS_COEFF, UINT_RE, ParsedFile, is_float,
                     is_int, match_header)
from .result import FAIL, NOT_EVALUATED, PASS, CheckResult

MAX_LINE = 254
DEFAULT_ALLOWED_SECTIONS = ["Atoms", "Velocities", "Masses", "Bonds", "Angles", "Dihedrals",
                            "Impropers"] + SECTION_COEFF_CLASS1
TOPO_ARITY = {"Bonds": 2, "Angles": 3, "Dihedrals": 4, "Impropers": 4}
COEFF_ID_FIELDS = {"PairIJ Coeffs": 2}
MAX_EXAMPLES = 10


def _check(name, prop, ok, msg_fail, details=None, msg_ok=""):
    return CheckResult(name, prop, 0, PASS if ok else FAIL, msg_ok if ok else msg_fail, details or {})


def _examples(items: List[Any]) -> List[Any]:
    return items[:MAX_EXAMPLES]


def allowed_sections(cfg) -> List[str]:
    return declared(cfg).get("allowed_sections") or DEFAULT_ALLOWED_SECTIONS


# ----------------------------------------------------------------------------------------------
def p0_1_header(pf: ParsedFile, cfg) -> CheckResult:
    problems = [{"line": h.lineno, "text": h.raw.strip()[:80], "reason": h.reason} for h in pf.header_issues]
    # Header-shaped lines inside the body are misplaced (FM21).
    for s in pf.sections:
        for r in s.rows:
            key, _, _ = match_header(" ".join(r.tokens))
            if key is not None:
                problems.append({"line": r.lineno, "text": " ".join(r.tokens)[:80],
                                 "reason": f"header line '{key}' after the first section keyword"})
    body_start = pf.sections[0].lineno if pf.sections else None
    n_content = sum(1 for ln in pf.lines[1:] if ln.strip() and not ln.strip().startswith("#"))
    if not pf.sections and n_content > len(pf.header):
        problems.append({"line": None, "text": "", "reason": "no section keyword found after the header"})
    return _check("header_structure", "P0.1", not problems,
                  f"{len(problems)} malformed header line(s); first: line {problems[0]['line'] if problems else ''}: "
                  f"{problems[0]['reason'] if problems else ''}",
                  {"problems": _examples(problems), "n_problems": len(problems), "body_starts_at_line": body_start})


def p0_2_sections(pf: ParsedFile, cfg) -> CheckResult:
    allowed = set(allowed_sections(cfg))
    problems = []
    seen = {}
    for s in pf.sections:
        if not s.recognised:
            hint = None
            norm = " ".join(s.name.split()).lower()
            for cand in SECTIONS_ALL:
                if cand.lower() == norm:
                    hint = cand
            problems.append({"line": s.lineno, "section": s.name, "reason": "unrecognised section keyword"
                             + (f" (did you mean '{hint}'? matching is exact and case-sensitive)" if hint else "")})
        elif s.name not in allowed:
            why = ("type-label sections unsupported (OD-K)" if s.name in SECTION_TYPE_LABELS else
                   "class 2 Coeff section not enabled in the declared configuration" if s.name in SECTION_COEFF_CLASS2 else
                   "finite-size/body section out of scope" if s.name in SECTION_BODY_STYLES else
                   "section not allowed by the declared configuration")
            problems.append({"line": s.lineno, "section": s.name, "reason": f"unsupported in scope: {why}"})
        if s.name in seen:
            problems.append({"line": s.lineno, "section": s.name,
                             "reason": f"section repeated (first at line {seen[s.name]})"})
        seen.setdefault(s.name, s.lineno)
    return _check("section_names", "P0.2", not problems,
                  f"{len(problems)} section keyword problem(s); first: line {problems[0]['line'] if problems else ''} "
                  f"'{problems[0]['section'] if problems else ''}': {problems[0]['reason'] if problems else ''}",
                  {"problems": _examples(problems), "sections": pf.section_names()})


def _atom_field_types(atom_style: str, ntok: int) -> List[str]:
    cols = list(ATOM_STYLE_COLUMNS[atom_style])
    if ntok == len(cols) + 3:
        cols += ["ix", "iy", "iz"]
    return cols


def p0_3_numeric(pf: ParsedFile, cfg) -> CheckResult:
    problems = []
    style = declared(cfg).get("atom_style")

    def bad(line, field, tok, expect):
        problems.append({"line": line, "field": field, "token": tok[:40], "expected": expect})

    for e in pf.header:
        if e.key in HEADER_INT_KEYWORDS:
            if not UINT_RE.match(e.values[0]):
                bad(e.lineno, e.key, e.values[0], "non-negative integer")
        elif e.key in HEADER_FLOAT_KEYWORDS:
            for v in e.values:
                if not is_float(v):
                    bad(e.lineno, e.key, v, "finite float")
    atoms_blocked = False
    for s in pf.sections:
        if not s.recognised:
            continue
        for r in s.rows:
            t = r.tokens
            if s.name == "Atoms":
                if style not in ATOM_STYLE_COLUMNS:
                    atoms_blocked = True
                    break
                k = len(ATOM_STYLE_COLUMNS[style])
                if len(t) not in (k, k + 3):
                    continue        # column count is P0.4's verdict
                for col, tok in zip(_atom_field_types(style, len(t)), t):
                    if col in INT_COLUMNS:
                        if not is_int(tok):
                            bad(r.lineno, col, tok, "integer")
                    elif not is_float(tok):
                        bad(r.lineno, col, tok, "finite float")
            elif s.name in TOPO_ARITY:
                need = 2 + TOPO_ARITY[s.name]
                if len(t) != need:
                    bad(r.lineno, f"{s.name} row", " ".join(t), f"{need} fields")
                    continue
                for tok in t:
                    if not is_int(tok):
                        bad(r.lineno, s.name, tok, "integer")
            elif s.name == "Masses":
                if len(t) != 2:
                    bad(r.lineno, "Masses row", " ".join(t), "2 fields: type mass")
                    continue
                if not is_int(t[0]):
                    bad(r.lineno, "type", t[0], "integer")
                if not is_float(t[1]):
                    bad(r.lineno, "mass", t[1], "finite float")
            elif s.name == "Velocities":
                if len(t) != 4:
                    bad(r.lineno, "Velocities row", " ".join(t), "4 fields: atom-ID vx vy vz")
                    continue
                if not is_int(t[0]):
                    bad(r.lineno, "atom-ID", t[0], "integer")
                for tok in t[1:]:
                    if not is_float(tok):
                        bad(r.lineno, "velocity", tok, "finite float")
            elif s.name in SECTIONS_COEFF:
                nid = COEFF_ID_FIELDS.get(s.name, 1)
                if len(t) < nid + 1:
                    bad(r.lineno, f"{s.name} row", " ".join(t), f">= {nid + 1} fields")
                    continue
                for tok in t[:nid]:
                    if not is_int(tok):
                        bad(r.lineno, "type", tok, "integer")
                for tok in t[nid:]:
                    if not is_float(tok):
                        bad(r.lineno, "coefficient", tok, "finite float")
    if atoms_blocked:
        others = problems
        return CheckResult("numeric_syntax", "P0.3", 0, FAIL if others else NOT_EVALUATED,
                           ("non-Atoms numeric problems found; " if others else "")
                           + "Atoms fields not checked: atom_style not declared (OD-C1)",
                           {"problems": _examples(problems)})
    return _check("numeric_syntax", "P0.3", not problems,
                  f"{len(problems)} malformed field(s); first: line {problems[0]['line'] if problems else ''} "
                  f"{problems[0]['field'] if problems else ''}={problems[0]['token'] if problems else ''!r} "
                  f"(expected {problems[0]['expected'] if problems else ''})",
                  {"problems": _examples(problems), "n_problems": len(problems)})


def p0_4_atoms_columns(pf: ParsedFile, cfg) -> CheckResult:
    style = declared(cfg).get("atom_style")
    if style not in ATOM_STYLE_COLUMNS:
        return CheckResult("atoms_columns", "P0.4", 0, NOT_EVALUATED,
                           f"atom_style {style!r} not declared or not supported (OD-C1)")
    sec = pf.section("Atoms")
    if sec is None:
        return CheckResult("atoms_columns", "P0.4", 0, PASS, "no Atoms section (P1.1 decides if one is required)")
    k = len(ATOM_STYLE_COLUMNS[style])
    counts = {}
    bad = []
    for r in sec.rows:
        n = len(r.tokens)
        counts[n] = counts.get(n, 0) + 1
        if n not in (k, k + 3):
            bad.append({"line": r.lineno, "fields": n})
    mixed = len(counts) > 1
    ok = not bad and not mixed
    msg = (f"{len(bad)} Atoms row(s) with a field count other than {k} or {k + 3} for atom_style {style}; "
           f"first at line {bad[0]['line']} ({bad[0]['fields']} fields)" if bad else
           f"image flags on some Atoms rows only (field counts {sorted(counts)})" if mixed else "")
    return _check("atoms_columns", "P0.4", ok, msg,
                  {"atom_style": style, "expected_fields": [k, k + 3], "field_counts": counts,
                   "bad_rows": _examples(bad)})


def p0_5_box(pf: ParsedFile, cfg) -> CheckResult:
    problems = []
    for e in pf.header:
        if e.key in HEADER_UNSUPPORTED:
            problems.append({"line": e.lineno, "reason": f"'{e.key}' unsupported in scope (general triclinic / body styles)"})
    for key in ("xlo xhi", "ylo yhi", "zlo zhi"):
        v = pf.header_floats(key)
        if v and not v[0] < v[1]:
            problems.append({"line": next(e.lineno for e in pf.header if e.key == key),
                             "reason": f"{key}: lo={v[0]} is not < hi={v[1]}"})
    return _check("box_representation", "P0.5", not problems,
                  f"{len(problems)} box problem(s): {problems[0]['reason'] if problems else ''}",
                  {"problems": problems})


def p0_6_line_length(pf: ParsedFile, cfg) -> CheckResult:
    long_lines = []
    for i, (ln, term) in enumerate(zip(pf.lines, pf.terminators)):
        n = len(ln) + (1 if term == "\r\n" else 0)   # a CR still occupies a character slot
        if n > MAX_LINE:
            long_lines.append({"line": i + 1, "length": n})
    return _check("line_length", "P0.6", not long_lines,
                  f"{len(long_lines)} line(s) longer than {MAX_LINE} characters (LAMMPS silently truncates); "
                  f"first: line {long_lines[0]['line'] if long_lines else ''} ({long_lines[0]['length'] if long_lines else ''} chars)",
                  {"long_lines": _examples(long_lines)})


def p0_7_blank_after_keyword(pf: ParsedFile, cfg) -> CheckResult:
    bad = [{"line": s.lineno + 1, "section": s.name} for s in pf.sections if s.line_after_keyword_blank is False]
    return _check("blank_line_after_keyword", "P0.7", not bad,
                  f"{len(bad)} section keyword(s) not followed by a blank line (LAMMPS discards that line); "
                  f"first: {bad[0]['section'] if bad else ''} (line {bad[0]['line'] if bad else ''})",
                  {"problems": bad})


def p0_8_box_keywords(pf: ParsedFile, cfg) -> CheckResult:
    missing = [k for k in ("xlo xhi", "ylo yhi", "zlo zhi") if pf.header_values(k) is None]
    box_kind = declared(cfg).get("box_kind", "any")
    if box_kind == "triclinic" and pf.header_values("xy xz yz") is None:
        missing.append("xy xz yz (declared box_kind: triclinic)")
    if box_kind == "orthogonal" and pf.header_values("xy xz yz") is not None:
        missing.append("unexpected 'xy xz yz' line (declared box_kind: orthogonal)")
    return _check("explicit_box_keywords", "P0.8", not missing,
                  f"box keyword problem: {', '.join(missing)} (LAMMPS silently defaults lo/hi to -0.5/0.5)",
                  {"missing": missing, "box_kind": box_kind})


def p0_9_order(pf: ParsedFile, cfg) -> CheckResult:
    names = pf.section_names()
    atoms_at = names.index("Atoms") if "Atoms" in names else None
    bad = []
    for i, n in enumerate(names):
        if n in ("Bonds", "Angles", "Dihedrals", "Impropers", "Velocities"):
            if atoms_at is None or i < atoms_at:
                bad.append(n)
    return _check("section_order", "P0.9", not bad,
                  f"section(s) {bad} appear before Atoms (LAMMPS: 'Must read Atoms before ...')",
                  {"order": names})


def p0_10_header_unique(pf: ParsedFile, cfg) -> CheckResult:
    seen: Dict[str, List[int]] = {}
    for e in pf.header:
        seen.setdefault(e.key, []).append(e.lineno)
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    return _check("header_keyword_unique", "P0.10", not dups,
                  f"header keyword(s) repeated: {', '.join(f'{k!r} at lines {v}' for k, v in dups.items())} "
                  f"(LAMMPS silently keeps the last value)", {"duplicates": dups})


def p0_11_surplus(pf: ParsedFile, cfg) -> CheckResult:
    problems = []
    for s in pf.sections:
        n = pf.expected_rows(s.name) if s.recognised else None
        if n is None:
            continue
        rows = [r for r in s.rows]
        inner = [g for g in s.gaps if g.rows_before < min(n, len(rows))]
        for g in inner:
            problems.append({"section": s.name, "line": g.lineno,
                             "reason": f"{g.kind} line inside the first {n} rows (consumes one of the N slots LAMMPS reads)"})
        if len(rows) > n:
            surplus = [r.lineno for r in rows[n:]]
            problems.append({"section": s.name, "line": surplus[0],
                             "reason": f"{len(surplus)} row(s) beyond the {n} declared by the header",
                             "surplus_lines": _examples(surplus)})
    return _check("no_surplus_rows", "P0.11", not problems,
                  f"{len(problems)} section(s) with surplus or interleaved content; first: {problems[0]['section'] if problems else ''} "
                  f"line {problems[0]['line'] if problems else ''}: {problems[0]['reason'] if problems else ''}",
                  {"problems": _examples(problems)})


def p0_12_encoding(pf: ParsedFile, cfg) -> CheckResult:
    policy = declared(cfg).get("encoding_policy", "ascii_lf")
    problems = []
    if pf.raw.startswith(b"\xef\xbb\xbf"):
        problems.append("byte-order mark at start of file")
    nul = pf.raw.find(b"\x00")
    if nul >= 0:
        problems.append(f"NUL byte at offset {nul}")
    for i, ln in enumerate(pf.lines):
        bad = [j for j, ch in enumerate(ln) if ord(ch) > 127]
        if bad:
            hash_at = ln.find("#")
            if hash_at < 0 or bad[0] < hash_at:
                problems.append(f"non-ASCII character outside a comment on line {i + 1}")
                break
    terms = set(t for t in pf.terminators if t)
    if pf.terminators and pf.terminators[-1] == "" and pf.lines[-1] != "":
        problems.append("final line is not terminated by a newline")
    if len(terms) > 1:
        problems.append("mixed LF and CRLF line endings")
    elif "\r\n" in terms and policy == "ascii_lf":
        problems.append("CRLF line endings (declared encoding_policy: ascii_lf)")
    return _check("encoding_line_endings", "P0.12", not problems, "; ".join(problems),
                  {"policy": policy, "problems": problems})


TIER0_CHECKS = [p0_1_header, p0_2_sections, p0_3_numeric, p0_4_atoms_columns, p0_5_box,
                p0_6_line_length, p0_7_blank_after_keyword, p0_8_box_keywords, p0_9_order,
                p0_10_header_unique, p0_11_surplus, p0_12_encoding]


def run_tier0(pf: ParsedFile, cfg) -> List[CheckResult]:
    return [fn(pf, cfg) for fn in TIER0_CHECKS]

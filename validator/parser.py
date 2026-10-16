"""Own LAMMPS DATA FILE parser (PROPERTIES §8.7). Never raises on a malformed file.

The parser only records *what is in the file* — header entries, section keywords, rows, blank and
comment lines, with 1-based line numbers. Every verdict is made later by the tier modules.
It deliberately does not use ASE or pymatgen (SPEC §7.1: the validator must not share failure
modes with the converters it checks).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------------------------
# Vocabulary (LAMMPS read_data.cpp:61-71, tag stable_22Jul2025_update6)
# ----------------------------------------------------------------------------------------------
HEADER_INT_KEYWORDS = [
    "atoms", "bonds", "angles", "dihedrals", "impropers",
    "atom types", "bond types", "angle types", "dihedral types", "improper types",
    "extra bond per atom", "extra angle per atom", "extra dihedral per atom",
    "extra improper per atom", "extra special per atom",
    "ellipsoids", "lines", "triangles", "bodies",
]
HEADER_FLOAT_KEYWORDS = {
    "xlo xhi": 2, "ylo yhi": 2, "zlo zhi": 2, "xy xz yz": 3,
    "avec": 3, "bvec": 3, "cvec": 3, "abc origin": 3,
}
# Header keywords that are recognised by LAMMPS but outside project scope (SPEC §7.4).
HEADER_UNSUPPORTED = {"ellipsoids", "lines", "triangles", "bodies", "avec", "bvec", "cvec", "abc origin"}

SECTION_TOPOLOGY = ["Bonds", "Angles", "Dihedrals", "Impropers"]
SECTION_COEFF_CLASS1 = ["Pair Coeffs", "PairIJ Coeffs", "Bond Coeffs", "Angle Coeffs",
                        "Dihedral Coeffs", "Improper Coeffs"]
SECTION_COEFF_CLASS2 = ["BondBond Coeffs", "BondAngle Coeffs", "MiddleBondTorsion Coeffs",
                        "EndBondTorsion Coeffs", "AngleTorsion Coeffs", "AngleAngleTorsion Coeffs",
                        "BondBond13 Coeffs", "AngleAngle Coeffs"]
SECTION_TYPE_LABELS = ["Atom Type Labels", "Bond Type Labels", "Angle Type Labels",
                       "Dihedral Type Labels", "Improper Type Labels"]
SECTION_BODY_STYLES = ["Ellipsoids", "Lines", "Triangles", "Bodies"]
SECTIONS_ALL = (["Atoms", "Velocities", "Masses"] + SECTION_TOPOLOGY + SECTION_COEFF_CLASS1
                + SECTION_COEFF_CLASS2 + SECTION_TYPE_LABELS + SECTION_BODY_STYLES)
SECTIONS_COEFF = SECTION_COEFF_CLASS1 + SECTION_COEFF_CLASS2

# How many rows a section must have: header keyword (or a function of it).
SECTION_COUNT_KEY = {
    "Atoms": "atoms", "Velocities": "atoms",
    "Bonds": "bonds", "Angles": "angles", "Dihedrals": "dihedrals", "Impropers": "impropers",
    "Masses": "atom types", "Pair Coeffs": "atom types", "PairIJ Coeffs": "atom types*",
    "Bond Coeffs": "bond types",
    "Angle Coeffs": "angle types", "BondBond Coeffs": "angle types", "BondAngle Coeffs": "angle types",
    "Dihedral Coeffs": "dihedral types", "MiddleBondTorsion Coeffs": "dihedral types",
    "EndBondTorsion Coeffs": "dihedral types", "AngleTorsion Coeffs": "dihedral types",
    "AngleAngleTorsion Coeffs": "dihedral types", "BondBond13 Coeffs": "dihedral types",
    "Improper Coeffs": "improper types", "AngleAngle Coeffs": "improper types",
}

# Atoms columns per atom_style (RD; SRC fields_data_atom). k = columns without image flags.
ATOM_STYLE_COLUMNS: Dict[str, List[str]] = {
    "atomic":    ["id", "type", "x", "y", "z"],
    "charge":    ["id", "type", "q", "x", "y", "z"],
    "bond":      ["id", "mol", "type", "x", "y", "z"],
    "angle":     ["id", "mol", "type", "x", "y", "z"],
    "molecular": ["id", "mol", "type", "x", "y", "z"],
    "full":      ["id", "mol", "type", "q", "x", "y", "z"],
}
INT_COLUMNS = {"id", "mol", "type", "ix", "iy", "iz"}

INT_RE = re.compile(r"^[+-]?\d+$")
UINT_RE = re.compile(r"^\d+$")
# LAMMPS utils::is_double grammar (utils.cpp:1697-1716): no nan/inf, no Fortran D exponents.
FLOAT_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
UNITS_HINT_RE = re.compile(r"units\s*=\s*(\S+)")


def is_int(tok: str) -> bool:
    return bool(INT_RE.match(tok))


def is_float(tok: str) -> bool:
    if not FLOAT_RE.match(tok):
        return False
    try:
        v = float(tok)
    except ValueError:
        return False
    return v == v and v not in (float("inf"), float("-inf"))


def decimals(tok: str) -> int:
    """Number of digits after the decimal point in a float token (0 if none)."""
    mant = re.split(r"[eE]", tok)[0]
    if "." not in mant:
        return 0
    return len(mant.split(".", 1)[1])


# ----------------------------------------------------------------------------------------------
# Parsed structures
# ----------------------------------------------------------------------------------------------
@dataclass
class HeaderEntry:
    key: str
    values: List[str]
    lineno: int
    raw: str


@dataclass
class HeaderIssue:
    lineno: int
    raw: str
    reason: str


@dataclass
class Row:
    lineno: int
    tokens: List[str]
    comment: Optional[str] = None
    after_keyword: bool = False   # row sat on the line LAMMPS always discards (P0.7)


@dataclass
class Gap:
    lineno: int
    kind: str            # "blank" | "comment"
    rows_before: int     # number of data rows already seen in the section


@dataclass
class Section:
    name: str
    lineno: int
    style_comment: Optional[str]
    recognised: bool
    raw_keyword: str
    line_after_keyword_blank: Optional[bool]   # None: keyword was the last line of the file
    rows: List[Row] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)


@dataclass
class ParsedFile:
    path: str
    raw: bytes
    sha256: str
    text: str
    lines: List[str]                 # without terminators
    terminators: List[str]           # "\n", "\r\n", "" (last line unterminated) per line
    first_line: str
    units_hint: Optional[str]
    header: List[HeaderEntry] = field(default_factory=list)
    header_issues: List[HeaderIssue] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    decode_error: Optional[str] = None

    # --- convenience ---------------------------------------------------------------------
    def header_values(self, key: str) -> Optional[List[str]]:
        """Last value for a header key (LAMMPS: last occurrence wins)."""
        vals = None
        for e in self.header:
            if e.key == key:
                vals = e.values
        return vals

    def header_int(self, key: str, default: Optional[int] = 0) -> Optional[int]:
        v = self.header_values(key)
        if v is None:
            return default
        try:
            return int(v[0])
        except (ValueError, IndexError):
            return default

    def header_floats(self, key: str) -> Optional[List[float]]:
        v = self.header_values(key)
        if v is None:
            return None
        try:
            return [float(x) for x in v]
        except ValueError:
            return None

    def section(self, name: str) -> Optional[Section]:
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def section_names(self) -> List[str]:
        return [s.name for s in self.sections]

    def expected_rows(self, name: str) -> Optional[int]:
        key = SECTION_COUNT_KEY.get(name)
        if key is None:
            return None
        if key == "atom types*":
            n = self.header_int("atom types", 0) or 0
            return n * (n + 1) // 2
        return self.header_int(key, 0) or 0


# ----------------------------------------------------------------------------------------------
# Header matching
# ----------------------------------------------------------------------------------------------
def _header_patterns():
    pats = []
    for kw in HEADER_INT_KEYWORDS:
        words = kw.split()
        pats.append((kw, 1, words))
    for kw, n in HEADER_FLOAT_KEYWORDS.items():
        pats.append((kw, n, kw.split()))
    # Longest keyword first so "atom types" is tried before "atoms" is impossible to confuse.
    pats.sort(key=lambda p: -len(p[2]))
    return pats


_HEADER_PATTERNS = _header_patterns()


def match_header(content: str) -> Tuple[Optional[str], Optional[List[str]], Optional[str]]:
    """Match one comment-stripped header line.

    Returns (key, values, problem). key is None if the line is not a header line at all.
    problem is set when the keyword is recognised but something else on the line is wrong
    (trailing content). Value syntax is checked later (P0.3).
    """
    toks = content.split()
    for key, nvals, words in _HEADER_PATTERNS:
        if len(toks) < nvals + len(words):
            continue
        if toks[nvals:nvals + len(words)] == words:
            extra = toks[nvals + len(words):]
            problem = f"unexpected trailing content {' '.join(extra)!r}" if extra else None
            return key, toks[:nvals], problem
    return None, None, None


def _strip_header_comment(line: str) -> Tuple[str, Optional[str]]:
    """Cut at the first '#'. Returns (content, problem) where problem flags a '#' with no blank before it."""
    idx = line.find("#")
    if idx < 0:
        return line, None
    problem = None
    if idx > 0 and not line[idx - 1].isspace():
        problem = "comment '#' not preceded by whitespace (project rule P0.1; LAMMPS also cuts here)"
    return line[:idx], problem


def _keyword_parts(line: str) -> Tuple[str, Optional[str]]:
    """Section keyword line: cut at '#'; remainder is the style comment (§8.7 rule 4)."""
    idx = line.find("#")
    if idx < 0:
        return line.strip(), None
    return line[:idx].strip(), line[idx + 1:].strip() or None


def _looks_like_keyword(stripped: str) -> bool:
    return bool(stripped) and stripped[0].isalpha()


def _split_row(line: str, coeff: bool) -> Tuple[List[str], Optional[str]]:
    if coeff:
        idx = line.find("#")      # §8.7 rule 6: Coeff rows are cut at the first '#' anywhere
        if idx >= 0:
            return line[:idx].split(), line[idx + 1:].strip()
        return line.split(), None
    toks = line.split()           # §8.7 rule 5: a token that *starts* with '#' begins a comment
    for i, t in enumerate(toks):
        if t.startswith("#"):
            return toks[:i], " ".join(toks[i:])[1:].strip()
    return toks, None


# ----------------------------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------------------------
def split_lines(text: str) -> Tuple[List[str], List[str]]:
    lines, terms = [], []
    pos = 0
    n = len(text)
    while pos < n:
        j = text.find("\n", pos)
        if j < 0:
            lines.append(text[pos:])
            terms.append("")
            break
        seg = text[pos:j]
        if seg.endswith("\r"):
            lines.append(seg[:-1])
            terms.append("\r\n")
        else:
            lines.append(seg)
            terms.append("\n")
        pos = j + 1
    return lines, terms


def parse_bytes(raw: bytes, path: str = "<memory>") -> ParsedFile:
    sha = hashlib.sha256(raw).hexdigest()
    decode_error = None
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as e:
        decode_error = f"non-ASCII byte at offset {e.start}"
        text = raw.decode("latin-1")
    if text.startswith("﻿") or raw.startswith(b"\xef\xbb\xbf"):
        decode_error = decode_error or "byte-order mark at start of file"
    lines, terms = split_lines(text)
    first = lines[0] if lines else ""
    m = UNITS_HINT_RE.search(first)
    pf = ParsedFile(path=path, raw=raw, sha256=sha, text=text, lines=lines, terminators=terms,
                    first_line=first, units_hint=m.group(1) if m else None, decode_error=decode_error)

    # ---- header: line 1 is skipped unconditionally (RD) -----------------------------------
    i = 1
    n = len(lines)
    while i < n:
        line = lines[i]
        content, cproblem = _strip_header_comment(line)
        stripped = content.strip()
        if not stripped:
            if cproblem and line.strip() and not line.strip().startswith("#"):
                pf.header_issues.append(HeaderIssue(i + 1, line, cproblem))
            i += 1
            continue
        key, vals, problem = match_header(content)
        if key is not None:
            pf.header.append(HeaderEntry(key, vals, i + 1, line))
            if problem:
                pf.header_issues.append(HeaderIssue(i + 1, line, problem))
            if cproblem:
                pf.header_issues.append(HeaderIssue(i + 1, line, cproblem))
            i += 1
            continue
        if _looks_like_keyword(line.strip()):
            break                 # end of header: must be a section keyword (checked by P0.1/P0.2)
        pf.header_issues.append(HeaderIssue(i + 1, line, "line matches no recognised header keyword"))
        i += 1

    # ---- body ------------------------------------------------------------------------------
    cur: Optional[Section] = None
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            if cur is not None:
                cur.gaps.append(Gap(i + 1, "blank", len(cur.rows)))
            i += 1
            continue
        if stripped.startswith("#"):
            if cur is not None:
                cur.gaps.append(Gap(i + 1, "comment", len(cur.rows)))
            i += 1
            continue
        if _looks_like_keyword(stripped):
            name, style = _keyword_parts(line)
            cur = Section(name=name, lineno=i + 1, style_comment=style, recognised=name in SECTIONS_ALL,
                          raw_keyword=line, line_after_keyword_blank=None)
            pf.sections.append(cur)
            # LAMMPS always consumes the next line (read_data.cpp:2509).
            if i + 1 < n:
                nxt = lines[i + 1]
                if not nxt.strip():
                    cur.line_after_keyword_blank = True
                    i += 2
                    continue
                cur.line_after_keyword_blank = False
                if _looks_like_keyword(nxt.strip()):
                    i += 1            # let the next keyword start its own section
                    continue
                if nxt.strip().startswith("#"):
                    cur.gaps.append(Gap(i + 2, "comment", 0))
                else:
                    toks, com = _split_row(nxt, name in SECTIONS_COEFF)
                    cur.rows.append(Row(i + 2, toks, com, after_keyword=True))
                i += 2
                continue
            i += 1
            continue
        if cur is None:          # unreachable: header loop stops only at keyword-like lines
            i += 1
            continue
        toks, com = _split_row(line, cur.name in SECTIONS_COEFF)
        if not toks:             # row that is only a comment token sequence
            cur.gaps.append(Gap(i + 1, "comment", len(cur.rows)))
        else:
            cur.rows.append(Row(i + 1, toks, com))
        i += 1
    return pf


def parse_file(path: str) -> ParsedFile:
    with open(path, "rb") as fh:
        raw = fh.read()
    return parse_bytes(raw, path=str(path))

"""Minimal text-level editor for LAMMPS DATA FILEs, used by the corruption operators and the
fixture builders.

Deliberately independent of validator/parser.py: a negative control must not be built with the
same code it is meant to test. It edits lines in place, so every untouched line is byte-identical
to the parent file.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

KEYWORD_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9]*(?: [A-Z][A-Za-z0-9]*)*)\s*(#.*)?$")


class DataText:
    def __init__(self, text: str):
        self.trailing_newline = text.endswith("\n")
        self.lines: List[str] = text.split("\n")
        if self.trailing_newline:
            self.lines.pop()

    @classmethod
    def read(cls, path: str) -> "DataText":
        with open(path) as fh:
            return cls(fh.read())

    def text(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.trailing_newline else "")

    def write(self, path: str) -> None:
        with open(path, "w", newline="") as fh:
            fh.write(self.text())

    # -- header --------------------------------------------------------------------------------
    def header_index(self, keyword: str) -> Optional[int]:
        pat = re.compile(r"^\s*(\S+\s+){1,3}" + r"\s+".join(map(re.escape, keyword.split())) + r"\s*(#.*)?$")
        for i, ln in enumerate(self.lines[1:], start=1):
            if KEYWORD_RE.match(ln) and not ln.strip()[0].isdigit() and not ln.strip()[0] in "+-.":
                return None          # reached the body
            if pat.match(ln):
                return i
        return None

    def header_values(self, keyword: str) -> List[str]:
        i = self.header_index(keyword)
        if i is None:
            raise KeyError(keyword)
        n = len(self.lines[i].split("#")[0].split()) - len(keyword.split())
        return self.lines[i].split()[:n]

    def set_header(self, keyword: str, values) -> None:
        i = self.header_index(keyword)
        vals = " ".join(str(v) for v in values)
        if i is None:
            raise KeyError(keyword)
        self.lines[i] = f"  {vals}  {keyword}"

    def header_int(self, keyword: str) -> int:
        return int(self.header_values(keyword)[0])

    # -- sections ------------------------------------------------------------------------------
    def section_index(self, name: str) -> Optional[int]:
        for i, ln in enumerate(self.lines):
            m = KEYWORD_RE.match(ln)
            if m and m.group(1) == name:
                return i
        return None

    def section_rows(self, name: str) -> List[Tuple[int, str]]:
        """(line index, text) of the data rows of a section: from keyword+2 to the next blank line."""
        k = self.section_index(name)
        if k is None:
            return []
        out = []
        i = k + 2
        while i < len(self.lines) and self.lines[i].strip():
            out.append((i, self.lines[i]))
            i += 1
        return out

    def section_names(self) -> List[str]:
        out = []
        for ln in self.lines:
            m = KEYWORD_RE.match(ln)
            if m and ln.strip() and ln.strip()[0].isalpha() and ln.strip() != "LAMMPS":
                out.append(m.group(1))
        return out

    def insert_lines(self, index: int, new: List[str]) -> None:
        self.lines[index:index] = new

    def delete_line(self, index: int) -> str:
        return self.lines.pop(index)

    def append_section(self, name: str, rows: List[str]) -> None:
        if self.lines and self.lines[-1].strip():
            self.lines.append("")
        self.lines += [name, ""] + rows


def split_comment(line: str) -> Tuple[List[str], str]:
    """Data tokens and the trailing comment (including '#'), as LAMMPS tokenises data rows."""
    toks = line.split()
    for i, t in enumerate(toks):
        if t.startswith("#"):
            return toks[:i], " ".join(toks[i:])
    return toks, ""


def join_row(tokens: List[str], comment: str = "") -> str:
    s = "  ".join(tokens)
    return f"  {s}  {comment}".rstrip() if comment else f"  {s}"

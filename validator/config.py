"""Configuration loading.

Two layers, merged in this order (later wins):
  1. project config  (config.yaml at the repo root: LAMMPS executable, backend, paths)
  2. declared validation configuration record (configs/*.yaml, SPEC §7.10)
  3. per-file overrides (e.g. the coefficient file belonging to one reference)
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_yaml(path: Path) -> Dict[str, Any]:
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def resolve(path: Optional[str], base: Path = REPO_ROOT) -> Optional[str]:
    if path is None:
        return None
    p = Path(os.path.expanduser(str(path)))
    return str(p if p.is_absolute() else (base / p).resolve())


def load_config(declared: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None,
                project: Optional[str] = None) -> Dict[str, Any]:
    proj_path = Path(project) if project else REPO_ROOT / "config.yaml"
    cfg = _read_yaml(proj_path) if proj_path.exists() else {}
    decl_name = declared or cfg.get("validator", {}).get("default_declared_config")
    if decl_name:
        decl_path = Path(resolve(decl_name))
        cfg = deep_merge(cfg, {"declared": _read_yaml(decl_path)})
        cfg["declared"]["_path"] = str(decl_path)
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return cfg


def declared(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return cfg.get("declared", {})


def periodic_flags(cfg: Dict[str, Any]):
    b = declared(cfg).get("boundary", ["p", "p", "p"])
    if isinstance(b, str):
        b = b.split()
    return tuple(x == "p" for x in b)


def load_calibration(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    import json
    path = declared(cfg).get("calibration")
    if not path:
        return None
    p = resolve(path)
    if not p or not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


_FRC_ELEMENTS: Dict[str, Dict[str, str]] = {}


def _frc_elements(path: str) -> Dict[str, str]:
    """Type -> element from the #atom_types section of a Materials Studio .frc file.

    Read directly (the validator does not import the builders): the .frc is the declared, cited
    force-field source, not a converter under test."""
    if path not in _FRC_ELEMENTS:
        out, section = {}, None
        with open(path, errors="replace") as fh:
            for line in fh:
                if line.startswith("#"):
                    section = line.split()[0]
                    continue
                t = line.split()
                if section == "#atom_types" and len(t) >= 5 and t[0][:1].isdigit():
                    el = t[4]
                    out.setdefault(t[2], el[:1].upper() + el[1:].lower())
        _FRC_ELEMENTS[path] = out
    return _FRC_ELEMENTS[path]


def element_table(cfg: Dict[str, Any]) -> Dict[str, str]:
    """Type-name -> element map (OD-J): the declared .frc element column (type_name_elements_frc),
    overridden by any explicit type_name_elements entries."""
    d = declared(cfg)
    table: Dict[str, str] = {}
    frc = d.get("type_name_elements_frc")
    if frc:
        table.update(_frc_elements(resolve(frc)))
    table.update(d.get("type_name_elements") or {})
    return table

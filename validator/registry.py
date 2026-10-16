"""Sidecar metadata: which declared configuration and per-file overrides apply to a DATA FILE.

Every reference (data/reference/REF-xx.json), fixture (data/fixtures/FIX-xx.json) and corrupted
variant (data/corrupted/<REF>__<FM>__<variant>.json, FAILURE_MODES §9.4) has a JSON sidecar:
  {"id": ..., "declared_config": "configs/....yaml", "overrides": {...declared keys...}, ...}
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from .config import REPO_ROOT, load_config


def sidecar_path(data_path: str) -> str:
    base, _ = os.path.splitext(data_path)
    return base + ".json"


def load_sidecar(data_path: str) -> Optional[Dict[str, Any]]:
    p = sidecar_path(data_path)
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        return json.load(fh)


def config_for(data_path: str, sidecar: Optional[Dict[str, Any]] = None, **project_overrides) -> Dict[str, Any]:
    meta = sidecar if sidecar is not None else load_sidecar(data_path)
    if meta is None:
        return load_config(overrides=project_overrides or None)
    over = {"declared": meta.get("overrides", {})}
    if project_overrides:
        over.update(project_overrides)
    return load_config(declared=meta.get("declared_config"), overrides=over)


def reference_for(data_path: str, sidecar: Optional[Dict[str, Any]] = None) -> Optional[str]:
    meta = sidecar if sidecar is not None else load_sidecar(data_path)
    if not meta or not meta.get("parent_file"):
        return None
    return str((REPO_ROOT / meta["parent_file"]).resolve())

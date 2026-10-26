"""Freeze the dev/test split of eval set v2 (plan Day 20).

Rule: stratify tasks by (domain, difficulty); from each stratum draw round(n/3) tasks, at least one, for
the test split with a fixed seed; redraw (next seed) until the test split contains both force fields.
Writes eval/split.json and prints its SHA-256 for LOG.md. Run once; the test split is not opened before
16 Nov (METRICS.md §6).

--extend (eval set v3, 2026-10-26): keep every existing dev/test assignment; draw only the tasks not yet in
the split, by the same rule applied to their own strata (and both force fields among the new test tasks).
"""
from __future__ import annotations

import datetime as _dt
import glob
import hashlib
import json
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 20261022


def main(extend=False):
    tasks = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(ROOT, "eval", "tasks", "*.json")))]
    path = os.path.join(ROOT, "eval", "split.json")
    old = json.load(open(path)) if extend else None
    kept = set(old["dev"]) | set(old["test"]) if old else set()
    strata = defaultdict(list)
    for t in tasks:
        if t["id"] not in kept:
            strata[(t["domain"], t["difficulty"])].append(t["id"])
    seed = SEED
    while True:
        rng = np.random.default_rng(seed)
        test = []
        for key in sorted(strata):
            ids = sorted(strata[key])
            k = max(1, int(round(len(ids) / 3)))
            test += sorted(rng.choice(ids, size=k, replace=False).tolist())
        ffs = {t["force_field"] for t in tasks if t["id"] in test}
        if ffs == {"pcff", "cvff"}:
            break
        seed += 1
    rule = "stratified by (domain, difficulty); round(n/3), min 1, per stratum to test; both force fields in test"
    if old:
        test += old["test"]
        prev = hashlib.sha256(open(path, "rb").read()).hexdigest()
    dev = sorted(t["id"] for t in tasks if t["id"] not in test)
    split = {"version": old["version"] + 1 if old else 1, "created": old["created"] if old else _dt.date.today().isoformat(),
             "seed": old["seed"] if old else seed, "rule": rule,
             "dev": dev, "test": sorted(test),
             "tasks_sha256": {t["id"]: hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest() for t in tasks}}
    if old:
        split["extended"] = {"date": _dt.date.today().isoformat(), "seed": seed, "new_tasks": sorted(sum(strata.values(), [])),
                             "supersedes_sha256": prev,
                             "rule": "existing assignments kept; new tasks drawn by the same rule within their own strata"}
    with open(path, "w") as fh:
        json.dump(split, fh, indent=2)
    print("dev:", dev)
    print("test:", sorted(test))
    print("split.json sha256:", hashlib.sha256(open(path, "rb").read()).hexdigest())


if __name__ == "__main__":
    main(extend="--extend" in sys.argv)

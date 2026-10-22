"""Freeze the dev/test split of eval set v2 (plan Day 20).

Rule: stratify tasks by (domain, difficulty); from each stratum draw round(n/3) tasks, at least one, for
the test split with a fixed seed; redraw (next seed) until the test split contains both force fields.
Writes eval/split.json and prints its SHA-256 for LOG.md. Run once; the test split is not opened before
16 Nov (METRICS.md §6).
"""
from __future__ import annotations

import datetime as _dt
import glob
import hashlib
import json
import os
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 20261022


def main():
    tasks = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(ROOT, "eval", "tasks", "*.json")))]
    strata = defaultdict(list)
    for t in tasks:
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
    dev = sorted(t["id"] for t in tasks if t["id"] not in test)
    split = {"version": 1, "created": _dt.date.today().isoformat(), "seed": seed,
             "rule": "stratified by (domain, difficulty); round(n/3), min 1, per stratum to test; both force fields in test",
             "dev": dev, "test": sorted(test),
             "tasks_sha256": {t["id"]: hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest() for t in tasks}}
    path = os.path.join(ROOT, "eval", "split.json")
    with open(path, "w") as fh:
        json.dump(split, fh, indent=2)
    print("dev:", dev)
    print("test:", sorted(test))
    print("split.json sha256:", hashlib.sha256(open(path, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()

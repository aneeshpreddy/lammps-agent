"""Variant E (optional, off by default): two checks against "valid but not the requested system".

The validator in the loop catches invalid files, not wrong ones (docs/AGENT.md, Known limitation). Variant E
adds, without ever seeing the task's reference:

  build summary   build_data_file also returns one plain sentence saying what was built (domain, force field,
                  model and supercell; per-chain backbone, side chains, EO lengths, anchors, counter-ions;
                  surface, height). Deterministic, no model.
  request check   once per task, a separate model call reads ONLY the request and lists what it states
                  explicitly (REQ_SCHEMA, every field null when not stated). After each attempt, plain code
                  compares that list with what was built (compare()); a mismatch is fed back like a failing
                  check. Each (field, built value) is raised once: if the agent rebuilds it unchanged, the
                  agent's reading wins, so an extraction error cannot force an escalation.

Both are decided on dev data only and reported as ablation E (= C + these checks).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from eval.analyse import canonical, chem_name  # noqa: E402

CHECKS_VERSION = "checks-v1 (2026-10-28)"
ANCHORS = ["methacrylate ester (MPEG)", "acrylate ester", "APEG", "HPEG", "TPEG", "VPEG"]

_N = {"type": "null"}


def _opt(s):
    return {"anyOf": [s, _N]}


REQ_FIELDS = {
    "system": _opt({"type": "string", "enum": ["mineral", "pce", "composite"]}),
    "force_field": _opt({"type": "string", "enum": ["pcff", "cvff"]}),
    "supercell": _opt({"type": "array", "items": {"type": "integer"}}),
    "n_chains": _opt({"type": "integer"}),
    "backbone_units_per_chain": _opt({"type": "integer"}),
    "side_chains_per_chain": _opt({"type": "integer"}),
    "acid_units_per_chain": _opt({"type": "integer"}),
    "eo_units": _opt({"type": "array", "items": {"type": "integer"}}),
    "anchor": _opt({"type": "string", "enum": ANCHORS}),
    "counterion": _opt({"type": "string", "enum": ["Ca2+", "Na+", "K+", "none"]}),
    "sequence": _opt({"type": "string", "enum": ["random", "alternating", "block", "gradient", "explicit"]}),
    "height_A": _opt({"type": "number"}),
    "orientation": _opt({"type": "string", "enum": ["flat", "as_built"]}),
}
REQ_SCHEMA = {"type": "object", "properties": REQ_FIELDS, "required": list(REQ_FIELDS), "additionalProperties": False}

REQ_PROMPT = """You read a request for a molecular model and list what it states explicitly, as JSON in the output schema.
Use null for anything the request does not state. Do not infer, do not fill in defaults, do not choose.

- system: "mineral" (a cement-mineral crystal or supercell), "pce" (a polycarboxylate superplasticiser on its own) or "composite" (a PCE on a mineral surface).
- force_field: "pcff" for PCFF-INTERFACE (class II), "cvff" for CVFF-INTERFACE (class I).
- supercell: replications [a, b, c] of the mineral or surface cell, when stated as numbers.
- n_chains: number of PCE chains. backbone_units_per_chain: monomer units in each main chain (the backbone length).
- side_chains_per_chain: PEG side chains (macromonomer units) per chain. acid_units_per_chain: acid units per chain (acrylic, methacrylic or maleic).
- eo_units: ethylene-oxide units of each distinct side-chain length stated, e.g. [22] or [10, 45].
- anchor: how the side chains attach. methacrylate ester (MPEG), acrylate ester, APEG (allyl ether), HPEG (methallyl ether), TPEG (isoprenyl ether), VPEG (vinyl / butenyl ether).
- counterion: the ion that neutralises the carboxylates, or "none" if the request says the system stays charged.
- sequence: "random", "alternating", "block", "gradient", or "explicit" when the request gives the order unit by unit.
- height_A: distance of the PCE above the surface in Å. orientation: "flat" if laid flat on the surface, "as_built" if kept as built."""

LABELS = {"system": "domain", "force_field": "force field", "supercell": "supercell", "n_chains": "chains",
          "backbone_units_per_chain": "backbone units per chain", "side_chains_per_chain": "side chains per chain",
          "acid_units_per_chain": "acid units per chain", "eo_units": "EO units per side chain",
          "anchor": "side-chain anchor", "counterion": "counter-ion", "sequence": "sequence",
          "height_A": "height above the surface (Å)", "orientation": "orientation"}


# ---------------------------------------------------------------------------------------------
def _anchor(c: tuple):
    k, am, _eo, _end, spacer, _dep = c
    if k == "ester_peg":
        return ANCHORS[0] if am else ANCHORS[1]
    if k == "ether_peg":
        return {(False, 1): "APEG", (True, 1): "HPEG", (True, 2): "TPEG", (False, 2): "VPEG"}.get((am, spacer))
    return None


def built_values(spec: dict, details: dict = None) -> dict:
    """The REQ_FIELDS values of a build (builder spec + the builder's record for a resolved "auto" supercell)."""
    c = canonical(spec)
    b = spec["builder"]
    out = {"system": {"minerals": "mineral"}.get(b, b), "force_field": spec["force_field"]}
    if b == "minerals":
        out["supercell"] = list(c["supercell"])
        return out
    pre = "pce." if b == "composite" else ""
    units = c[pre + "units"]
    side = {u: n for u, n in units.items() if u[0] in ("ester_peg", "ether_peg")}
    seq = c[pre + "sequence"]
    out.update({"n_chains": c[pre + "n_chains"], "backbone_units_per_chain": sum(units.values()),
                "side_chains_per_chain": sum(side.values()),
                "acid_units_per_chain": sum(n for u, n in units.items() if u[0] in ("acid", "diacid")),
                "eo_units": sorted({u[2] for u in side}), "anchor": sorted({_anchor(u) for u in side}),
                "counterion": c[pre + "counterion"] or "none",
                "sequence": "explicit" if isinstance(seq, list) else seq})
    if b == "composite":
        sc = c["surface.supercell"]
        if sc == "auto":
            sc = (details or {}).get("supercell") or "auto"
        out.update(supercell=sc if sc == "auto" else list(sc), height_A=c["height"], orientation=c["orientation"])
    return out


def compare(req: dict, built: dict) -> list:
    """[(field, stated, built)] for every field the request states and the build does not match."""
    out = []
    if req.get("system") and req["system"] != built["system"]:
        return [("system", req["system"], built["system"])]       # nothing else is comparable
    for f, want in req.items():
        if want is None or f == "system":
            continue
        have = built.get(f)
        if f == "anchor":
            ok = have == [want]
        elif f == "eo_units":
            ok = sorted(set(want)) == have
        elif f == "height_A":
            ok = have is not None and abs(float(have) - float(want)) <= 0.05
        elif f == "supercell":
            ok = have == "auto" or have == list(want)
        else:
            ok = have == want
        if not ok:
            out.append((f, want, have))
    return out


def mismatch_lines(mism: list) -> list:
    return [f"- {LABELS[f]}: the request says {json.dumps(want)}, the build has {json.dumps(have)}" for f, want, have in mism]


# ---------------------------------------------------------------------------------------------
def describe_build(spec: dict, facts: dict, details: dict = None) -> str:
    """One plain sentence about what was built (option 2)."""
    ff = {"pcff": "PCFF-INTERFACE", "cvff": "CVFF-INTERFACE"}[spec["force_field"]]
    tail = (f"{facts['atoms']} atoms, net charge {facts['net_charge_e']:+g} e, box "
            + " x ".join(f"{x:.1f}" for x in facts["box_A"]["lengths"]) + " Å")
    if spec["builder"] == "minerals":
        sc = "x".join(map(str, spec["supercell"]))
        return f"Built: mineral {spec['model']} ({ff}), supercell {sc}; {tail}."
    b = built_values(spec, details)
    c = canonical(spec)
    pre = "pce." if spec["builder"] == "composite" else ""
    units = ", ".join(f"{chem_name(u)} x{n}" for u, n in sorted(c[pre + "units"].items(), key=lambda x: -x[1]))
    pce = (f"PCE ({ff}), {b['n_chains']} chain(s), each {b['backbone_units_per_chain']} backbone units "
           f"[{units}], {b['side_chains_per_chain']} side chain(s), sequence {b['sequence']}, "
           f"counter-ion {b['counterion']}")
    if spec["builder"] == "pce":
        return f"Built: {pce}; {tail}."
    sc = b["supercell"] if b["supercell"] == "auto" else "x".join(map(str, b["supercell"]))
    return (f"Built: {pce}, on surface {spec['surface']['model']} supercell {sc}, {b['height_A']:g} Å above it, "
            f"orientation {b['orientation']}; {tail}.")


# ---------------------------------------------------------------------------------------------
def extract_requirements(client, model: str, effort: str, request: str, max_tokens: int = 4000):
    """One model call that reads only the request -> (requirements | None, usage, trace event data)."""
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=REQ_PROMPT, messages=[{"role": "user", "content": request}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": REQ_SCHEMA}})
    u = resp.usage
    usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
             "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
             "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
    text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
    ev = {"stop_reason": resp.stop_reason, "request_id": getattr(resp, "_request_id", None), "usage": usage,
          "text": text}
    if resp.stop_reason != "end_turn":
        return None, usage, ev
    try:
        return json.loads(text), usage, ev
    except json.JSONDecodeError:
        return None, usage, ev

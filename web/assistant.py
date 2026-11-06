"""AtomForge request assistant and plain-English descriptions (no Streamlit here, so it can be unit-tested).

The assistant is an interface helper, not part of the evaluated v1.0 system. It makes one model call that reads
the user's request and returns the same builder spec as the single-call baseline (agents/baseline.py SCHEMA,
same builder knowledge, imported unchanged), plus where each value came from: stated by the user, inferred
from loose wording, or a documented builder default. The improved prompt is then written by code from that
spec (render_prompt), so the text and the configuration panel cannot disagree. Generation still goes
through the frozen agent with the improved text.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents.baseline import MODEL, SCHEMA, _OBJ, _opt, knowledge, to_builder_spec  # noqa: E402

UGRP = os.path.dirname(ROOT)
CACHE = os.path.join(ROOT, "runs", "assistant")
ASSIST_VERSION = "assistant-v1 (2026-11-06)"

ION = {"Na+": ("Na⁺", 1), "K+": ("K⁺", 1), "Ca2+": ("Ca²⁺", 2)}
FF = {"pcff": "PCFF-INTERFACE", "cvff": "CVFF-INTERFACE"}
ETHER = {(False, 1): "APEG", (True, 1): "HPEG", (True, 2): "TPEG", (False, 2): "VPEG"}
ETHER_LONG = {"APEG": "APEG (allyl ether)", "HPEG": "HPEG (methallyl ether)", "TPEG": "TPEG (isoprenyl ether)",
              "VPEG": "VPEG (4-hydroxybutyl vinyl ether)"}
END = {"OCH3": "methoxy (OCH₃)", "OH": "hydroxyl (OH)"}
SEQ = {"random": "random", "alternating": "alternating", "block": "block", "gradient": "gradient", "explicit": "explicit"}

ASSIST_SCHEMA = _OBJ({                    # flat strings: nested objects next to SCHEMA make the grammar too large
    "buildable": {"type": "boolean"},
    "out_of_scope_reason": {"type": "string"},
    "spec": SCHEMA,                       # ignored when buildable is false
    "parameters": {"type": "array", "items": {"type": "string"}},     # "key | stated|inferred|default | note"
    "ambiguities": {"type": "array", "items": {"type": "string"}},    # "issue | chosen reading | alternative; alternative"
    "missing": {"type": "array", "items": {"type": "string"}},
})

ASSIST_INTRO = """You are the request assistant of a tool that builds LAMMPS DATA FILEs with deterministic builders. \
You read a user's description of a molecular system and interpret it as a builder spec (the "spec" field; its \
fields mean exactly what the documentation below says). You do not build anything, and you never invent chemistry.

Rules:
- Keep every value the user stated exactly. Never change, round or "correct" an explicit value.
- Where the user gave no value, use the documented default below; where the wording is loose ("about 25 %", "maybe", \
"pcff" for PCFF-INTERFACE, "short"), choose the most common reading.
- In "parameters", give one string "key | source | note" for every parameter your spec uses, with these keys: "system", "force_field"; \
for minerals "mineral.model", "mineral.supercell"; for a PCE "n_chains", "sequence", "end_groups", "counterion", \
"box_padding" and, for each monomer label L, "unit.L.count", "unit.L.type", and where they apply "unit.L.eo_units", \
"unit.L.end", "unit.L.deprotonated"; for a composite also "surface.model", "surface.supercell", "height", "orientation". \
source = "stated" only when the user gave that value explicitly; "default" when it is the documented default and the \
user said nothing; "inferred" when you read it from loose or indirect wording. note = a short phrase saying what you \
read or why (for deprotonation and counter-ions, say how the charge is balanced: the builder adds counter-ions to \
neutralise the carboxylates).
- In "ambiguities", list wording with more than one reasonable reading (for example whether "20 units" counts the \
side-chain units, or whether maleic units are fully deprotonated), one string each: "issue | the reading you chose | \
alternative; alternative". Short phrases. Empty when there is none.
- In "missing", list information the user should confirm that has no documented default. Keep it short; empty when \
nothing important is missing.
- If the request asks for something these builders cannot make (another force field, solvent or water, other \
molecules, a mineral or surface not in the catalogue, ...), set buildable false, explain why in \
out_of_scope_reason in one or two sentences (otherwise an empty string), and fill spec with the closest reading (it is not used). Never \
suggest a different system.
- Use seed 1 and an empty "notes".

"""


def system_prompt() -> str:
    return ASSIST_INTRO + knowledge()


# --------------------------------------------------------------------------------------------- the model call
def _cache_path(text: str) -> str:
    return os.path.join(CACHE, hashlib.sha256(text.strip().encode()).hexdigest()[:20] + ".json")


def cached(text: str):
    p = _cache_path(text)
    return json.load(open(p)) if os.path.exists(p) else None


def analyse(text: str, client=None) -> dict:
    """One model call. Returns {"ok", "result" (ASSIST_SCHEMA), "problems", "model", "version"}; never raises on
    a bad answer (problems lists what was wrong). Successful analyses are saved for offline use."""
    import anthropic
    client = client or anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL, max_tokens=8000,
        system=[{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": text.strip()}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": ASSIST_SCHEMA}})
    if resp.stop_reason in ("refusal", "max_tokens"):
        return {"ok": False, "result": None, "problems": [f"no usable answer (stop reason {resp.stop_reason})"]}
    try:
        result = json.loads("".join(b.text for b in resp.content if b.type == "text"))
    except json.JSONDecodeError as e:
        return {"ok": False, "result": None, "problems": [f"unreadable answer: {e}"]}
    out = {"ok": True, "result": result, "problems": check_result(result), "model": resp.model, "version": ASSIST_VERSION}
    if out["problems"] and result.get("buildable"):
        out["ok"] = False
    os.makedirs(CACHE, exist_ok=True)
    if out["ok"]:
        json.dump({"input": text.strip(), **out}, open(_cache_path(text), "w"), indent=1)
    return out


def parameters(r: dict) -> dict:
    """{key: (source, note)} from the assistant's "key | source | note" strings; malformed entries are skipped."""
    out = {}
    for line in r.get("parameters") or []:
        parts = [x.strip() for x in str(line).split("|")]
        if len(parts) >= 2 and parts[1] in ("stated", "inferred", "default"):
            out[parts[0]] = (parts[1], " | ".join(parts[2:]))
    return out


def ambiguities(r: dict) -> list:
    """[(issue, chosen, [alternatives])] from "issue | chosen | alt; alt" strings."""
    out = []
    for line in r.get("ambiguities") or []:
        parts = [x.strip() for x in str(line).split("|")]
        if parts and parts[0]:
            alts = [a.strip() for a in parts[2].split(";") if a.strip()] if len(parts) > 2 else []
            out.append((parts[0], parts[1] if len(parts) > 1 else "", alts))
    return out


def check_result(r: dict) -> list:
    """Schema-level problems the JSON schema cannot express: the spec must convert to a builder spec."""
    if not r.get("buildable"):
        return [] if r.get("out_of_scope_reason") else ["not buildable, but no reason given"]
    if not r.get("spec"):
        return ["buildable, but no spec"]
    return spec_problems(r["spec"])


def spec_problems(a: dict) -> list:
    out = []
    try:
        to_builder_spec(a)
    except (KeyError, TypeError, ValueError) as e:
        out.append(f"inconsistent specification: {e}")
        return out
    p = a.get("pce")
    if p:
        labels = {m["label"] for m in p["monomers"]}
        for c in p["composition"]:
            if c["label"] not in labels:
                out.append(f"composition names an unknown unit {c['label']!r}")
        if sum(c["count"] for c in p["composition"]) < 1:
            out.append("the backbone has no units")
        if p["n_chains"] < 1:
            out.append("at least one chain is needed")
        q = carboxylates(a) * max(p["n_chains"], 1)
        ion = p.get("counterion")
        if ion and q and q % ION[ion][1]:
            out.append(f"{ION[ion][0]} cannot neutralise {q} carboxylates exactly (the builder would refuse)")
    if a.get("mineral") and a["force_field"] == "cvff":
        cat = {m["name"]: m for m in mineral_catalogue()}
        if a["mineral"]["model"] in cat and "cvff" not in cat[a["mineral"]["model"]]["ffs"]:
            out.append(f"{a['mineral']['model']} is not covered by CVFF-INTERFACE (use PCFF-INTERFACE)")
    return out


# --------------------------------------------------------------------------------------------- catalogue
def mineral_catalogue() -> list:
    """Cement-mineral models with the force fields that cover them (same source as the baseline's catalogue)."""
    from builders.minerals import KNOWN_DEFECTIVE
    out = []
    for car in sorted(glob.glob(os.path.join(UGRP, "CEMENT_MINERALS", "*.car"))):
        name = os.path.basename(car)[:-4]
        if name in KNOWN_DEFECTIVE:
            continue
        ffs = [ff for ff in ("pcff", "cvff")
               if os.path.exists(os.path.join(ROOT, "data", "reference", "minerals", f"{name}_{ff}.data"))]
        if ffs:
            out.append({"name": name, "surface": "surface" in name, "ffs": ffs})
    return out


def usable_surfaces() -> list:
    """Surface slabs the composite builder accepts (a vacuum gap above the slab)."""
    from builders.composite import Data, slab_geometry
    out = []
    for m in mineral_catalogue():
        if not m["surface"]:
            continue
        try:
            slab_geometry(Data(os.path.join(ROOT, "data", "reference", "minerals", f"{m['name']}_pcff.data")))
            out.append(m["name"])
        except (ValueError, OSError):
            pass
    return out


def model_title(name: str) -> str:
    base = {"c3s": "C3S (tricalcium silicate)", "c3a": "C3A (tricalcium aluminate)", "ettr": "ettringite",
            "monosulfate": "monosulfate", "tob11": "tobermorite 11 Å", "tob14": "tobermorite 14 Å"}
    head, _, rest = name.partition("_")
    rest = rest.replace("_", " ")
    return f"{base.get(head, head)} — {rest}" if rest else base.get(head, head)


# --------------------------------------------------------------------------------------------- words
def unit_name(m: dict, short: bool = False) -> str:
    k = m["kind"]
    if k == "acid":
        acid = "methacrylic acid" if m.get("alpha_methyl") else "acrylic acid"
        return acid if short else f"{acid} ({'COO⁻' if m.get('deprotonated') else 'COOH'})"
    if k == "diacid":
        d = int(m.get("deprotonated") or 0)
        return "maleic acid" if short else f"maleic acid ({d} COO⁻)" if d else "maleic acid (COOH, neutral)"
    eo, end = m.get("eo_units"), m.get("end") or ("OCH3" if k == "ester_peg" else "OH")
    if k == "ester_peg":
        name = "MPEG methacrylate" if m.get("alpha_methyl") else "PEG acrylate"
    else:
        name = ETHER.get((bool(m.get("alpha_methyl")), int(m.get("spacer") or 1)), "PEG ether")
    return name if short else f"{name}, EO{eo}, {'OCH₃' if end == 'OCH3' else 'OH'} end"


def polymer_type(p: dict) -> str:
    kinds = [m for m in p["monomers"] if m["kind"] in ("ester_peg", "ether_peg")]
    if not kinds:
        return "polycarboxylate"
    names = sorted({"MPEG" if m["kind"] == "ester_peg" and m.get("alpha_methyl") else
                    "PEG-acrylate" if m["kind"] == "ester_peg" else unit_name(m, short=True) for m in kinds})
    return "/".join(names) + "-type PCE"


def _a(word: str) -> str:
    return ("an " if word[:1].upper() in "AEIOU" or word[:4] in ("MPEG", "HPEG") else "a ") + word


def carboxylates(a: dict) -> int:
    """Carboxylate groups per chain, from the composition (what the counter-ions neutralise)."""
    p = a.get("pce") or {}
    mons = {m["label"]: m for m in p.get("monomers", [])}
    q = 0
    for c in p.get("composition", []):
        m = mons.get(c["label"])
        if not m:
            continue
        if m["kind"] == "acid" and m.get("deprotonated"):
            q += c["count"]
        elif m["kind"] == "diacid":
            q += c["count"] * int(m.get("deprotonated") or 0)
    return q


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _pce_sentence(p: dict) -> str:
    mons = {m["label"]: m for m in p["monomers"]}
    comp = [(c["label"], c["count"]) for c in p["composition"] if c["count"] > 0]
    total = sum(n for _, n in comp)
    parts = []
    for lab, n in comp:
        m = mons[lab]
        k = m["kind"]
        if k == "acid":
            acid = "methacrylic acid" if m.get("alpha_methyl") else "acrylic acid"
            parts.append(f"{n} {acid} unit{'' if n == 1 else 's'} ({'deprotonated, COO⁻' if m.get('deprotonated') else 'protonated, COOH'})")
        elif k == "diacid":
            d = int(m.get("deprotonated") or 0)
            parts.append(f"{n} maleic acid unit{'' if n == 1 else 's'} ({'with ' + _plural(d, 'carboxylate') + ' (COO⁻) each' if d else 'fully protonated, COOH'})")
        else:
            end = END[m.get("end") or ("OCH3" if k == "ester_peg" else "OH")]
            if k == "ester_peg":
                kind = "MPEG methacrylate ester" if m.get("alpha_methyl") else "PEG acrylate ester"
            else:
                kind = ETHER_LONG.get(ETHER.get((bool(m.get("alpha_methyl")), int(m.get("spacer") or 1)), ""), "PEG ether")
            parts.append(f"{n} {kind} side-chain unit{'' if n == 1 else 's'} with {m.get('eo_units')} EO units and a {end} end")
    chains = p["n_chains"]
    seq = p["sequence"]
    if seq["mode"] == "explicit":
        order = ", ".join(unit_name(mons[l], short=True) for l in (seq.get("explicit") or []) if l in mons)
        seq_text = f"in this explicit order along the chain: {order}"
    else:
        seq_text = f"in {_a(SEQ[seq['mode']])} sequence"
    ends = " and ".join(p["end_groups"])
    s = (f"{_plural(chains, 'chain')} of {_a(polymer_type(p))}, {'each ' if chains > 1 else ''}with a backbone of {total} units: "
         f"{'; '.join(parts)}, {seq_text}. Backbone end groups {ends}.")
    ion = p.get("counterion")
    q = carboxylates({"pce": p}) * chains
    if ion:
        sym, z = ION[ion]
        s += (f" {sym} counter-ions neutralise the {q} carboxylates ({q // z if q % z == 0 else q / z:g} ions)." if q
              else f" Counter-ion {sym} (no carboxylates to neutralise).")
    else:
        s += f" No counter-ions (net charge −{q} e)." if q else " No counter-ions."
    return s


def render_prompt(a: dict) -> str:
    """The configuration as one explicit request, in the words the builders' documentation uses."""
    ff = FF[a["force_field"]]
    if a["builder"] == "minerals":
        m = a["mineral"]
        return (f"Build a LAMMPS data file in {ff} of the {m['model']} cement-mineral model "
                f"({model_title(m['model'])}) as a {' × '.join(map(str, m['supercell']))} supercell.")
    p = a["pce"]
    if a["builder"] == "pce":
        pad = p.get("box_padding")
        return (f"Build a LAMMPS data file in {ff} for {_pce_sentence(p)} Box padding "
                f"{2.0 if pad is None else pad:g} Å on every side.")
    s = a["surface"]
    sc = "the smallest lateral repetition that fits the PCE" if s["supercell"] == "auto" else \
        f"a {' × '.join(map(str, s['supercell']))} surface supercell"
    h = a.get("height")
    orient = {"flat": "lying flat", "as_built": "as built (not flattened)"}[a.get("orientation") or "flat"]
    return (f"Build a LAMMPS data file in {ff} of a PCE on the {s['model']} surface ({model_title(s['model'])}), "
            f"using {sc}. The PCE: {_pce_sentence(p)} Place it {orient}, {3.0 if h is None else h:g} Å above the "
            f"topmost surface atom.")


def describe_built(spec: dict, facts: dict) -> str:
    """One sentence about the generated structure, from the builder spec that was used and the file facts."""
    from agents.baseline import from_builder_spec
    a = from_builder_spec(spec)
    atoms = f"{facts['atoms']:,} atoms"
    box = " × ".join(f"{x:.1f}" for x in facts["box_A"]["lengths"])
    ff = FF[spec["force_field"]]
    if a["builder"] == "minerals":
        m = a["mineral"]
        return (f"{model_title(m['model'])}, {' × '.join(map(str, m['supercell']))} supercell in {ff}: "
                f"{atoms} in a {box} Å cell.")
    p = a["pce"]
    mons = {m["label"]: m for m in p["monomers"]}
    comp = ", ".join(f"{c['count']} {unit_name(mons[c['label']])}" for c in p["composition"] if c["count"])
    total = sum(c["count"] for c in p["composition"])
    seq = p["sequence"]["mode"]
    ion = p.get("counterion")
    head = (f"{_plural(p['n_chains'], 'chain')} of {_a(polymer_type(p))} with {total} backbone units each "
            f"({comp}), {seq} sequence" + (f", neutralised by {ION[ion][0]}" if ion else ""))
    if a["builder"] == "composite":
        return (f"{head}, placed {(a.get('orientation') or 'flat').replace('_', ' ')} "
                f"{a.get('height') or 3.0:g} Å above the {model_title(a['surface']['model'])} surface — "
                f"{atoms} in a {box} Å cell, {ff}.")
    return f"{head} — {atoms} in a {box} Å box, {ff}."


def builder_defaults(spec: dict) -> list:
    """[(parameter, value)] whose value equals the documented builder default (PCE / composite)."""
    if spec["builder"] == "minerals":
        return []
    p = spec["pce"] if spec["builder"] == "composite" else spec
    out = []
    if list(p.get("end_groups", ["CH3", "CH3"])) == ["CH3", "CH3"]:
        out.append(("Backbone end groups", "CH₃ and CH₃"))
    for lab, m in p.get("monomers", {}).items():
        if m["kind"] == "ester_peg" and m.get("end") == "OCH3":
            out.append((f"Side-chain end ({lab})", "methoxy, OCH₃ (default for ester side chains)"))
        if m["kind"] == "ether_peg" and m.get("end") == "OH":
            out.append((f"Side-chain end ({lab})", "hydroxyl, OH (default for ether side chains)"))
    if int(p.get("n_chains", 1)) == 1:
        out.append(("Number of chains", "1"))
    if spec["builder"] == "pce" and float((p.get("box") or {}).get("padding", 2.0)) == 2.0:
        out.append(("Box padding", "2 Å on every side"))
    if spec["builder"] == "composite":
        if float(spec.get("height", 3.0)) == 3.0:
            out.append(("Height above the surface", "3 Å"))
        if spec.get("orientation", "flat") == "flat":
            out.append(("Orientation", "flat on the surface"))
        if spec["surface"]["supercell"] == "auto":
            out.append(("Surface cells", "smallest repetition that fits the PCE"))
    return out

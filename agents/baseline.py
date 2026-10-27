"""Single-call baseline (plan Days 23-24; SPEC §7.3 E, §7.12).

One model call per task, no tools, no validator feedback, no retry: the model reads the request and
returns a builder spec as structured output (JSON schema below); the deterministic builders
(builders/dispatch.py) turn it into the DATA FILE. The model never writes coordinate lines. A refusal,
a truncated or unparseable answer, or a builder refusal is a failed run (NO_OUTPUT).

The system prompt is generated from the builders' documentation and the model database (names, cells,
surface normals, force-field coverage) — nothing task-specific. The agent loop (Nov) adds tools and
validator feedback on top of the same builders.

Model and settings are recorded in every result (METRICS §5); prices come from eval/pricing.json
(fetched from the pricing page on the day of the run). No API key is ever written to a file: the SDK
reads ANTHROPIC_API_KEY (or an `ant auth login` profile) from the environment.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builders.dispatch import build_from_spec  # noqa: E402
from builders.pce import architecture_from_params  # noqa: E402

def model_config() -> dict:
    """The `model:` block of config.yaml: the one place where the model is chosen (plan Day 23)."""
    import yaml
    return yaml.safe_load(open(os.path.join(ROOT, "config.yaml"))).get("model") or {}


MODEL = model_config().get("model_id") or "claude-opus-5-5"    # config.yaml; Claude API ID, models overview 2026-10-27
EFFORT = model_config().get("effort") or "medium"               # the model's documented default, set explicitly
MAX_TOKENS = 16000
PROMPT_VERSION = "baseline-v1 (2026-10-27)"
UGRP = os.path.dirname(ROOT)

# ---------------------------------------------------------------------------------------------
_NULL = {"type": "null"}


def _opt(schema):
    return {"anyOf": [schema, _NULL]}


_OBJ = lambda props: {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}  # noqa: E731
_INT3 = {"type": "array", "items": {"type": "integer"}}
MONOMER = _OBJ({
    "label": {"type": "string"},
    "kind": {"type": "string", "enum": ["acid", "ester_peg", "ether_peg", "diacid"]},
    "alpha_methyl": _opt({"type": "boolean"}),
    "deprotonated": _opt({"type": "integer"}),
    "eo_units": _opt({"type": "integer"}),
    "end": _opt({"type": "string", "enum": ["OH", "OCH3"]}),
    "spacer": _opt({"type": "integer"}),
})
PCE = _OBJ({
    "monomers": {"type": "array", "items": MONOMER},
    "composition": {"type": "array", "items": _OBJ({"label": {"type": "string"}, "count": {"type": "integer"}})},
    "sequence": _OBJ({"mode": {"type": "string", "enum": ["random", "alternating", "block", "gradient", "explicit"]},
                      "explicit": _opt({"type": "array", "items": {"type": "string"}})}),
    "end_groups": {"type": "array", "items": {"type": "string", "enum": ["CH3", "H"]}},
    "n_chains": {"type": "integer"},
    "counterion": _opt({"type": "string", "enum": ["Ca2+", "Na+", "K+"]}),
    "box_padding": _opt({"type": "number"}),
    "seed": {"type": "integer"},
})
SCHEMA = _OBJ({
    "builder": {"type": "string", "enum": ["minerals", "pce", "composite"]},
    "force_field": {"type": "string", "enum": ["pcff", "cvff"]},
    "mineral": _opt(_OBJ({"model": {"type": "string"}, "supercell": _INT3})),
    "pce": _opt(PCE),
    "surface": _opt(_OBJ({"model": {"type": "string"},
                          "supercell": {"anyOf": [_INT3, {"type": "string", "enum": ["auto"]}]}})),
    "height": _opt({"type": "number"}),
    "orientation": _opt({"type": "string", "enum": ["flat", "as_built"]}),
    "notes": {"type": "string"},
})


# ---------------------------------------------------------------------------------------------
def to_builder_spec(r: dict) -> dict:
    """Model answer (SCHEMA) -> builders/dispatch.py spec. Raises ValueError on an inconsistent answer."""
    b, ff = r["builder"], r["force_field"]
    if b == "minerals":
        m = r.get("mineral") or {}
        if not m:
            raise ValueError("builder 'minerals' needs the 'mineral' field")
        return {"builder": "minerals", "model": m["model"], "supercell": list(m["supercell"]), "force_field": ff}
    p = r.get("pce")
    if not p:
        raise ValueError(f"builder {b!r} needs the 'pce' field")
    mons = {}
    for m in p["monomers"]:
        k = m["kind"]
        if k == "acid":
            u = {"kind": "acid", "alpha_methyl": bool(m.get("alpha_methyl")), "deprotonated": bool(m.get("deprotonated"))}
        elif k == "diacid":
            u = {"kind": "diacid", "deprotonated": int(m.get("deprotonated") or 0)}
        else:
            u = {"kind": k, "alpha_methyl": bool(m.get("alpha_methyl")), "eo_units": int(m.get("eo_units") or 0),
                 "end": m.get("end") or "OH"}
            if k == "ether_peg":
                u["spacer"] = int(m.get("spacer") or 1)
        mons[m["label"]] = u
    seq = p["sequence"]
    arch = {"monomers": mons, "composition": {c["label"]: int(c["count"]) for c in p["composition"]},
            "sequence": seq["explicit"] if seq["mode"] == "explicit" else seq["mode"],
            "end_groups": list(p["end_groups"]), "n_chains": int(p["n_chains"]), "counterion": p.get("counterion"),
            "seed": int(p["seed"])}
    if p.get("box_padding") is not None:
        arch["box"] = {"padding": float(p["box_padding"])}
    if b == "pce":
        return {"builder": "pce", **arch, "force_field": ff}
    s = r.get("surface") or {}
    if not s:
        raise ValueError("builder 'composite' needs the 'surface' field")
    arch.pop("box", None)
    sc = s["supercell"] if s["supercell"] == "auto" else list(s["supercell"])
    out = {"builder": "composite", "surface": {"model": s["model"], "supercell": sc}, "pce": arch,
           "force_field": ff}
    if r.get("height") is not None:
        out["height"] = float(r["height"])
    if r.get("orientation"):
        out["orientation"] = r["orientation"]
    return out


def from_builder_spec(spec: dict) -> dict:
    """Inverse of to_builder_spec (for the 'perfect model' mock that checks the glue, and for tests)."""
    def pce_part(p):
        if "monomers" not in p:
            p = architecture_from_params(dict(p))
        mons = []
        for lab, u in p["monomers"].items():
            dep = u.get("deprotonated")
            mons.append({"label": lab, "kind": u["kind"], "alpha_methyl": u.get("alpha_methyl"),
                         "deprotonated": (int(dep) if dep is not None else None),
                         "eo_units": u.get("eo_units"), "end": u.get("end"), "spacer": u.get("spacer")})
        seq = p.get("sequence", "random")
        return {"monomers": mons, "composition": [{"label": k, "count": v} for k, v in p["composition"].items()],
                "sequence": {"mode": "explicit", "explicit": seq} if isinstance(seq, list) else {"mode": seq, "explicit": None},
                "end_groups": p.get("end_groups", ["CH3", "CH3"]), "n_chains": p.get("n_chains", 1),
                "counterion": p.get("counterion", "Ca2+"), "box_padding": (p.get("box") or {}).get("padding"),
                "seed": p.get("seed", 1)}
    base = {"builder": spec["builder"], "force_field": spec["force_field"], "mineral": None, "pce": None,
            "surface": None, "height": None, "orientation": None, "notes": ""}
    if spec["builder"] == "minerals":
        base["mineral"] = {"model": spec["model"], "supercell": spec["supercell"]}
    elif spec["builder"] == "pce":
        base["pce"] = pce_part(spec)
    else:
        base["pce"] = pce_part(spec["pce"])
        base["surface"] = dict(spec["surface"])
        base["height"], base["orientation"] = spec.get("height"), spec.get("orientation")
    return base


# ---------------------------------------------------------------------------------------------
def model_catalogue() -> str:
    """One line per INTERFACE cement-mineral model: cell, kind, surface normal, force fields that cover it."""
    from builders.composite import Data, slab_geometry
    from builders.minerals import KNOWN_DEFECTIVE
    lines = []
    for car in sorted(glob.glob(os.path.join(UGRP, "CEMENT_MINERALS", "*.car"))):
        name = os.path.basename(car)[:-4]
        if name in KNOWN_DEFECTIVE:
            lines.append(f"- {name}: defective database entry, do not use ({KNOWN_DEFECTIVE[name]})")
            continue
        pbc = next(l for l in open(car) if l.startswith("PBC "))
        a, b, c, al, be, ga = (float(x) for x in pbc.split()[1:7])
        ffs = [ff for ff in ("pcff", "cvff")
               if os.path.exists(os.path.join(ROOT, "data", "reference", "minerals", f"{name}_{ff}.data"))]
        kind = "unit cell"
        extra = ""
        if "surface" in name:
            kind = "surface slab"
            try:
                g = slab_geometry(Data(os.path.join(ROOT, "data", "reference", "minerals", f"{name}_pcff.data")))
                extra = f"; surface normal {'xyz'[g['axis']]} (slab {g['thickness']:.1f} Å thick + vacuum)"
            except ValueError:
                extra = "; no vacuum gap (the gap is filled with water): not usable by the composite builder"
        elif "rectangular" in name:
            kind = "rectangular (orthogonal) cell"
        lines.append(f"- {name}: {kind}, a b c = {a:.3f} {b:.3f} {c:.3f} Å, angles {al:g} {be:g} {ga:g}{extra}; "
                     f"force fields: {', '.join(ffs) or 'none'}")
    return "\n".join(lines)


BASELINE_INTRO = """You turn a request for a LAMMPS DATA FILE into a structured spec for deterministic structure builders. \
You do not write the file: the builders do (INTERFACE FF 1.5, msi2lmp typing and charges, LAMMPS-checked). \
Return only the JSON spec defined by the output schema; the "notes" field may hold one or two sentences of reasoning."""


def system_prompt() -> str:
    return BASELINE_INTRO + "\n\n" + knowledge()


def knowledge() -> str:
    """Force fields, builders, monomers and the model catalogue: shared word for word with the agent loop,
    so the two systems differ only in tools, feedback and retries."""
    return f"""## Force fields
- "pcff" = PCFF-INTERFACE (class II). Covers every cement-mineral model below and all PCE chemistry.
- "cvff" = CVFF-INTERFACE (class I). Covers PCE chemistry, but among minerals only the C3S and C3A models listed with cvff below.
Use the force field the request names.

## builder "minerals": an INTERFACE FF cement-mineral model, optionally replicated
Fields: mineral.model (exact name from the catalogue), mineral.supercell [na, nb, nc] (replications along a, b, c; [1,1,1] = one cell). \
Triclinic cells are tilt-reduced automatically.

## builder "pce": polycarboxylate ether/ester superplasticiser, any architecture
A vinyl backbone of monomer units, each unit given a short label (1-3 letters or digits, e.g. "A", "E"):
- kind "acid": acrylic (alpha_methyl false) or methacrylic (alpha_methyl true) acid unit; deprotonated 1 = carboxylate (COO-), 0 = COOH.
- kind "ester_peg": (meth)acrylate ester carrying a PEG side chain: alpha_methyl false = acrylate ester, true = methacrylate ester (MPEG type); eo_units = ethylene-oxide units in the side chain; end "OH" or "OCH3" (methoxy).
- kind "ether_peg": vinyl-ether-anchored PEG: APEG (allyl) = alpha_methyl false, spacer 1; HPEG (methallyl) = alpha_methyl true, spacer 1; TPEG (isoprenyl) = alpha_methyl true, spacer 2; VPEG (butenyl / 4-hydroxybutyl vinyl) = alpha_methyl false, spacer 2; eo_units and end as above.
- kind "diacid": maleic unit; deprotonated = number of carboxylates (0, 1 or 2).
Unused fields of a monomer are null.
composition: number of units of each label per chain (the backbone length is the sum). Partly deprotonated acid = two labels (one deprotonated, one not).
sequence.mode: "random" (shuffled), "alternating" (side-chain units spread evenly between the others), "block" (units in the order of the composition list: all of the first label, then the next), "gradient" (side-chain density increasing along the chain), or "explicit" with sequence.explicit = the full list of labels in chain order.
end_groups: [head, tail], each "CH3" or "H". n_chains: number of identical-architecture chains. \
counterion: "Ca2+", "Na+" or "K+" to neutralise the carboxylates (null = leave the system charged). \
box_padding: empty space in Å on every side of the box around the atoms (default 2.0). seed: any integer.

## builder "composite": a PCE on a cement-mineral surface
pce as above (box_padding null). surface.model = a surface-slab model from the catalogue; surface.supercell = replications, \
which must be 1 along that model's surface normal, or "auto" (the smallest lateral repetition that fits the PCE). height = Å between the topmost slab atom and the lowest PCE atom (default 3.0). \
orientation "flat" (PCE laid flat on the surface, default) or "as_built". Unused top-level fields are null.

## Mineral model catalogue (UGRP/CEMENT_MINERALS)
{model_catalogue()}
"""


# ---------------------------------------------------------------------------------------------
class BaselineSystem:
    """system(task_view, workdir) for eval/harness.py."""

    def __init__(self, mock: str = None, model: str = MODEL, effort: str = EFFORT):
        self.mock = mock
        self.needs_hidden = mock == "perfect"
        self.model, self.effort = model, effort
        self.system = system_prompt()
        self.meta = {"name": "baseline" + (f"-mock-{mock}" if mock else ""), "kind": "single call, no tools, no feedback",
                     "model": None if mock else model, "effort": effort, "thinking": "adaptive (always on for this model)",
                     "sampling": "API defaults (temperature is not settable on this model)", "max_tokens": MAX_TOKENS,
                     "prompt_version": PROMPT_VERSION,
                     "system_prompt_sha256": hashlib.sha256(self.system.encode()).hexdigest(),
                     "schema_sha256": hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest(),
                     "refusal_fallback": "off (a fallback model would change which model is measured)"}
        self._client = None

    def _call(self, text: str):
        import anthropic
        if self._client is None:
            self._client = anthropic.Anthropic()
        resp = self._client.messages.create(
            model=self.model, max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": text}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}})
        u = resp.usage
        usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                 "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                 "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
        trace = {"request_id": getattr(resp, "_request_id", None), "model": resp.model, "stop_reason": resp.stop_reason}
        if resp.stop_reason == "refusal":
            det = getattr(resp, "stop_details", None)
            trace["stop_details"] = det.to_dict() if hasattr(det, "to_dict") else str(det)
            return None, usage, trace
        text_out = "".join(b.text for b in resp.content if b.type == "text")
        trace["response_text"] = text_out
        if resp.stop_reason == "max_tokens":
            return None, usage, trace
        return json.loads(text_out), usage, trace

    def __call__(self, task, workdir, repeat=0):
        t0 = time.time()
        if self.mock == "perfect":
            answer, usage, trace = from_builder_spec(task["hidden_spec"]), {}, {"mock": "perfect"}
        else:
            import anthropic
            try:
                answer, usage, trace = self._call(task["input"])
            except anthropic.AuthenticationError:
                raise SystemExit("No valid Anthropic credentials: set ANTHROPIC_API_KEY (or run `ant auth login`).")
            except TypeError as e:      # no credentials at all: stop the run instead of failing every task
                if "authentication method" in str(e):
                    raise SystemExit("No Anthropic credentials: set ANTHROPIC_API_KEY (or run `ant auth login`).")
                raise
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                return {"data_file": None, "error": f"API: {type(e).__name__}: {e}", "usage": {}, "trace": {}}
            except json.JSONDecodeError as e:
                return {"data_file": None, "error": f"unparseable answer: {e}", "usage": {}, "trace": {}}
        trace["call_s"] = round(time.time() - t0, 2)
        out = {"usage": usage, "trace": trace, "attempts": 1}
        if answer is None:
            out.update(data_file=None, error=f"no answer (stop_reason {trace.get('stop_reason')})")
            return out
        trace["answer"] = answer
        try:
            spec = to_builder_spec(answer)
        except (KeyError, TypeError, ValueError) as e:
            out.update(data_file=None, error=f"inconsistent spec: {e}")
            return out
        trace["builder_spec"] = spec
        try:
            path, rec = build_from_spec(spec, workdir, task["id"])
        except Exception as e:
            out.update(data_file=None, builder_refused=True, error=f"builder: {type(e).__name__}: {str(e)[:300]}")
            return out
        out["data_file"] = path
        return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="python -m agents.baseline")
    ap.add_argument("--show-prompt", action="store_true", help="print the system prompt and the output schema")
    if ap.parse_args().show_prompt:
        print(system_prompt())
        print(json.dumps(SCHEMA, indent=1))

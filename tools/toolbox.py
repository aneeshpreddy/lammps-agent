"""The agent's tool layer (plan Days 26-27): a minimal set of deterministic tools with strict schemas.

  build_data_file        builder spec -> DATA FILE in the attempt's work directory + plain facts about it
  get_model_info         one cement-mineral model in one force field: cell, composition, atom types, charges
                         (the plan's get_type_map, for the models the builders type)
  get_reference_example  a known-good request + build_data_file input (tools/examples.py)

The plan's run_generation_script(code) is replaced by build_data_file(spec): the model never writes
code or coordinate lines (SPEC §7.3 E); the spec is the same one the baseline returns (agents/baseline.py
SCHEMA, without its "notes" field), so the two systems differ only by tools and feedback.

The validator is NOT a tool: the orchestrator runs it after every attempt (plan, Key design decisions).

Every tool
  - is defined with strict: true (the API then returns schema-valid arguments) and still checks its
    arguments against the same schema (tools/schema_check.py);
  - is deterministic: the same arguments give the same answer (builds are seeded; the knowledge tools read
    fixed files) and it is safe to retry: a build writes a new file and never touches earlier ones;
  - never raises: any problem becomes {"ok": false, "error": ...}, returned to the model as is_error;
  - is logged as one JSON line (timestamp, tool, arguments, result summary, duration) in tool_calls.jsonl.

The output of an attempt is the last successful build (ToolBox.last_build); the orchestrator validates it
when the model stops calling tools.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents.baseline import SCHEMA, from_builder_spec, to_builder_spec  # noqa: E402
from builders.dispatch import build_from_spec  # noqa: E402
from tools.examples import EXAMPLES  # noqa: E402
from tools.facts import FORCE_FIELDS, cement_models, data_facts, model_facts  # noqa: E402
from tools.schema_check import check  # noqa: E402

TOOLS_VERSION = "tools-v1 (2026-10-27)"

BUILD_SCHEMA = copy.deepcopy(SCHEMA)
del BUILD_SCHEMA["properties"]["notes"]
BUILD_SCHEMA["required"] = [k for k in BUILD_SCHEMA["required"] if k != "notes"]

MODEL_INFO_SCHEMA = {"type": "object", "properties": {
    "model": {"type": "string", "enum": cement_models()},
    "force_field": {"type": "string", "enum": list(FORCE_FIELDS)}},
    "required": ["model", "force_field"], "additionalProperties": False}

EXAMPLE_SCHEMA = {"type": "object", "properties": {"kind": {"type": "string", "enum": list(EXAMPLES)}},
                  "required": ["kind"], "additionalProperties": False}

DESCRIPTIONS = {
    "build_data_file":
        "Build a LAMMPS DATA FILE with the deterministic builders (INTERFACE FF 1.5 typing and charges) from a "
        "builder spec, and return plain facts about the file: atom and topology counts, element counts, net "
        "charge, molecule count, box lengths, and builder details (PCE sequences and counter-ions; the surface "
        "model, supercell, normal and PCE height for a composite). Use it to build the answer, and again after "
        "changing the spec; the last successful build is the file that gets submitted. Fields that do not apply "
        "to the chosen builder must be null. Returns ok=false with the reason if the spec is inconsistent or a "
        "builder refuses (unknown model, missing force-field parameters, PCE does not fit). Building does not "
        "validate the file.",
    "get_model_info":
        "Look up one INTERFACE FF cement-mineral model in one force field: unit-cell lengths and angles, kind "
        "(unit cell, rectangular cell or surface slab), atom count, element counts, net charge, the atom-type "
        "table (force-field type, element, mass, count, charges) and, for slabs, the surface normal, slab "
        "thickness and vacuum gap. Use it to choose between similar models or to check composition before "
        "building. Returns ok=false if the model is not available in that force field (CVFF-INTERFACE covers "
        "only the C3S and C3A models) or is a known-defective database entry.",
    "get_reference_example":
        "Return a known-good worked example: a request in natural language and the exact build_data_file input "
        "that answers it, with a short explanation of how the request maps to the fields. Kinds: mineral "
        "supercell, MPEG ester PCE, TPEG ether PCE with an explicit sequence, maleic-HPEG PCE, partly "
        "deprotonated two-chain block PCE, PCE on a surface (composite). The examples are not the requested "
        "system: use them for the format, not for the values.",
}
SCHEMAS = {"build_data_file": BUILD_SCHEMA, "get_model_info": MODEL_INFO_SCHEMA,
           "get_reference_example": EXAMPLE_SCHEMA}


def definitions() -> list:
    """Tool definitions for client.messages.create(tools=...)."""
    return [{"name": n, "description": DESCRIPTIONS[n], "input_schema": SCHEMAS[n], "strict": True} for n in SCHEMAS]


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


class ToolBox:
    """The tools of one attempt, bound to its work directory and its JSONL log."""

    def __init__(self, workdir: str, log_path: str = None):
        self.workdir = workdir
        os.makedirs(workdir, exist_ok=True)
        self.log_path = log_path or os.path.join(workdir, "tool_calls.jsonl")
        self.n_calls = 0
        self.n_builds = 0
        self.last_build = None          # path of the last successful build: the attempt's output
        self.builds = []                # every build: {"build", "ok", "data_file" + "spec" | "error"}

    # -- dispatch ------------------------------------------------------------------------------
    def run(self, name: str, args) -> dict:
        t0 = time.time()
        self.n_calls += 1
        if name not in SCHEMAS:
            res = {"ok": False, "error": f"unknown tool {name!r}; tools: {', '.join(SCHEMAS)}"}
        elif not isinstance(args, dict):
            res = {"ok": False, "error": f"arguments must be a JSON object, got {type(args).__name__}"}
        else:
            errs = check(SCHEMAS[name], args)
            if errs:
                res = {"ok": False, "error": "invalid arguments: " + "; ".join(errs[:10])}
            else:
                try:
                    res = getattr(self, "_" + name)(args)
                except Exception as e:          # a tool never raises into the loop
                    res = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:500]}"}
        self._log(name, args, res, time.time() - t0)
        return res

    def spec_of(self, data_file: str) -> dict:
        """The builder spec that produced a build (the orchestrator picks the validation config from it)."""
        return next(b["spec"] for b in self.builds if b.get("data_file") == data_file)

    def tool_result(self, block) -> dict:
        """A tool_use block (SDK object or dict) -> the tool_result block that answers it."""
        get = (lambda k: block[k]) if isinstance(block, dict) else (lambda k: getattr(block, k))
        res = self.run(get("name"), get("input"))
        return {"type": "tool_result", "tool_use_id": get("id"), "content": json.dumps(res),
                "is_error": not res["ok"]}

    # -- tools ---------------------------------------------------------------------------------
    def _build_data_file(self, args: dict) -> dict:
        self.n_builds += 1
        name = f"build_{self.n_builds}"
        entry = {"build": name, "ok": False}
        self.builds.append(entry)
        try:
            spec = to_builder_spec({**args, "notes": ""})
        except (KeyError, TypeError, ValueError) as e:
            entry["error"] = f"inconsistent spec: {e}"
            return {"ok": False, "build": name, "stage": "spec", "error": entry["error"]}
        try:
            path, rec = build_from_spec(spec, os.path.join(self.workdir, name), name)
        except Exception as e:
            entry["error"] = f"builder: {type(e).__name__}: {str(e)[:500]}"
            return {"ok": False, "build": name, "stage": "builder", "error": entry["error"]}
        entry.update(ok=True, data_file=path, spec=spec)
        self.last_build = path
        return {"ok": True, "build": name, "builder": spec["builder"], "facts": data_facts(path),
                "builder_details": _details(spec["builder"], rec)}

    def _get_model_info(self, args: dict) -> dict:
        try:
            return {"ok": True, **model_facts(args["model"], args["force_field"])}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    def _get_reference_example(self, args: dict) -> dict:
        ex = EXAMPLES[args["kind"]]
        inp = from_builder_spec(ex["spec"])
        del inp["notes"]
        return {"ok": True, "kind": args["kind"], "request": ex["request"], "build_data_file_input": inp,
                "explanation": ex["explanation"]}

    # -- log -----------------------------------------------------------------------------------
    def _log(self, name, args, res, dt):
        line = {"ts": _now(), "call": self.n_calls, "tool": name, "arguments": args, "ok": bool(res.get("ok")),
                "result": _summary(name, res), "duration_s": round(dt, 3)}
        with open(self.log_path, "a") as f:
            f.write(json.dumps(line, default=str) + "\n")


def _details(builder: str, rec: dict) -> dict:
    if builder == "minerals":
        return {k: rec.get(k) for k in ("model", "supercell", "tilt_reduction")}
    if builder == "pce":
        return {k: rec.get(k) for k in ("sequences", "chain_charges", "counterions", "conformation_attempts")}
    out = {k: rec.get(k) for k in ("surface_model", "supercell", "surface_normal", "slab_thickness_A", "height_A",
                                   "orientation", "closest_pce_slab_distance_A", "slab_atoms", "pce_atoms")}
    out.update({k: rec.get("pce", {}).get(k) for k in ("sequences", "chain_charges", "counterions")})
    return out


def _summary(name: str, res: dict) -> dict:
    """The short form of a result for the log line (the full result goes to the trace, plan Day 33)."""
    if not res.get("ok"):
        return {k: res[k] for k in ("build", "stage", "error") if k in res}
    if name == "build_data_file":
        f = res["facts"]
        return {"build": res["build"], "builder": res["builder"], "atoms": f["atoms"], "net_charge_e": f["net_charge_e"],
                "elements": f["elements"]}
    if name == "get_model_info":
        return {"model": res["model"], "force_field": res["force_field"], "atoms": res["atoms"]}
    return {"kind": res["kind"]}

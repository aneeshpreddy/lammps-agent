"""Scripted stand-ins for the model, to build and test the agent loop without any API call (plan Days 29-33).

They read the task's hidden spec, so they are harness and loop checks, never results:
  perfect   looks up an example, builds the hidden spec, stops                    -> accepted in attempt 1
  fix       attempt 1 builds a defect the validator catches (a PCE without counter-ions -> net charge;
            a mineral with a mistyped model name -> a builder error it fixes within the attempt);
            after feedback it builds the hidden spec                                -> accepted in attempt 2
  stubborn  rebuilds the same defective spec whatever the feedback                 -> escalation
  runaway   keeps calling a lookup tool and never builds                           -> step and attempt limits
  wrongvalid  attempt 1 builds a valid but different system (eval/systems.py perturb_spec: one more cell,
            EO unit or acid unit); after feedback it builds the hidden spec. Without variant E the wrong
            build is accepted; with E the request check catches it
The request check's extraction call (no tools) is answered with what the hidden spec states.
Responses mimic the SDK's shape (stop_reason, content blocks, usage) with fixed token counts.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

from agents.baseline import from_builder_spec

POLICIES = ("perfect", "fix", "stubborn", "runaway", "wrongvalid")
_KIND = {"minerals": "mineral", "pce": "pce_ester", "composite": "composite"}


def _tool_input(spec: dict) -> dict:
    inp = from_builder_spec(spec)
    del inp["notes"]
    return inp


def _defective(spec: dict) -> dict:
    s = copy.deepcopy(spec)
    if s["builder"] == "minerals":
        s["model"] = s["model"].replace("_", "", 1)          # a mistyped model name: the builder refuses
    elif s["builder"] == "pce":
        s["counterion"] = None                                 # carboxylates left unneutralised
    else:
        s["pce"]["counterion"] = None
    return s


class ScriptedClient:
    def __init__(self, policy: str, task: dict):
        if policy not in POLICIES:
            raise ValueError(f"mock policy must be one of {POLICIES}")
        self.policy, self.spec = policy, task["hidden_spec"]
        self.messages = self
        self.n = 0

    # -- the SDK surface used by the loop --------------------------------------------------------
    def create(self, **kw):
        self.n += 1
        if "tools" not in kw:                                   # variant E: the request check's extraction call
            return self._text(json.dumps(_requirements(self.spec)))
        msgs = kw["messages"]
        attempt = 1 + sum(1 for m in msgs[1:] if m["role"] == "user" and _has_text(m))
        last = msgs[-1]
        last_tool = _last_tool_name(msgs) if last["role"] == "user" and not _has_text(last) else None
        last_error = _last_tool_error(last) if last_tool else False

        if self.policy == "runaway":
            return self._tool("get_model_info", {"model": "tob11_unit_cell", "force_field": "pcff"})
        if last_tool is None:                                   # start of an attempt
            if attempt == 1 and self.policy == "perfect":
                return self._tool("get_reference_example", {"kind": _KIND[self.spec["builder"]]})
            return self._build(attempt)
        if last_tool == "get_reference_example":
            return self._build(attempt)
        if last_tool == "build_data_file" and last_error:     # builder refused: fix within the attempt
            return self._tool("build_data_file", _tool_input(self.spec))
        return self._text("Built the requested system.")

    def _build(self, attempt):
        if self.policy == "wrongvalid" and attempt == 1:
            from eval.systems import perturb_spec
            return self._tool("build_data_file", _tool_input(perturb_spec(self.spec)))
        bad = self.policy == "stubborn" or (self.policy == "fix" and attempt == 1)
        return self._tool("build_data_file", _tool_input(_defective(self.spec) if bad else self.spec))

    def _tool(self, name, inp):
        return self._resp("tool_use", [SimpleNamespace(type="text", text="Calling a tool."),
                                       SimpleNamespace(type="tool_use", id=f"toolu_mock_{self.n}", name=name, input=inp)])

    def _text(self, text):
        return self._resp("end_turn", [SimpleNamespace(type="text", text=text)])

    @staticmethod
    def _resp(stop, content):
        return SimpleNamespace(stop_reason=stop, model="mock", content=content,
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=100,
                                                     cache_creation_input_tokens=0, cache_read_input_tokens=0))


def _requirements(spec: dict) -> dict:
    """Everything the hidden spec determines, in agents/checks.py REQ_SCHEMA form."""
    from agents.checks import REQ_FIELDS, built_values
    b = built_values(spec)
    req = {f: b.get(f) for f in REQ_FIELDS}
    req["anchor"] = b["anchor"][0] if len(b.get("anchor") or []) == 1 else None
    if req.get("supercell") == "auto":
        req["supercell"] = None
    return req


def _has_text(m) -> bool:
    c = m["content"]
    return isinstance(c, str) or any(isinstance(b, dict) and b.get("type") == "text" for b in c)


def _last_tool_name(msgs):
    for m in reversed(msgs):
        if m["role"] == "assistant":
            for b in m["content"]:
                if getattr(b, "type", None) == "tool_use" or (isinstance(b, dict) and b.get("type") == "tool_use"):
                    return getattr(b, "name", None) or b.get("name")
            return None
    return None


def _last_tool_error(m) -> bool:
    return any(isinstance(b, dict) and b.get("is_error") for b in m["content"])

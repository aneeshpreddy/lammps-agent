# Tool layer (plan Days 26–27)

Code: `tools/` (`toolbox.py` definitions and dispatch, `facts.py`, `examples.py`, `schema_check.py`). Tests: `tests/test_tools.py`. Checks: `scripts/tool_checks.py` (below). Version `tools-v1 (2026-10-27)`.

## The tools

The plan asks for a minimal set: every tool is a failure surface.

| Tool | Input (strict schema) | Answer | Plan candidate |
|---|---|---|---|
| `build_data_file` | the baseline's builder spec (`agents/baseline.py` `SCHEMA` without `notes`) | the DATA FILE, written in the attempt's work directory; plain facts about it (counts, elements, net charge, molecules, box) and builder details (PCE sequences and counter-ions; surface model, supercell, normal and height for a composite) | `run_generation_script(code)` |
| `get_model_info` | `model` (enum: the 28 cement-mineral models), `force_field` (`pcff` / `cvff`) | cell, kind, atom count, elements, net charge, the atom-type table (force-field type, element, mass, count, charges) and, for slabs, the normal, thickness and vacuum gap | `get_type_map()` |
| `get_reference_example` | `kind` (enum: 6 examples) | a request, the exact `build_data_file` input that answers it, and how one maps to the other | `get_reference_example(kind)` |

**Departures from the plan's candidates:**
- **Build from a spec, not a script.** `run_generation_script(code)` becomes `build_data_file(spec)`, because of design decision E (SPEC §7.3): the model never writes code or coordinate lines.
  - The spec is the baseline's own output schema, so the baseline and the agent share one vocabulary and one builder entry point (`builders/dispatch.py`).
  - Their difference is then only the tools, the feedback and the retries.
- **Type map per model.** `get_type_map()` becomes `get_model_info(model, force_field)`. The builders do all atom typing, so a type table is only useful for one concrete model.
  - For PCE, the facts returned by `build_data_file` show the composition that was built.

**Not a tool: the validator.** The orchestrator runs it after every attempt (plan, Key design decisions; CLAUDE.md). The facts the tools return are counts and sums with no tolerance and no verdict. Examples:
- `build_data_file` reports the net charge;
- it does not say whether that charge is acceptable;
- it does not run Tier 2 or 3.

**The output of an attempt** is the last successful `build_data_file` (`ToolBox.last_build`). The orchestrator validates it when the model stops calling tools (plan Day 30).

## Guarantees

- **Strict schemas.**
  - Each definition carries `strict: true`, with `additionalProperties: false` and every property `required`. Unused fields are `null` via `anyOf`.
  - Arguments returned by the API therefore match the schema (Claude API docs, structured outputs / strict tool use, read 2026-10-27).
  - Opus 5.5 rejects forced tool choice (`tool_choice` `any` / `tool`), so the loop will use `auto` and say in the prompt which tool builds the answer.
- **Checked again inside the tool.** `tools/schema_check.py` validates every call against the same schema, with no dependency. It catches:
  - direct Python calls;
  - replayed traces;
  - any client without strict mode.

  A violation is returned with its JSON path.
- **Never raises.** Every problem becomes `{"ok": false, "error": …}`, sent back as a `tool_result` with `is_error: true`:
  - unknown tool;
  - invalid arguments;
  - inconsistent spec;
  - builder refusal;
  - model not covered by the force field;
  - unexpected exception.

  The loop never crashes on a tool.
- **Deterministic and safe to retry.**
  - Builds are seeded; the knowledge tools read fixed files.
  - Each build goes to a new `build_<n>/` folder and never touches earlier ones.
  - No tool writes outside the attempt's work directory.
- **Logged.** One JSON line per call in `<workdir>/tool_calls.jsonl`, with these fields:
  - `ts` (UTC);
  - `call` (index);
  - `tool`;
  - `arguments`;
  - `ok`;
  - `result` (a summary: build name, atoms, net charge, elements, or the error);
  - `duration_s`.

  The full results go into the per-run trace (plan Day 33).
- **Per-tool timeouts:** plan Day 31 (bounds).
  - Builds take 0.1–11 s on the dev tasks.
  - The LAMMPS calls inside the builders end on their own.

## Calling the tools without an LLM

```bash
python -m tools list                                                     # definitions as sent to the API
python -m tools call get_model_info '{"model": "tob14_001_surface", "force_field": "pcff"}'
python -m tools call get_reference_example '{"kind": "composite"}'
python -m tools call build_data_file "$(cat my_spec.json)" --workdir runs/tools_manual
```

```python
from tools.toolbox import ToolBox, definitions
tb = ToolBox("runs/x")                       # one per attempt
tb.run("get_model_info", {...})              # -> dict, never raises
tb.tool_result(tool_use_block)               # -> {"type": "tool_result", "tool_use_id", "content", "is_error"}
tb.last_build                                # the attempt's output file
```

## Reference examples and the eval set

The six examples (`tools/examples.py`) were written by hand to differ from every eval task. `tests/test_tools.py` enforces this. It checks that no example shares its key parameters with any of the 22 tasks:
- for a mineral: model and supercell;
- for a PCE: monomer chemistry and composition;
- for a composite: surface model, or PCE.

The test reads the task files only to compare fingerprints and prints nothing about test tasks. The tool description also tells the model that the examples are for the format, not for the values.

## Checks (generated)

Generated by `scripts/tool_checks.py` on 2026-10-27 · git 415ebd9 (dirty) · tools-v1 (2026-10-27) · validator 1.0.0. No LLM involved.

**Reference examples:** each is built with `build_data_file` and validated (Tiers 0–3, the declared configuration of its family; no TC, there is no task reference). All must PASS.

| Example | Validator | Built | Build + validation (s) |
|---|---|---|---|
| `mineral` | PASS | 416 atoms, {'Ca': 40, 'H': 128, 'O': 200, 'Si': 48} | 0.2 |
| `pce_ester` | PASS | 281 atoms, {'C': 85, 'H': 151, 'Na': 5, 'O': 40} | 0.5 |
| `pce_ether_explicit` | PASS | 214 atoms, {'C': 65, 'Ca': 3, 'H': 114, 'O': 32} | 0.2 |
| `pce_maleic` | PASS | 248 atoms, {'C': 74, 'H': 130, 'K': 4, 'O': 40} | 0.4 |
| `pce_partial_two_chains` | PASS | 328 atoms, {'C': 100, 'H': 166, 'Na': 6, 'O': 56} | 0.4 |
| `composite` | PASS | 916 atoms, {'Al': 32, 'C': 21, 'Ca': 64, 'H': 420, 'Na': 2, 'O': 361, 'S': 16} | 0.6 |

**get_model_info:** 28 cement-mineral models × 2 force fields: 35 answered, 21 refused with the covering force field or the defect named, 0 unexpected errors.

**Log:** 68 calls, one JSON line each with arguments, call, duration_s, ok, result, tool, ts: complete.

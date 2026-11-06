# AtomForge — website

AtomForge is the local web interface to the frozen `v1.0` agent and the validator. Generation and validation only call the existing code (`agents/`, `builders/`, `validator/`); nothing in the evaluated system changed.

```bash
pip install -r web/requirements.txt     # once (Streamlit)
./web/run.sh                            # blue theme, opens http://localhost:8501
./web/run.sh violet                     # violet theme
```

## Build: Describe → Refine → Configure → Generate → Visualise & download

1. **Describe.** Write a request, or start from one of five examples.
2. **Refine (optional).** The request assistant (`assistant.py`) makes one model call. It returns the same builder spec as the single-call baseline (same schema, same builder knowledge, imported unchanged), and for every parameter it says where the value came from: **you specified**, **AI inferred** (from loose wording) or **builder default**. It also lists ambiguities with their alternatives, and anything missing. A request the builders cannot make gets an explanation, never a substitute.
   - The suggested request is written by code from the configuration (`render_prompt`), so the text and the panel cannot disagree. If you edit the text by hand, the page says so and generation uses your text.
3. **Configure.** The panel shows only the controls the system uses:
   - PCE: units, side chains, EO length, ends, protonation, chains, sequence, end groups, counter-ion, box padding;
   - mineral: model, supercell;
   - surface: model, cells, height, orientation.
   - The counter-ion count follows the builder's own rule (carboxylates ÷ ion charge). The panel warns before a request the builder would refuse, for example Ca²⁺ with an odd number of carboxylates.
4. **Generate.** The frozen agent receives the request text. Seven stages are each marked done only when the agent's trace records them.
5. **Result.** The result page shows:
   - a large 3D view with fit, zoom, spin, box, hide-H, representation, hover (element and atom ID) and PNG export;
   - a one-line description;
   - a check that the built spec matches the configuration you reviewed;
   - an assumptions table with the source of each value;
   - the status and download (data file and builder spec);
   - the molecular summary;
   - the four validation tiers with every check;
   - the technical details (run folder, trace, model, log).

- **Recent generations** reopens or reuses earlier website runs (`runs/requests/web_*`).
- **Offline mode** (Settings) replays saved runs (`runs/requests/`) and saved assistant analyses (`runs/assistant/`), with no internet.
- **Opening a saved result directly:** `http://localhost:8501/?show=<folder in runs/requests>`.

## Validate

- **Inputs:** four corrupted C3S cells that LAMMPS runs without any error or warning, the correct cell, or an uploaded file. For an uploaded file you declare the system family, force field and box shape.
- **What the page shows:**
  - LAMMPS on its own next to the validator;
  - the four tiers;
  - what is wrong;
  - every check;
  - the 3D structure.
- **Three outcomes:** valid, incomplete (a check NOT_CALIBRATED or NOT_EVALUATED, which never counts as a pass) and failed.

## About

- **What the page covers:** what AtomForge does, how it works, what it can build, and the platform reliability figures.
- **Where the figures come from:** they are read from `docs/validator_matrix.csv`, `docs/PROPERTIES.md` and the latest test run, not typed in.
- **The assistant's place:** it is an interface helper on top of the evaluated pipeline, and it is not part of the results.

## Notes

- **This Mac only.** The site listens on `localhost` (`.streamlit/config.toml`), so nobody else on the network can spend the API credits. Both the assistant and the agent need `ANTHROPIC_API_KEY` in the terminal the site is started from.
- **Bundled 3D viewer:** `assets/3Dmol-min.js`, 3Dmol.js 2.4.0 (BSD-3-Clause, https://3dmol.csb.pitt.edu), so it works offline.
- **Example files:** the `examples/` files are copies of `data/reference/minerals/c3s_unit_cell_minimized_pcff` and four of its corruptions from `data/corrupted/`.
- **Tests:** `tests/test_web_assistant.py` covers the assistant's parsing, checks and prompt writing with a fake client (no model call).

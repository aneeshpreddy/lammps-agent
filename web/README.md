# AtomForge — website

AtomForge is the local web interface to the frozen `v1.0` agent and the validator. Generation and validation only call the existing code (`agents/`, `builders/`, `validator/`); nothing in the evaluated system changed.

```bash
pip install -r web/requirements.txt     # once (Streamlit)
./web/run.sh                            # blue theme, opens http://localhost:8501
./web/run.sh violet                     # violet theme
```

## Home (the page it opens on)

- **Hero:** a live 3D view of an actual AtomForge output (an APEG-type PCE on hydroxylated C3S (040), rotating slowly) behind a faint field of drifting glow points. The glow points are decorative and are not presented as a structure.
- **As you scroll:** an introduction, then the four stages (Understand, Build, Validate, Deliver), then two identical entry cards, **Build** and **Validate**, each with a live structure.
  - The sections reveal with scroll-driven CSS: no script, and they stay visible in browsers without it.
- **Motion:** every animation stops for visitors who prefer reduced motion, and the live views pause while scrolled out of sight.
- **Navigation:** Home · Build · Validate · About tabs, and the logo also returns to Home. The browser's Back and Forward buttons move between pages (each page change adds a `?page=<name>` history entry), and a reload reopens the same page. The request, the configuration, results and Validate choices are kept across pages.

## Build: Describe → Refine → Configure → Generate → Visualise & download

1. **Describe.** Write a request, or start from one of five example cards. Each card's picture is the structure AtomForge built for that request.
2. **Refine (optional).** The request assistant (`assistant.py`) makes one model call. It returns the same builder spec as the single-call baseline (same schema, same builder knowledge, imported unchanged), and for every parameter it says where the value came from: **you specified**, **AI inferred** (from loose wording) or **builder default**. It also lists ambiguities with their alternatives, and anything missing. A request the builders cannot make gets an explanation, never a substitute.
   - The suggested request is written by code from the configuration (`render_prompt`), so the text and the panel cannot disagree. If you edit the text by hand, the page says so and generation uses your text.
3. **Configure.** The panel shows only the controls the system uses:
   - PCE: units, side chains, EO length, ends, protonation, chains, sequence, end groups, counter-ion, box padding;
   - mineral: model, supercell;
   - surface: model, cells, height, orientation.
   - The counter-ion count follows the builder's own rule (carboxylates ÷ ion charge). The panel warns before a request the builder would refuse, for example Ca²⁺ with an odd number of carboxylates.
4. **Generate.** The frozen agent receives the request text. Seven stages are each marked done only when the agent's trace records them.
5. **Result.** The result page shows:
   - a large 3D view: centred on the atoms (not on the vacuum above a slab), with the periodic box drawn as cylinders, an orientation indicator (x, y, z) and an element legend in Jmol/CPK colours. The toolbar has reset, fit, zoom, view along x/y/z, rotate, box, element labels, hide H, representation (ball and stick, sticks, space filling, lines, atoms only), hover (element and LAMMPS atom ID) and PNG export;
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

## Learn

- **A 12-step guide for first-time users:** simulations and LAMMPS; the data file section by section; bonds, angles, dihedrals and impropers; units and atom style; the two force fields; the cement minerals; PCE superplasticisers; boxes, supercells and surfaces; validation; a request builder; and a five-question quiz. A searchable glossary sits under every step.
- **Where the facts come from:**
  - data-file excerpts: a validated agent output, `examples/apeg_maleic_pcff_tutorial.data`, which can be downloaded from the page;
  - atom-type meanings: the PCFF-INTERFACE parameter file;
  - force-field styles: the builders;
  - mineral compositions: computed from the reference models;
  - PCE sequences: drawn by the builder's own `make_sequence`.
- **Background:** general context (what C3S is, what a PCE does) is labelled as such. `tests/test_web_learn.py` fails if the guide's facts drift from these files.
- **The request builder:** it writes the request with the same code as Build (`assistant.render_prompt`), and *Open this request in Build* puts it in the request box.

## About

- **What the page covers:** what AtomForge does, what a LAMMPS data file is, what it can build, how it works, the request assistant's place (an interface helper, not part of the evaluated pipeline) and technical information.
- **People, acknowledgements and references:**
  - The people: the developer, the supervisor (Adarsh P) and the professor (Prof. Aslam Kunhi Mohamed). The intros use only what the owner gave and what the faculty page states.
  - An acknowledgements note.
  - Grouped references with links (DOIs checked to resolve).
  - No model or vendor is named on this page.
- **Where the reliability figures went:** they moved off About to a single "Technical information" line at the bottom of Build. They are read from `docs/validator_matrix.csv`, `docs/PROPERTIES.md` and the latest test run, not typed in.

## Notes

- **This Mac only.** The site listens on `localhost` (`.streamlit/config.toml`), so nobody else on the network can spend the API credits. Both the assistant and the agent need `ANTHROPIC_API_KEY` in the terminal the site is started from.
- **Bundled 3D viewer:** `assets/3Dmol-min.js`, 3Dmol.js 2.4.0 (BSD-3-Clause, https://3dmol.csb.pitt.edu), inlined into each view so it works offline. Streamlit serves static `.js` files as text/plain, which browsers refuse to run.
- **Landing structures and example pictures:** `structures/*.json` and `assets/examples/*.png` are made by `python web/make_assets.py` from five accepted website runs, each listed in the script and recorded in each JSON. It needs those run folders and Playwright with Chrome. The outputs are committed, so the site does not need `runs/`.
- **Example files:** the `examples/` files are copies of `data/reference/minerals/c3s_unit_cell_minimized_pcff` and four of its corruptions from `data/corrupted/`.
- **Tests:**
  - `tests/test_web_assistant.py` covers the assistant's parsing, checks and prompt writing with a fake client (no model call).
  - `tests/test_web_viewer.py` covers the scenes, that every toolbar control is wired, and the provenance of the committed structures.

# LAMMPS Data-File Agent — website

A local web interface to the frozen `v1.0` agent and the validator. It only calls the existing code.

```bash
pip install -r web/requirements.txt     # once (Streamlit)
./web/run.sh                            # blue theme, opens http://localhost:8501
./web/run.sh violet                     # violet theme
```

- **Build a data file:** example cards or your own request, a four-stage progress bar, a 3D view, what was built, the validator tiers, a download button, and the agent's notes.
  - The agent needs `ANTHROPIC_API_KEY` in the terminal the site is started from.
  - **Offline mode** (sidebar) replays saved results for the example requests from `runs/requests/`, with no internet.
- **Check an existing data file:** the validator on four corrupted C3S cells that LAMMPS runs without any error or warning, on the correct cell, or on an uploaded file. It shows LAMMPS on its own next to the validator.
- **Opening a saved result directly:** `http://localhost:8501/?show=<folder in runs/requests>`.
- **This Mac only.** The site listens on `localhost` (`.streamlit/config.toml`), so nobody else on the network can spend the API credits.
- **Bundled 3D viewer:** `assets/3Dmol-min.js`, 3Dmol.js 2.4.0 (BSD-3-Clause, https://3dmol.csb.pitt.edu), so it works offline. The `examples/` files are copies of `data/reference/minerals/c3s_unit_cell_minimized_pcff` and four of its corruptions from `data/corrupted/`.

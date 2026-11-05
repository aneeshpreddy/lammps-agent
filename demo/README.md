# Presentation demo

A local web page around the frozen `v1.0` agent and the validator. It only calls the existing code.

```bash
pip install -r demo/requirements.txt     # once (Streamlit)
./demo/run.sh            # navy theme, opens http://localhost:8501
./demo/run.sh violet     # violet theme
```

- **Build a data file:** example buttons or your own request, the agent's steps as they happen, the "Built: …" sentence, the agent's assumptions, the validator tiers, a 3D view and a download button.
  - **Live mode** calls the model: a few cents per request. It needs `ANTHROPIC_API_KEY` in the terminal you start it from.
  - **Demo mode** replays saved runs from `runs/requests/`. It needs no internet and costs nothing, for a room with bad Wi-Fi. It replays the example requests that were run before.
- **Check any data file:** the validator on four deliberately corrupted C3S cells that LAMMPS runs without any error or warning, on the clean cell, or on an uploaded file.
- **Opening a saved result directly:** `http://localhost:8501/?show=<folder in runs/requests>`.
- **This Mac only.** The page listens on `localhost` (`.streamlit/config.toml`), so nobody else on the network can spend the API credits.
- **Bundled 3D viewer:** `assets/3Dmol-min.js`, 3Dmol.js 2.4.0 (BSD-3-Clause, https://3dmol.csb.pitt.edu), so it works offline. The `examples/` files are copies of `data/reference/minerals/c3s_unit_cell_minimized_pcff` and four of its corruptions from `data/corrupted/`.

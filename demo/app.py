"""Presentation demo: the frozen v1.0 agent and the validator in a browser page (runs locally).

  cd lammps-agent && source .venv/bin/activate
  pip install -r demo/requirements.txt          # once
  streamlit run demo/app.py                     # opens http://localhost:8501

Live mode runs the agent (needs ANTHROPIC_API_KEY in the terminal; a few cents per request). Demo mode
replays saved runs from runs/requests/ (no internet, no cost) for a room with bad Wi-Fi. The page only calls
the frozen code (agents/, validator/); it changes nothing in it.
"""
from __future__ import annotations

import csv
import datetime as _dt
import glob
import json
import os
import sys
import threading
import time

import streamlit as st
import streamlit.components.v1 as components

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents.baseline import MODEL, to_builder_spec  # noqa: E402
from agents.checks import describe_build  # noqa: E402
from agents.loop import AgentSystem, declared_config_for  # noqa: E402
from eval.harness import cost_usd, prices  # noqa: E402
from validator import load_config, validate  # noqa: E402
from validator.registry import config_for  # noqa: E402
import viewer  # noqa: E402

st.set_page_config(page_title="LAMMPS Data-File Agent", page_icon="⚛️", layout="wide")

EXAMPLES = {
    "MPEG PCE": "I need a data file for a typical MPEG-type PCE in PCFF. Methacrylic acid backbone, 20 units in total "
                "with about 25% of them carrying MPEG side chains of 45 EO, methoxy capped, random order, "
                "neutralised with sodium.",
    "C3S 2×2×2": "Give me a 2x2x2 supercell of the tricalcium silicate (C3S) unit cell in CVFF-INTERFACE.",
    "PCE on C3S surface": "Can you put a short APEG-type PCE on the hydroxylated C3S (040) surface? Something like 4 "
                          "maleic acid units alternating with 4 APEG units of 10 EO, sodium counterions, lying flat "
                          "about 3 Angstrom above the surface, PCFF, 2x2 surface cells.",
    "Three HPEG chains": "Three HPEG chains, each with 12 acrylic acid units (all deprotonated) and 6 HPEG side chains "
                         "of 23 EO units, random sequence, calcium counter-ions, PCFF-INTERFACE.",
    "Out of scope: C-S-H in CLAYFF": "Build a C-S-H model with Ca/Si ratio 1.7 including interlayer water, in CLAYFF.",
}
CHECK_EXAMPLES = [
    ("Clean: C3S unit cell (INTERFACE FF, PCFF)", "c3s_unit_cell_minimized_pcff.data",
     "The published INTERFACE FF model, as built by the project."),
    ("Two atoms 0.3 Å apart", "c3s_unit_cell_minimized_pcff__FM17__atom_moved_onto_another.data",
     "One oxygen moved almost on top of a calcium."),
    ("Masses swapped between elements", "c3s_unit_cell_minimized_pcff__FM15__masses_values_permuted.data",
     "The Masses section is shuffled: calcium gets silicon's mass and so on."),
    ("Bonds removed, header edited to match", "c3s_unit_cell_minimized_pcff__FM04__drop_bond_header_adjusted.data",
     "Two Si–O bonds deleted and the bond count lowered so the file still looks consistent."),
    ("Box tilt line missing", "c3s_unit_cell_minimized_pcff__FM10__tilt_line_dropped.data",
     "The triclinic tilt line is gone: the crystal is read in the wrong cell."),
]
LAMMPS_ALONE = {"Silent": "LAMMPS by itself reads and runs this file <b>without any error or warning</b>.",
                "Warn": "LAMMPS by itself only prints a warning.", "Loud": "LAMMPS by itself stops with an error."}
TIER_NAMES = {0: "Tier 0 · readable", 1: "Tier 1 · consistent", 2: "Tier 2 · physically plausible",
              3: "Tier 3 · LAMMPS accepts it", "TC": "TC · matches a reference"}

PALETTES = {     # page accents and 3D-viewer colours; the base theme is in .streamlit/config.toml (or --theme.* flags)
    "navy": {"bg": "#070b14", "panel": "#0d1a33", "side": "#0b1630", "border": "#1f3358", "accent": "#5aa9ff",
             "soft": "#a9d2ff", "chip": "#10284d", "chipb": "#2a5a99", "text": "#e3ecfb", "code": "#cfe3ff",
             "viewer": "#0a1222"},
    "violet": {"bg": "#0b0714", "panel": "#1a1030", "side": "#1d1238", "border": "#3b2a5c", "accent": "#a78bfa",
               "soft": "#d8ccff", "chip": "#26174d", "chipb": "#5b3fa0", "text": "#efeaff", "code": "#e4dbff",
               "viewer": "#120b22"},
}
PAL = PALETTES.get(st.query_params.get("palette") or os.environ.get("DEMO_PALETTE", "navy"), PALETTES["navy"])
st.markdown(f"""<style>
.block-container {{padding-top: 1.6rem;}}
h1, h2, h3 {{color: {PAL['text']};}}
[data-testid="stSidebar"] {{background: linear-gradient(180deg, {PAL['side']} 0%, {PAL['bg']} 100%);
                           border-right: 1px solid {PAL['border']};}}
[data-testid="stMetricValue"] {{color: {PAL['soft']};}}
.card {{border: 1px solid {PAL['border']}; border-radius: 12px; padding: 1rem 1.2rem; margin: .4rem 0 .8rem 0;
        background: {PAL['panel']};}}
.no {{color: #ff8a80; font-weight: 600;}}
.chip {{display:inline-block; padding: .18rem .65rem; margin: 0 .35rem .35rem 0; border-radius: 999px;
        background:{PAL['chip']}; color:{PAL['soft']}; font-size:.86rem; border:1px solid {PAL['chipb']};}}
.chip.bad {{background:#3a1620; color:#ffb4ab; border-color:#7a2b35;}}
.built {{font-family: ui-monospace, Menlo, monospace; font-size:.9rem; background:{PAL['panel']}; color:{PAL['code']};
         padding:.65rem .85rem; border-radius:8px; border:1px solid {PAL['border']};}}
</style>""", unsafe_allow_html=True)


# --------------------------------------------------------------------------------------------- helpers
def events(run_dir: str) -> list:
    path = os.path.join(run_dir, "trace.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass                                  # the last line may still be being written
    return out


def step_lines(evs: list) -> list:
    """The trace as short, readable steps."""
    L = ["📝 Reading the request"]
    for e in evs:
        if e["event"] == "tool":
            r = e.get("result") or {}
            if e["name"] == "build_data_file":
                if r.get("ok"):
                    f = r.get("facts", {})
                    L.append(f"🧱 Builder wrote {r.get('build')} ({f.get('atoms', '?')} atoms, net charge "
                             f"{f.get('net_charge_e', 0):+g} e)")
                else:
                    L.append(f"↩️ Builder refused: {str(r.get('error', ''))[:140]} — the agent revises the spec")
            elif e["name"] == "get_model_info":
                L.append(f"🔎 Looked up mineral model `{(e.get('input') or {}).get('model')}`")
            else:
                L.append("📖 Looked at a worked example")
        elif e["event"] == "validation":
            if e.get("verdict") == "NO_BUILD":
                continue
            L.append("✅ Validator: every Tier 0–3 check passed (LAMMPS ran it with the full force field)"
                     if e.get("passed") else
                     f"❌ Validator: {', '.join(c['property'] for c in e.get('checks', [])) or e.get('verdict')}")
        elif e["event"] == "feedback":
            L.append(f"💬 Feedback to the agent: {e['text'][:140]}")
        elif e["event"] == "stop":
            L.append("🏁 " + ("Accepted" if str(e.get("stop", "")).startswith("accepted") else str(e.get("stop"))))
    return L


def recorded() -> dict:
    """Saved runs (request text -> run folder), newest first, for demo mode."""
    out = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "runs", "requests", "*")), key=os.path.getmtime, reverse=True):
        ev = events(d)
        if ev and ev[0]["event"] == "start" and any(e["event"] == "stop" for e in ev):
            out.setdefault(ev[0]["input"].strip(), d)
    return out


@st.cache_data(show_spinner=False)
def quick_checks(path: str, spec_json: str) -> list:
    """Tier 0-2 checks of the accepted file, for the result card (Tier 3 already ran inside the loop)."""
    res = validate(path, declared_config_for(json.loads(spec_json)), run_tier3=False)
    return [(c.tier, c.property, c.verdict) for c in res.checks]


def result_card(run_dir: str):
    ev = events(run_dir)
    stop = next((e for e in reversed(ev) if e["event"] == "stop"), None)
    if not stop:
        st.warning("This run did not finish.")
        return
    builds = [e for e in ev if e["event"] == "tool" and e["name"] == "build_data_file" and (e.get("result") or {}).get("ok")]
    reply = next((" ".join(b["text"] for b in e["content"] if b.get("type") == "text")
                  for e in reversed(ev) if e["event"] == "response"
                  and any(b.get("type") == "text" and b.get("text", "").strip() for b in e["content"])), "")
    accepted = str(stop.get("stop", "")).startswith("accepted")
    usage = stop.get("usage") or {}
    cost = cost_usd(MODEL, usage, prices()) or 0.0
    data_file = os.path.join(run_dir, stop["data_file"]) if stop.get("data_file") else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Result", "Accepted" if accepted else "Declined" if "declined" in stop["stop"] else "Not accepted")
    c2.metric("Attempts", len(stop.get("attempts") or []) or 1)
    c3.metric("Time", f"{stop.get('wall_s', 0):.0f} s")
    c4.metric("Cost", f"${cost:.3f}")

    if accepted and builds and data_file:
        last = builds[-1]
        spec = to_builder_spec({**last["input"], "notes": ""})
        built = describe_build(spec, last["result"]["facts"], last["result"].get("builder_details"))
        st.markdown(f"<div class='built'>{built}</div>", unsafe_allow_html=True)
        if reply:
            with st.expander("What the agent says (including its assumptions)", expanded=True):
                st.markdown(reply)
        checks = quick_checks(data_file, json.dumps(spec))
        chips = ""
        for t in (0, 1, 2):
            n = sum(1 for c in checks if c[0] == t)
            bad = sum(1 for c in checks if c[0] == t and c[2] == "FAIL")
            chips += f"<span class='chip{' bad' if bad else ''}'>{'✓' if not bad else '✗'} {TIER_NAMES[t]} ({n} checks)</span>"
        chips += f"<span class='chip'>✓ {TIER_NAMES[3]} (full force field, run 0)</span>"
        st.markdown("**Validator** " + chips, unsafe_allow_html=True)
        left, right = st.columns([3, 1])
        with left:
            components.html(viewer.html(data_file, height=470, bg=PAL['viewer'], box=PAL['accent'], border=PAL['border']), height=480)
        with right:
            st.caption("Drag to rotate · scroll to zoom. The coloured outline is the periodic box.")
            st.download_button("⬇ Download system.data", open(data_file, "rb").read(), file_name="system.data",
                               use_container_width=True, type="primary")
            st.caption(f"Run folder: `{os.path.relpath(run_dir, ROOT)}`")
    else:
        st.markdown(f"<div class='card'><span class='no'>No file written.</span> {stop['stop']}</div>",
                    unsafe_allow_html=True)
        if reply:
            st.info(reply)


# --------------------------------------------------------------------------------------------- page
with st.sidebar:
    st.markdown("### ⚛️ LAMMPS Data-File Agent")
    st.caption("Plain-English request → validated LAMMPS data file. PCE superplasticisers, INTERFACE FF cement "
               "minerals and PCE on mineral surfaces, in CVFF- and PCFF-INTERFACE.")
    mode = st.radio("Mode", ["Live (calls the model)", "Demo (replays saved runs)"],
                    help="Demo mode needs no internet and costs nothing: it replays runs saved in runs/requests/.")
    live = mode.startswith("Live")
    if live:
        st.caption("API key: " + ("✅ found" if os.environ.get("ANTHROPIC_API_KEY") else "❌ not set in this terminal"))
    st.divider()
    st.markdown("**Results (frozen v1.0)**")
    st.metric("Held-out test tasks correct", "27 / 27")
    st.metric("Deliberately broken files caught", "948 / 948")
    st.metric("Cost per file", "≈ 1 cent")
    st.caption(f"Model: {MODEL} · validator 1.0.0 · METRICS v1.2")

st.title("From a sentence to a validated LAMMPS data file")
shown_run = st.query_params.get("show")          # ?show=<folder in runs/requests>: open a saved result directly
if shown_run and "last_run" not in st.session_state:
    st.session_state["last_run"] = os.path.join(ROOT, "runs", "requests", os.path.basename(shown_run))
tab_build, tab_check = st.tabs(["🧪 Build a data file", "🔍 Check any data file"])

with tab_build:
    st.write("Pick an example or type your own request.")
    cols = st.columns(len(EXAMPLES))
    for col, (name, text) in zip(cols, EXAMPLES.items()):
        if col.button(name, use_container_width=True):
            st.session_state["request"] = text
    request = st.text_area("Request", key="request", height=110,
                           placeholder="e.g. Build a PCFF-INTERFACE data file for an HPEG PCE with ...")
    go = st.button("Build ▶", type="primary", disabled=not (request or "").strip())

    if go:
        text = request.strip()
        if live:
            out = os.path.join(ROOT, "runs", "requests", "demo_" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
            holder = {}

            def work():
                try:
                    holder["r"] = AgentSystem()({"id": "request", "input": text}, out)
                except BaseException as e:            # SystemExit on missing credentials included
                    holder["err"] = f"{type(e).__name__}: {e}"
            th = threading.Thread(target=work, daemon=True)
            th.start()
            with st.status("The agent is working…", expanded=True) as box:
                shown = 0
                while th.is_alive():
                    lines = step_lines(events(out))
                    for line in lines[shown:]:
                        st.write(line)
                    shown = len(lines)
                    time.sleep(0.7)
                for line in step_lines(events(out))[shown:]:
                    st.write(line)
                box.update(label="Error" if "err" in holder else "Done", state="error" if "err" in holder else "complete")
            if "err" in holder:
                st.error(holder["err"])
            else:
                st.session_state["last_run"] = out
        else:
            run = recorded().get(text)
            if not run:
                st.warning("No saved run for this exact request. Pick one of the example buttons, or switch to Live mode.")
            else:
                with st.status("Replaying a saved run…", expanded=True) as box:
                    for line in step_lines(events(run)):
                        st.write(line)
                        time.sleep(0.45)
                    box.update(label="Done (replayed)", state="complete")
                st.session_state["last_run"] = run

    if st.session_state.get("last_run"):
        st.subheader("Result")
        result_card(st.session_state["last_run"])

with tab_check:
    st.write("The validator checks **any** LAMMPS data file — from this agent, EMC, Materials Studio, msi2lmp or by "
             "hand. It needs no model and no internet.")
    matrix = {}
    mpath = os.path.join(ROOT, "docs", "validator_matrix.csv")
    if os.path.exists(mpath):
        matrix = {r["id"]: r for r in csv.DictReader(open(mpath))}
    labels = [e[0] for e in CHECK_EXAMPLES] + ["Upload your own file…"]
    choice = st.radio("File", labels, horizontal=True)
    path, cfg, note = None, None, ""
    if choice == labels[-1]:
        up = st.file_uploader("LAMMPS data file", type=None)
        confs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "configs", "*.yaml")))
        conf = st.selectbox("Declared configuration (force field and system family)", confs,
                            index=confs.index("interface_pcff_pce.yaml") if "interface_pcff_pce.yaml" in confs else 0)
        if up is not None:
            path = os.path.join(ROOT, "runs", "uploads", up.name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(up.getbuffer())
            cfg = load_config(declared=os.path.join("configs", conf))
    else:
        _, fname, note = next(e for e in CHECK_EXAMPLES if e[0] == choice)
        path = os.path.join(ROOT, "demo", "examples", fname)
        cfg = config_for(path)
        st.caption(note)
        row = matrix.get(fname[:-5])
        if row and row.get("lammps_alone") in LAMMPS_ALONE:
            st.markdown(f"<div class='card'>{LAMMPS_ALONE[row['lammps_alone']]}</div>", unsafe_allow_html=True)
    tier3 = st.toggle("Include Tier 3 (run LAMMPS)", value=True)
    if path and st.button("Validate ▶", type="primary"):
        with st.spinner("Validating…"):
            res = validate(path, cfg, run_tier3=tier3)
        fails = [c for c in res.checks if c.verdict == "FAIL"]
        if res.passed:
            st.success(f"PASS — every check passed ({len(res.checks)} checks, {res.elapsed_s:.1f} s).")
        else:
            st.error(f"FAIL — {len(fails)} check(s) failed. First: {fails[0].property} · {fails[0].message[:200]}"
                     if fails else f"{res.verdict} — some checks could not be evaluated.")
        rows = sorted(res.checks, key=lambda c: (c.verdict == "PASS", str(c.tier), c.property))
        st.dataframe([{"": {"PASS": "✅", "FAIL": "❌"}.get(c.verdict, "➖"), "Tier": str(c.tier),
                       "Property": c.property, "Check": c.name.replace("_", " "), "Message": c.message[:180]}
                      for c in rows], use_container_width=True, hide_index=True, height=420)
        components.html(viewer.html(path, height=380, bg=PAL['viewer'], box=PAL['accent'], border=PAL['border']), height=390)

"""LAMMPS Data-File Agent: web interface for the frozen v1.0 agent and the validator (runs locally).

  cd lammps-agent && source .venv/bin/activate
  pip install -r web/requirements.txt           # once
  ./web/run.sh [navy|violet]                    # opens http://localhost:8501

The agent calls the model (ANTHROPIC_API_KEY must be set in the terminal). Offline mode replays results saved in
runs/requests/ and needs no internet. The page only calls the frozen code (agents/, validator/).
"""
from __future__ import annotations

import csv
import datetime as _dt
import glob
import html as _html
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
from agents.checks import built_values  # noqa: E402
from agents.loop import AgentSystem, declared_config_for  # noqa: E402
from eval.analyse import canonical, chem_name  # noqa: E402
from validator import load_config, validate  # noqa: E402
from validator.registry import config_for  # noqa: E402
import viewer  # noqa: E402

st.set_page_config(page_title="LAMMPS Data-File Agent", page_icon="⚛️", layout="wide",
                   initial_sidebar_state="expanded")

EXAMPLES = [
    ("🧬", "MPEG-type PCE", "20 units, 25 % MPEG side chains of 45 EO, Na⁺",
     "I need a data file for a typical MPEG-type PCE in PCFF. Methacrylic acid backbone, 20 units in total with about "
     "25% of them carrying MPEG side chains of 45 EO, methoxy capped, random order, neutralised with sodium."),
    ("💎", "C3S supercell", "Tricalcium silicate, 2 × 2 × 2, CVFF-INTERFACE",
     "Give me a 2x2x2 supercell of the tricalcium silicate (C3S) unit cell in CVFF-INTERFACE."),
    ("🪨", "PCE on a C3S surface", "APEG–maleic PCE lying flat on C3S (040)",
     "Can you put a short APEG-type PCE on the hydroxylated C3S (040) surface? Something like 4 maleic acid units "
     "alternating with 4 APEG units of 10 EO, sodium counterions, lying flat about 3 Angstrom above the surface, "
     "PCFF, 2x2 surface cells."),
    ("🔗", "Three HPEG chains", "Multi-chain system with Ca²⁺ counter-ions",
     "Three HPEG chains, each with 12 acrylic acid units (all deprotonated) and 6 HPEG side chains of 23 EO units, "
     "random sequence, calcium counter-ions, PCFF-INTERFACE."),
    ("🚫", "Outside the scope", "C-S-H in CLAYFF: the agent declines",
     "Build a C-S-H model with Ca/Si ratio 1.7 including interlayer water, in CLAYFF."),
]
CHECK_FILES = [
    ("Two atoms 0.3 Å apart", "c3s_unit_cell_minimized_pcff__FM17__atom_moved_onto_another.data",
     "An oxygen atom moved almost on top of a calcium atom."),
    ("Masses swapped between elements", "c3s_unit_cell_minimized_pcff__FM15__masses_values_permuted.data",
     "The Masses section is shuffled: calcium carries silicon's mass, and so on."),
    ("Bonds removed, header edited to match", "c3s_unit_cell_minimized_pcff__FM04__drop_bond_header_adjusted.data",
     "Two Si–O bonds are deleted and the bond count lowered, so the file still looks consistent."),
    ("Box tilt line missing", "c3s_unit_cell_minimized_pcff__FM10__tilt_line_dropped.data",
     "The triclinic tilt line is gone, so the crystal is read in the wrong cell."),
    ("Correct file: C3S unit cell", "c3s_unit_cell_minimized_pcff.data",
     "The published INTERFACE FF model, as built by this project."),
]
LAMMPS_ALONE = {"Silent": ("Runs", "No error and no warning: the problem goes unnoticed."),
                "Warn": ("Runs, with a warning", "Only a warning that is easy to miss."),
                "Loud": ("Stops", "LAMMPS stops with an error."),
                "Loud@run": ("Stops when run", "LAMMPS stops once the simulation starts.")}
TIERS = [(0, "Readable", "syntax and sections"), (1, "Consistent", "counts, IDs, topology"),
         (2, "Physically plausible", "charge, overlaps, bonds, density"), (3, "Accepted by LAMMPS", "full force field")]

PALETTES = {     # page colours and 3D-viewer colours; the base theme is in .streamlit/config.toml (or --theme.* flags)
    "navy": {"bg": "#070b14", "panel": "#0d1a33", "panel2": "#0a1428", "side": "#0b1630", "border": "#1f3358",
             "accent": "#5aa9ff", "accent2": "#2f7de1", "soft": "#a9d2ff", "muted": "#8ea3c4", "text": "#e3ecfb",
             "viewer": "#0a1222"},
    "violet": {"bg": "#0b0714", "panel": "#1a1030", "panel2": "#140c26", "side": "#1d1238", "border": "#3b2a5c",
               "accent": "#a78bfa", "accent2": "#7c5ce6", "soft": "#d8ccff", "muted": "#a99cc8", "text": "#efeaff",
               "viewer": "#120b22"},
}
P = PALETTES.get(st.query_params.get("palette") or os.environ.get("APP_PALETTE", "navy"), PALETTES["navy"])
OK, BAD, WARN = "#4ade80", "#f87171", "#fbbf24"

st.markdown(f"""<style>
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{display: none !important;}}
header[data-testid="stHeader"] {{background: transparent;}}
.block-container {{padding-top: 2.2rem; max-width: 1320px;}}
html, body, [class*="css"] {{font-family: -apple-system, "Inter", "Segoe UI", Roboto, sans-serif;}}
[data-testid="stSidebar"] {{background: linear-gradient(180deg, {P['side']} 0%, {P['bg']} 100%);
                            border-right: 1px solid {P['border']};}}
.hero h1 {{font-size: 2.35rem; font-weight: 750; letter-spacing: -.02em; margin: 0 0 .3rem 0; color: {P['text']};}}
.hero p {{color: {P['muted']}; font-size: 1.05rem; margin: 0 0 1.2rem 0; max-width: 820px;}}
.kpis {{display: grid; grid-template-columns: repeat(4, 1fr); gap: .8rem; margin: .4rem 0 1.4rem 0;}}
.kpi {{background: linear-gradient(160deg, {P['panel']} 0%, {P['panel2']} 100%); border: 1px solid {P['border']};
       border-radius: 14px; padding: .9rem 1.1rem;}}
.kpi .v {{font-size: 1.7rem; font-weight: 700; color: {P['soft']}; line-height: 1.15;}}
.kpi .l {{font-size: .84rem; color: {P['muted']}; margin-top: .2rem;}}
.section {{font-size: .78rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
           color: {P['accent']}; margin: 1.1rem 0 .55rem 0;}}
.ex {{background: {P['panel2']}; border: 1px solid {P['border']}; border-radius: 14px; padding: .85rem .95rem .3rem .95rem;
      min-height: 118px;}}
.ex .i {{font-size: 1.35rem;}} .ex .t {{font-weight: 650; color: {P['text']}; margin-top: .25rem;}}
.ex .d {{font-size: .82rem; color: {P['muted']}; margin-top: .15rem; line-height: 1.35;}}
.stepper {{display: flex; gap: .5rem; margin: .4rem 0 .6rem 0;}}
.step {{flex: 1; border-radius: 12px; padding: .65rem .8rem; border: 1px solid {P['border']}; background: {P['panel2']};
        color: {P['muted']}; font-size: .9rem;}}
.step b {{display: block; font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; margin-bottom: .15rem;}}
.step.done {{border-color: {P['accent2']}; color: {P['text']}; background: {P['panel']};}}
.step.done b {{color: {P['accent']};}}
.step.active {{border-color: {P['accent']}; color: {P['text']}; box-shadow: 0 0 0 2px {P['accent']}33;}}
.step.stopped {{border-color: {WARN}88; color: {P['text']};}}
.badge {{display: inline-flex; align-items: center; gap: .45rem; padding: .35rem .8rem; border-radius: 999px;
         font-weight: 650; font-size: .95rem;}}
.badge.ok {{background: {OK}1f; color: {OK}; border: 1px solid {OK}55;}}
.badge.bad {{background: {BAD}1f; color: {BAD}; border: 1px solid {BAD}55;}}
.badge.warn {{background: {WARN}1f; color: {WARN}; border: 1px solid {WARN}55;}}
.panel {{background: {P['panel2']}; border: 1px solid {P['border']}; border-radius: 14px; padding: 1rem 1.15rem;
         margin-bottom: .8rem;}}
.panel h4 {{margin: 0 0 .55rem 0; font-size: .78rem; letter-spacing: .09em; text-transform: uppercase; color: {P['accent']};}}
.kv {{display: grid; grid-template-columns: 38% 62%; row-gap: .38rem; font-size: .92rem;}}
.kv .k {{color: {P['muted']};}} .kv .v {{color: {P['text']};}}
.tier {{display: flex; align-items: center; gap: .6rem; padding: .32rem 0; font-size: .92rem; color: {P['text']};}}
.tier .s {{color: {P['muted']}; font-size: .8rem;}}
.dot {{width: 1.35rem; height: 1.35rem; border-radius: 50%; display: inline-flex; align-items: center;
       justify-content: center; font-size: .78rem; font-weight: 800;}}
.dot.ok {{background: {OK}26; color: {OK};}} .dot.bad {{background: {BAD}26; color: {BAD};}}
.vs {{display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; margin-bottom: .8rem;}}
.vs .card {{border-radius: 14px; padding: 1rem 1.15rem; border: 1px solid {P['border']}; background: {P['panel2']};}}
.vs .card .h {{font-size: .78rem; letter-spacing: .09em; text-transform: uppercase; color: {P['muted']};}}
.vs .card .big {{font-size: 1.45rem; font-weight: 700; margin: .25rem 0;}}
.vs .card .sub {{color: {P['muted']}; font-size: .9rem;}}
.issue {{border-left: 3px solid {BAD}; background: {BAD}12; border-radius: 8px; padding: .6rem .85rem; margin: .45rem 0;}}
.issue .p {{font-weight: 700; color: {BAD}; font-size: .85rem;}} .issue .m {{color: {P['text']}; font-size: .9rem;}}
.note {{color: {P['muted']}; font-size: .86rem;}}
.side-brand {{font-weight: 750; font-size: 1.1rem; color: {P['text']};}}
.chips span {{display: inline-block; margin: 0 .3rem .35rem 0; padding: .15rem .6rem; border-radius: 999px;
              font-size: .78rem; color: {P['soft']}; border: 1px solid {P['border']}; background: {P['panel2']};}}
div.stButton > button {{border-radius: 10px;}}
button[data-baseweb="tab"] p {{font-size: 1.08rem; font-weight: 600;}}
button[data-baseweb="tab"] {{padding: .4rem 1.1rem .55rem 0;}}
</style>""", unsafe_allow_html=True)


# --------------------------------------------------------------------------------------------- helpers
def esc(x) -> str:
    return _html.escape(str(x))


def events(run_dir: str) -> list:
    path = os.path.join(run_dir, "trace.jsonl")
    out = []
    if os.path.exists(path):
        for line in open(path):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass                              # the last line may still be being written
    return out


def stages(evs: list) -> list:
    """The four stages and their state: done / active / pending / stopped."""
    responded = any(e["event"] == "response" for e in evs)
    built = any(e["event"] == "tool" and e["name"] == "build_data_file" and (e.get("result") or {}).get("ok") for e in evs)
    passed = any(e["event"] == "validation" and e.get("passed") for e in evs)
    stop = next((e for e in evs if e["event"] == "stop"), None)
    accepted = bool(stop) and str(stop.get("stop", "")).startswith("accepted")
    declined = bool(stop) and not accepted
    names = [("Understand", "Reading the request"), ("Build", "Deterministic builders"),
             ("Validate", "Tier 0–3 checks + LAMMPS"), ("Ready", "File delivered")]
    state = ["done" if responded else "active",
             "done" if built else ("pending" if declined else "active" if responded else "pending"),
             "done" if passed else ("pending" if declined else "active" if built else "pending"),
             "done" if accepted else ("stopped" if declined else "active" if passed else "pending")]
    if declined:
        names[3] = ("Declined", "Not something the builders can make")
    return list(zip(names, state))


def stepper_html(evs: list) -> str:
    cells = "".join(f"<div class='step {s}'><b>{'✓ ' if s == 'done' else ''}{esc(n)}</b>{esc(d)}</div>"
                    for (n, d), s in stages(evs))
    return f"<div class='stepper'>{cells}</div>"


def log_lines(evs: list) -> list:
    L = []
    for e in evs:
        if e["event"] == "tool":
            r = e.get("result") or {}
            if e["name"] == "build_data_file":
                L.append(f"Builder wrote {r.get('build')}: {r.get('facts', {}).get('atoms', '?')} atoms" if r.get("ok")
                         else f"Builder refused: {str(r.get('error', ''))[:160]} — the agent revises the specification")
            elif e["name"] == "get_model_info":
                L.append(f"Looked up mineral model {(e.get('input') or {}).get('model')}")
            else:
                L.append("Consulted a worked example")
        elif e["event"] == "validation" and e.get("verdict") != "NO_BUILD":
            L.append("Validator: every Tier 0–3 check passed" if e.get("passed") else
                     "Validator: " + (", ".join(c["property"] for c in e.get("checks", [])) or e.get("verdict")))
        elif e["event"] == "feedback":
            L.append("Feedback to the agent: " + e["text"][:160])
    return L


def recorded() -> dict:
    out = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "runs", "requests", "*")), key=os.path.getmtime, reverse=True):
        ev = events(d)
        if ev and ev[0]["event"] == "start" and any(e["event"] == "stop" for e in ev):
            out.setdefault(ev[0]["input"].strip(), d)
    return out


@st.cache_data(show_spinner=False)
def tier_counts(path: str, spec_json: str) -> dict:
    """Tier 0-2 checks of the accepted file for the result panel (Tier 3 ran inside the agent's loop)."""
    res = validate(path, declared_config_for(json.loads(spec_json)), run_tier3=False)
    return {t: (sum(1 for c in res.checks if c.tier == t), sum(1 for c in res.checks if c.tier == t and c.verdict == "FAIL"))
            for t in (0, 1, 2)}


def spec_rows(spec: dict, facts: dict, details: dict) -> list:
    ff = {"pcff": "PCFF-INTERFACE (class II)", "cvff": "CVFF-INTERFACE (class I)"}[spec["force_field"]]
    if spec["builder"] == "minerals":
        rows = [("System", "Cement mineral"), ("Model", spec["model"]), ("Force field", ff),
                ("Supercell", " × ".join(map(str, spec["supercell"])))]
    else:
        b = built_values(spec, details)
        c = canonical(spec)
        units = c["pce.units" if spec["builder"] == "composite" else "units"]
        rows = [("System", "PCE superplasticiser" + (" on a mineral surface" if spec["builder"] == "composite" else "")),
                ("Force field", ff), ("Chains", b["n_chains"]),
                ("Backbone per chain", f"{b['backbone_units_per_chain']} units"),
                ("Units", "<br>".join(f"{n} × {esc(chem_name(u))}" for u, n in sorted(units.items(), key=lambda x: -x[1]))),
                ("Sequence", b["sequence"]), ("Counter-ion", b["counterion"] or "none")]
        if spec["builder"] == "composite":
            sc = b["supercell"] if b["supercell"] == "auto" else " × ".join(map(str, b["supercell"]))
            rows += [("Surface", spec["surface"]["model"]), ("Surface cells", sc),
                     ("Placement", f"{b['height_A']:g} Å above the surface, {b['orientation']}")]
    box = " × ".join(f"{x:.1f}" for x in facts["box_A"]["lengths"])
    rows += [("Atoms", f"{facts['atoms']:,}"), ("Net charge", f"{facts['net_charge_e']:+g} e"), ("Box", f"{box} Å")]
    return rows


def kv_html(rows: list) -> str:
    return "<div class='kv'>" + "".join(f"<div class='k'>{esc(k)}</div><div class='v'>{v if '<br>' in str(v) else esc(v)}</div>"
                                        for k, v in rows) + "</div>"


def result_view(run_dir: str):
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
    data_file = os.path.join(run_dir, stop["data_file"]) if stop.get("data_file") else None
    st.markdown(stepper_html(ev), unsafe_allow_html=True)

    if not (accepted and builds and data_file):
        st.markdown(f"<div class='panel'><span class='badge warn'>⏹ {'Declined' if 'declined' in stop['stop'] else 'Not accepted'}"
                    f"</span><p class='note' style='margin-top:.6rem'>No file was written. Nothing is substituted for a "
                    f"request the builders cannot make.</p></div>", unsafe_allow_html=True)
        if reply:
            st.markdown(f"<div class='panel'><h4>The agent's explanation</h4><div style='line-height:1.6'>"
                        f"{esc(reply).replace(chr(10), '<br>')}</div></div>", unsafe_allow_html=True)
        return

    last = builds[-1]
    spec = to_builder_spec({**last["input"], "notes": ""})
    facts, details = last["result"]["facts"], last["result"].get("builder_details")
    left, right = st.columns([1.45, 1], gap="large")
    with left:
        components.html(viewer.html(data_file, height=560, bg=P["viewer"], box=P["accent"], border=P["border"]), height=570)
        st.markdown("<p class='note'>Drag to rotate · scroll to zoom · the coloured outline is the periodic box.</p>",
                    unsafe_allow_html=True)
    with right:
        n_att = len(stop.get("attempts") or []) or 1
        st.markdown(f"<span class='badge ok'>✓ Validated data file</span>"
                    f"<span class='note' style='margin-left:.7rem'>{n_att} attempt{'s' if n_att > 1 else ''} · "
                    f"{stop.get('wall_s', 0):.0f} s</span>", unsafe_allow_html=True)
        st.markdown(f"<div class='panel' style='margin-top:.8rem'><h4>What was built</h4>{kv_html(spec_rows(spec, facts, details))}</div>",
                    unsafe_allow_html=True)
        counts = tier_counts(data_file, json.dumps(spec))
        tiers = ""
        for t, name, sub in TIERS:
            n, bad = counts.get(t, (0, 0))
            label = f"{n} checks" if t < 3 else "read_data + run 0"
            tiers += (f"<div class='tier'><span class='dot {'bad' if bad else 'ok'}'>{'✕' if bad else '✓'}</span>"
                      f"<span>Tier {t} · {esc(name)} <span class='s'>· {esc(sub)} · {label}</span></span></div>")
        st.markdown(f"<div class='panel'><h4>Validator</h4>{tiers}</div>", unsafe_allow_html=True)
        st.download_button("⬇  Download LAMMPS data file", open(data_file, "rb").read(), file_name="system.data",
                           use_container_width=True, type="primary")
    if reply:
        with st.expander("The agent's notes, including what it assumed", expanded=False):
            st.markdown(reply)
    with st.expander("Technical details"):
        st.markdown(f"Run folder `{os.path.relpath(run_dir, ROOT)}` · trace `trace.jsonl` · model `{MODEL}`")
        for line in log_lines(ev):
            st.markdown(f"- {line}")


# --------------------------------------------------------------------------------------------- page
with st.sidebar:
    st.markdown("<div class='side-brand'>⚛️ LAMMPS Data-File Agent</div>", unsafe_allow_html=True)
    st.markdown("<p class='note'>Describe a cementitious system in plain English and get a LAMMPS data file that has "
                "passed every check of a deterministic validator.</p>", unsafe_allow_html=True)
    offline = st.toggle("Offline mode", value=False,
                        help="Replays results saved earlier for the example requests. Needs no internet connection.")
    if not offline:
        ok_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        st.markdown(f"<p class='note'>{'🟢 Connected to the model' if ok_key else '🔴 No API key in this terminal'}</p>",
                    unsafe_allow_html=True)
    else:
        st.markdown("<p class='note'>⚪ Showing saved results</p>", unsafe_allow_html=True)
    st.markdown("<div class='section'>Scope</div><div class='chips'><span>PCE · any architecture</span>"
                "<span>INTERFACE FF cement minerals</span><span>PCE on mineral surfaces</span><span>CVFF-INTERFACE</span>"
                "<span>PCFF-INTERFACE</span></div>", unsafe_allow_html=True)
    st.markdown("<div class='section'>How it works</div><p class='note'>1. A language model reads the request and "
                "writes a structured specification.<br>2. Deterministic builders create the atoms, topology and force-field "
                "parameters.<br>3. A validator checks the file in four tiers, including LAMMPS itself.<br>4. Only a file "
                "that passes every check is delivered.</p>", unsafe_allow_html=True)
    st.markdown(f"<p class='note' style='margin-top:1.2rem'>Version 1.0 · validator 1.0.0 · INTERFACE FF 1.5 · "
                f"LAMMPS 22 Jul 2025</p>", unsafe_allow_html=True)

st.markdown("""<div class='hero'><h1>From a sentence to a validated LAMMPS data file</h1>
<p>PCE superplasticisers, cement minerals and their interfaces — built by deterministic tools, chosen by a language
model, and certified by a validator that checks every file before you see it.</p></div>""", unsafe_allow_html=True)
st.markdown("""<div class='kpis'>
<div class='kpi'><div class='v'>27 / 27</div><div class='l'>held-out test runs: valid and exactly the requested system</div></div>
<div class='kpi'><div class='v'>948 / 948</div><div class='l'>deliberately corrupted files caught by the validator</div></div>
<div class='kpi'><div class='v'>44</div><div class='l'>properties checked in four tiers, LAMMPS included</div></div>
<div class='kpi'><div class='v'>≈ 20 s</div><div class='l'>typical time from request to validated file</div></div>
</div>""", unsafe_allow_html=True)

shown_run = st.query_params.get("show")          # ?show=<folder in runs/requests>: open a saved result directly
if shown_run and "last_run" not in st.session_state:
    st.session_state["last_run"] = os.path.join(ROOT, "runs", "requests", os.path.basename(shown_run))

tab_build, tab_check = st.tabs(["Build a data file", "Check an existing data file"])

with tab_build:
    st.markdown("<div class='section'>Start from an example</div>", unsafe_allow_html=True)
    cols = st.columns(len(EXAMPLES), gap="small")
    for col, (icon, title, desc, text) in zip(cols, EXAMPLES):
        with col:
            st.markdown(f"<div class='ex'><div class='i'>{icon}</div><div class='t'>{esc(title)}</div>"
                        f"<div class='d'>{esc(desc)}</div></div>", unsafe_allow_html=True)
            if st.button("Use this request", key=f"ex_{title}", use_container_width=True):
                st.session_state["request"] = text
    st.markdown("<div class='section'>Or describe your system</div>", unsafe_allow_html=True)
    request = st.text_area("Request", key="request", height=105, label_visibility="collapsed",
                           placeholder="For example: a PCFF-INTERFACE data file for an HPEG PCE with 10 acrylic acid units "
                                       "and 5 side chains of 23 EO, random sequence, sodium counter-ions.")
    b1, _ = st.columns([1, 4])
    go = b1.button("Build data file  →", type="primary", disabled=not (request or "").strip(), use_container_width=True)

    if go:
        text = request.strip()
        st.session_state.pop("last_run", None)
        if not offline:
            out = os.path.join(ROOT, "runs", "requests", "web_" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
            holder = {}

            def work():
                try:
                    holder["r"] = AgentSystem()({"id": "request", "input": text}, out)
                except BaseException as e:            # SystemExit on missing credentials included
                    holder["err"] = f"{type(e).__name__}: {e}"
            th = threading.Thread(target=work, daemon=True)
            th.start()
            box = st.empty()
            while th.is_alive():
                box.markdown(stepper_html(events(out)), unsafe_allow_html=True)
                time.sleep(0.6)
            box.empty()
            if "err" in holder:
                st.error("The agent could not run: " + holder["err"])
            else:
                st.session_state["last_run"] = out
        else:
            run = recorded().get(text)
            if not run:
                st.info("Offline mode shows saved results for the example requests. Choose one of the examples above, "
                        "or switch offline mode off.")
            else:
                box = st.empty()
                ev = events(run)
                for k in range(1, len(ev) + 1):
                    box.markdown(stepper_html(ev[:k]), unsafe_allow_html=True)
                    time.sleep(0.12)
                box.empty()
                st.session_state["last_run"] = run

    if st.session_state.get("last_run"):
        st.markdown("<div class='section'>Result</div>", unsafe_allow_html=True)
        result_view(st.session_state["last_run"])

with tab_check:
    st.markdown("<p class='note' style='font-size:1rem'>The validator checks any LAMMPS data file — from this agent, "
                "EMC, Materials Studio, msi2lmp or written by hand. It runs locally and needs no internet.</p>",
                unsafe_allow_html=True)
    matrix = {}
    mpath = os.path.join(ROOT, "docs", "validator_matrix.csv")
    if os.path.exists(mpath):
        matrix = {r["id"]: r for r in csv.DictReader(open(mpath))}
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown("<div class='section'>Choose a file</div>", unsafe_allow_html=True)
        labels = [f[0] for f in CHECK_FILES] + ["Upload your own file"]
        choice = st.radio("File", labels, label_visibility="collapsed")
        path, cfg, row = None, None, None
        if choice == labels[-1]:
            up = st.file_uploader("LAMMPS data file", label_visibility="collapsed")
            confs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "configs", "*.yaml")))
            conf = st.selectbox("Force field and system family", confs,
                                index=confs.index("interface_pcff_pce.yaml") if "interface_pcff_pce.yaml" in confs else 0)
            if up is not None:
                path = os.path.join(ROOT, "runs", "uploads", up.name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(up.getbuffer())
                cfg = load_config(declared=os.path.join("configs", conf))
        else:
            _, fname, note = next(f for f in CHECK_FILES if f[0] == choice)
            path = os.path.join(ROOT, "web", "examples", fname)
            cfg = config_for(path)
            row = matrix.get(fname[:-5])
            st.markdown(f"<p class='note'>{esc(note)}</p>", unsafe_allow_html=True)
        tier3 = st.toggle("Run LAMMPS as well (Tier 3)", value=True)
        if path and st.button("Validate  →", type="primary", use_container_width=True):
            with st.spinner("Checking the file…"):
                st.session_state["check"] = (path, validate(path, cfg, run_tier3=tier3), row)
    with right:
        chk = st.session_state.get("check")
        if not chk or chk[0] != path:
            st.markdown("<div class='panel'><h4>How to read the result</h4><p class='note'>On the left, LAMMPS on its "
                        "own; on the right, this validator. The corrupted examples are all files that LAMMPS reads and "
                        "runs <b>without any error or warning</b>.</p></div>", unsafe_allow_html=True)
        else:
            _, res, row = chk
            fails = [c for c in res.checks if c.verdict == "FAIL"]
            lam = LAMMPS_ALONE.get((row or {}).get("lammps_alone", ""), None)
            if row and row.get("kind") == "positive":
                lam = ("Runs", "A correct file runs normally.")
            lam_html = (f"<div class='card'><div class='h'>LAMMPS on its own</div><div class='big' style='color:{WARN if lam and lam[0].startswith('Runs') and fails else P['soft']}'>"
                        f"{esc(lam[0])}</div><div class='sub'>{esc(lam[1])}</div></div>" if lam else
                        "<div class='card'><div class='h'>LAMMPS on its own</div><div class='big'>—</div>"
                        "<div class='sub'>Not measured for an uploaded file.</div></div>")
            val_html = (f"<div class='card'><div class='h'>This validator</div><div class='big' style='color:{OK}'>✓ Passed</div>"
                        f"<div class='sub'>All {len(res.checks)} checks passed.</div></div>" if res.passed else
                        f"<div class='card'><div class='h'>This validator</div><div class='big' style='color:{BAD}'>✕ Rejected</div>"
                        f"<div class='sub'>{len(fails)} check{'s' if len(fails) != 1 else ''} failed — explained below.</div></div>")
            st.markdown(f"<div class='vs'>{lam_html}{val_html}</div>", unsafe_allow_html=True)
            tiers = ""
            for t, name, sub in TIERS:
                checks = [c for c in res.checks if c.tier == t]
                bad = [c for c in checks if c.verdict == "FAIL"]
                if not checks:
                    continue
                tiers += (f"<div class='tier'><span class='dot {'bad' if bad else 'ok'}'>{'✕' if bad else '✓'}</span>"
                          f"<span>Tier {t} · {esc(name)} <span class='s'>· {len(checks)} checks"
                          f"{f' · {len(bad)} failed' if bad else ''}</span></span></div>")
            st.markdown(f"<div class='panel'><h4>Tiers</h4>{tiers}</div>", unsafe_allow_html=True)
            if fails:
                st.markdown("<div class='section'>What is wrong</div>", unsafe_allow_html=True)
                for c in fails[:6]:
                    st.markdown(f"<div class='issue'><div class='p'>{esc(c.property)} · {esc(c.name.replace('_', ' '))}</div>"
                                f"<div class='m'>{esc(c.message[:300])}</div></div>", unsafe_allow_html=True)
            with st.expander(f"All {len(res.checks)} checks"):
                rows = sorted(res.checks, key=lambda c: (c.verdict == "PASS", str(c.tier), c.property))
                st.dataframe([{"": {"PASS": "✓", "FAIL": "✕"}.get(c.verdict, "–"), "Tier": str(c.tier),
                               "Property": c.property, "Check": c.name.replace("_", " "), "Message": c.message[:180]}
                              for c in rows], use_container_width=True, hide_index=True, height=360)
            components.html(viewer.html(path, height=360, bg=P["viewer"], box=P["accent"], border=P["border"]), height=370)

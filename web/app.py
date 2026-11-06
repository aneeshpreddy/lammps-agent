"""AtomForge: the web interface for the frozen v1.0 agent and the validator (runs locally).

  cd lammps-agent && source .venv/bin/activate
  pip install -r web/requirements.txt           # once
  ./web/run.sh [violet]                         # opens http://localhost:8501

Generation calls the frozen agent (agents/loop.py AgentSystem) and the validator, unchanged. The request
assistant (web/assistant.py) is an interface helper that turns a loose request into an explicit one; the agent
then builds from that text. ANTHROPIC_API_KEY must be set in the terminal; offline mode replays saved runs
(runs/requests/) and saved assistant analyses (runs/assistant/) and needs no internet.
"""
from __future__ import annotations

import copy
import csv
import datetime as _dt
import difflib
import glob
import html as _html
import json
import os
import re
import statistics
import sys
import threading
import time

import streamlit as st
import streamlit.components.v1 as components

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents.baseline import MODEL, to_builder_spec  # noqa: E402
from agents.loop import AgentSystem, declared_config_for  # noqa: E402
from eval.analyse import spec_diff  # noqa: E402
from validator import load_config, validate  # noqa: E402
from validator.registry import config_for  # noqa: E402
import assistant as A  # noqa: E402
import viewer  # noqa: E402

st.set_page_config(page_title="AtomForge", page_icon="⚛️", layout="wide", initial_sidebar_state="collapsed")

EXAMPLES = [
    ("MPEG-type PCE", "I need a data file for a typical MPEG-type PCE in PCFF. Methacrylic acid backbone, 20 units in "
     "total with about 25% of them carrying MPEG side chains of 45 EO, methoxy capped, random order, neutralised with sodium."),
    ("C3S supercell", "Give me a 2x2x2 supercell of the tricalcium silicate (C3S) unit cell in CVFF-INTERFACE."),
    ("PCE on a C3S surface", "Can you put a short APEG-type PCE on the hydroxylated C3S (040) surface? Something like 4 "
     "maleic acid units alternating with 4 APEG units of 10 EO, sodium counterions, lying flat about 3 Angstrom above "
     "the surface, PCFF, 2x2 surface cells."),
    ("Three HPEG chains", "Three HPEG chains, each with 12 acrylic acid units (all deprotonated) and 6 HPEG side chains "
     "of 23 EO units, random sequence, calcium counter-ions, PCFF-INTERFACE."),
    ("A loosely worded request", "short APEG superplasticizer, maybe 6 maleic and 6 APEG units with 10 EO each, sodium, pcff"),
]
PLACEHOLDER = ("Build a PCE superplasticizer using PCFF-INTERFACE with 20 acrylic acid backbone units, 5 MPEG side "
               "chains of 45 EO units, random sequence and sodium counter-ions.")
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
CONFIG_NAMES = {"interface_pcff_pce.yaml": "PCE · PCFF-INTERFACE", "interface_cvff_pce.yaml": "PCE · CVFF-INTERFACE",
                "interface_pcff_minerals.yaml": "Cement mineral · PCFF-INTERFACE",
                "interface_cvff_minerals.yaml": "Cement mineral · CVFF-INTERFACE",
                "interface_pcff_composite.yaml": "PCE on a mineral surface · PCFF-INTERFACE",
                "interface_cvff_composite.yaml": "PCE on a mineral surface · CVFF-INTERFACE",
                "interface_pcff_tobermorite.yaml": "Tobermorite · PCFF-INTERFACE",
                "emc_pcff_real_full.yaml": "EMC-built PCE · PCFF (real units)",
                "interface_pcff_fixture.yaml": "Synthetic tobermorite test fixtures"}
TIERS = [(0, "Readability", "Header, sections, numbers and columns can be parsed"),
         (1, "Structural consistency", "Counts, unique IDs, topology references, coefficients"),
         (2, "Physical plausibility", "Charge, overlaps, bond lengths, density, cell"),
         (3, "LAMMPS compatibility", "read_data and run 0 with the full force field")]
SOURCES = {"stated": ("You specified", "src-stated"), "inferred": ("AI inferred · check", "src-inferred"),
           "default": ("Builder default", "src-default"), "edited": ("You edited", "src-edited"),
           None: ("Not reported", "src-none")}

PALETTES = {     # design tokens; the base Streamlit theme is in .streamlit/config.toml (or --theme.* flags in run.sh)
    "navy": {"bg": "#0a0e16", "surface": "#111827", "surface2": "#0d1320", "raised": "#162033", "border": "#1f2a3d",
             "border2": "#2a3852", "accent": "#38bdf8", "accent2": "#3b82f6", "text": "#e6edf7", "muted": "#8b9bb4",
             "faint": "#5d6b84", "viewer": "#0b111c"},
    "violet": {"bg": "#0d0a16", "surface": "#161127", "surface2": "#110d20", "raised": "#1e1733", "border": "#2a2140",
               "border2": "#3a2f57", "accent": "#a78bfa", "accent2": "#7c5ce6", "text": "#efeaff", "muted": "#a99cc8",
               "faint": "#6f6390", "viewer": "#100c1c"},
}
P = PALETTES.get(st.query_params.get("palette") or os.environ.get("APP_PALETTE", "navy"), PALETTES["navy"])
OK, BAD, WARN = "#34d399", "#f87171", "#fbbf24"

st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebarCollapsedControl"] {{display:none !important;}}
header[data-testid="stHeader"] {{display: none !important;}}
.stApp {{background: {P['bg']};}}
.block-container {{padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1440px;}}
html, body, .stApp, .stMarkdown, button, input, textarea, select {{font-family: "Inter", -apple-system, "Segoe UI", Roboto, sans-serif;}}
code, .mono {{font-family: "JetBrains Mono", ui-monospace, Menlo, monospace;}}
h1, h2, h3, h4 {{letter-spacing: -.015em;}}
/* brand + navigation */
.brand {{display:flex; align-items:center; gap:.7rem;}}
.brand .name {{font-size:1.32rem; font-weight:700; color:{P['text']}; letter-spacing:-.02em; line-height:1.1;}}
.brand .tag {{font-size:.8rem; color:{P['muted']};}}
.pill {{display:inline-flex; align-items:center; gap:.4rem; padding:.28rem .7rem; border-radius:999px; font-size:.78rem;
       border:1px solid {P['border']}; background:{P['surface2']}; color:{P['muted']}; white-space:nowrap;}}
.pill i {{width:.5rem; height:.5rem; border-radius:50%; display:inline-block;}}
div[data-testid="stSegmentedControl"] button p, [data-testid="stButtonGroup"] button p {{font-size:.92rem; font-weight:550;}}
.rule {{height:1px; background:{P['border']}; margin:.7rem 0 1.4rem 0;}}
/* hero */
.hero h1 {{font-size:2.05rem; font-weight:700; margin:0 0 .45rem 0; color:{P['text']}; line-height:1.15;}}
.hero h1 span {{color:{P['accent']};}}
.hero p {{color:{P['muted']}; font-size:1rem; line-height:1.6; margin:0; max-width:860px;}}
/* journey */
.journey {{display:flex; gap:.35rem; margin:1.2rem 0 1.1rem 0; flex-wrap:wrap;}}
.journey .j {{display:flex; align-items:center; gap:.45rem; font-size:.82rem; color:{P['faint']}; padding:.32rem .75rem .32rem .4rem;
             border-radius:999px; border:1px solid {P['border']}; background:{P['surface2']};}}
.journey .j b {{display:inline-flex; width:1.35rem; height:1.35rem; border-radius:50%; align-items:center; justify-content:center;
               font-size:.72rem; background:{P['raised']}; color:{P['muted']};}}
.journey .j.done {{color:{P['muted']};}} .journey .j.done b {{background:{P['accent2']}33; color:{P['accent']};}}
.journey .j.now {{color:{P['text']}; border-color:{P['accent']}88;}} .journey .j.now b {{background:{P['accent']}; color:{P['bg']};}}
.journey .arrow {{color:{P['faint']}; align-self:center; font-size:.8rem;}}
/* cards (st.container(key="card_...")) */
[class*="st-key-card"] {{background:{P['surface']}; border:1px solid {P['border']}; border-radius:14px; padding:1.15rem 1.3rem 1.2rem 1.3rem;}}
[class*="st-key-cardaccent"] {{border-color:{P['accent']}55; box-shadow:0 0 0 1px {P['accent']}14 inset;}}
.ch {{display:flex; align-items:center; gap:.6rem; margin-bottom:.15rem;}}
.ch .n {{display:inline-flex; width:1.6rem; height:1.6rem; border-radius:8px; align-items:center; justify-content:center;
        font-size:.8rem; font-weight:700; background:{P['accent']}1f; color:{P['accent']}; border:1px solid {P['accent']}44;}}
.ch .t {{font-size:1.08rem; font-weight:650; color:{P['text']};}}
.cs {{color:{P['muted']}; font-size:.9rem; margin:.1rem 0 .8rem 0; line-height:1.5;}}
.eyebrow {{font-size:.72rem; font-weight:650; letter-spacing:.08em; text-transform:uppercase; color:{P['faint']}; margin:.2rem 0 .45rem 0;}}
.note {{color:{P['muted']}; font-size:.84rem; line-height:1.5;}}
.faint {{color:{P['faint']}; font-size:.8rem;}}
/* badges */
.badge {{display:inline-flex; align-items:center; gap:.4rem; padding:.3rem .75rem; border-radius:999px; font-weight:600; font-size:.88rem;}}
.badge.ok {{background:{OK}1a; color:{OK}; border:1px solid {OK}55;}}
.badge.bad {{background:{BAD}1a; color:{BAD}; border:1px solid {BAD}55;}}
.badge.warn {{background:{WARN}1a; color:{WARN}; border:1px solid {WARN}55;}}
.src {{display:inline-block; font-size:.68rem; font-weight:600; padding:.08rem .45rem; border-radius:6px; margin-left:.35rem;
      vertical-align:1px; white-space:nowrap;}}
.src-stated {{background:{P['accent2']}26; color:#93c5fd;}} .src-inferred {{background:{WARN}22; color:{WARN};}}
.src-default {{background:{P['raised']}; color:{P['muted']};}} .src-edited {{background:{P['accent']}26; color:{P['accent']};}}
.src-none {{background:transparent; color:{P['faint']}; border:1px dashed {P['border2']};}}
/* key-value and lists */
.kv {{display:grid; grid-template-columns: minmax(110px, 40%) 1fr; row-gap:.42rem; column-gap:.8rem; font-size:.88rem;}}
.kv .k {{color:{P['muted']};}} .kv .v {{color:{P['text']}; word-break:break-word;}}
.plabel {{font-size:.86rem; color:{P['text']}; font-weight:550; line-height:1.3;}}
.pnote {{font-size:.75rem; color:{P['faint']}; line-height:1.35; margin-top:.1rem;}}
.unit-h {{font-size:.9rem; font-weight:650; color:{P['text']}; margin-bottom:.25rem;}}
/* prompt comparison */
.quote {{background:{P['surface2']}; border:1px solid {P['border']}; border-radius:10px; padding:.75rem .9rem; color:{P['muted']};
        font-size:.9rem; line-height:1.55; min-height:120px;}}
.diff {{background:{P['surface2']}; border:1px solid {P['border']}; border-radius:10px; padding:.75rem .9rem; font-size:.88rem;
       line-height:1.7; color:{P['muted']};}}
.diff ins {{text-decoration:none; background:{OK}22; color:#a7f3d0; border-radius:4px; padding:0 .15rem;}}
.diff del {{background:{BAD}1c; color:#fecaca; border-radius:4px; padding:0 .15rem;}}
.attn {{border-left:3px solid {WARN}; background:{WARN}0f; border-radius:8px; padding:.55rem .8rem; margin:.4rem 0; font-size:.86rem;
       color:{P['text']};}}
.attn .alt {{color:{P['muted']}; font-size:.8rem; margin-top:.15rem;}}
.info {{border-left:3px solid {P['accent']}; background:{P['accent']}0f; border-radius:8px; padding:.55rem .8rem; margin:.4rem 0;
       font-size:.86rem; color:{P['text']};}}
.issue {{border-left:3px solid {BAD}; background:{BAD}10; border-radius:8px; padding:.55rem .85rem; margin:.4rem 0;}}
.issue .p {{font-weight:650; color:{BAD}; font-size:.82rem;}} .issue .m {{color:{P['text']}; font-size:.87rem;}}
/* progress */
.prog {{display:flex; flex-direction:column; gap:.15rem;}}
.ps {{display:flex; align-items:center; gap:.7rem; padding:.42rem .2rem; font-size:.92rem; color:{P['faint']};}}
.ps .ic {{width:1.45rem; height:1.45rem; border-radius:50%; display:inline-flex; align-items:center; justify-content:center;
         font-size:.75rem; font-weight:700; border:1px solid {P['border2']};}}
.ps.done {{color:{P['text']};}} .ps.done .ic {{background:{OK}22; color:{OK}; border-color:{OK}55;}}
.ps.active {{color:{P['text']};}} .ps.active .ic {{border-color:{P['accent']}; color:{P['accent']}; animation: pulse 1.2s ease-in-out infinite;}}
.ps.failed .ic {{background:{WARN}22; color:{WARN}; border-color:{WARN}66;}} .ps.failed {{color:{P['text']};}}
.ps.stopped .ic {{background:{BAD}22; color:{BAD}; border-color:{BAD}66;}}
.ps .d {{color:{P['faint']}; font-size:.8rem; margin-left:auto;}}
@keyframes pulse {{0%,100% {{box-shadow:0 0 0 0 {P['accent']}55;}} 50% {{box-shadow:0 0 0 5px {P['accent']}00;}}}}
/* result */
.status {{display:flex; align-items:center; gap:.8rem;}}
.status .big {{font-size:1.15rem; font-weight:650; color:{OK};}}
.status .ico {{width:2.3rem; height:2.3rem; border-radius:10px; display:inline-flex; align-items:center; justify-content:center;
             background:{OK}1f; color:{OK}; font-weight:800; border:1px solid {OK}55;}}
.meta {{display:grid; grid-template-columns:1fr 1fr; gap:.5rem .9rem; margin-top:.85rem; font-size:.84rem;}}
.meta .k {{color:{P['faint']}; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em;}} .meta .v {{color:{P['text']};}}
.desc {{font-size:.95rem; line-height:1.6; color:{P['text']}; margin:.85rem .1rem .2rem .1rem;}}
.atable {{width:100%; border-collapse:collapse; font-size:.86rem; border:none !important;}}
.atable tr, .atable td {{border-left:none !important; border-right:none !important; border-top:none !important;}}
.atable td {{padding:.42rem .3rem; border-bottom:1px solid {P['border']}; vertical-align:top; color:{P['text']};}}
.atable td.k {{color:{P['muted']}; width:34%;}} .atable td.n {{color:{P['faint']}; font-size:.78rem;}}
.tierrow {{display:flex; align-items:center; gap:.65rem; padding:.48rem 0; border-bottom:1px solid {P['border']};}}
.tierrow:last-child {{border-bottom:none;}}
.tierrow .ic {{width:1.5rem; height:1.5rem; border-radius:50%; display:inline-flex; align-items:center; justify-content:center;
              font-size:.75rem; font-weight:800; flex-shrink:0;}}
.tierrow .ic.ok {{background:{OK}22; color:{OK};}} .tierrow .ic.bad {{background:{BAD}22; color:{BAD};}}
.tierrow .ic.warn {{background:{WARN}22; color:{WARN};}} .tierrow .ic.na {{background:{P['raised']}; color:{P['faint']};}}
.tierrow .t {{font-size:.9rem; color:{P['text']}; font-weight:550;}} .tierrow .s {{font-size:.76rem; color:{P['faint']};}}
.tierrow .c {{margin-left:auto; font-size:.78rem; color:{P['muted']}; white-space:nowrap;}}
.vs {{display:grid; grid-template-columns:1fr 1fr; gap:.8rem; margin-bottom:.8rem;}}
.vs .card {{border-radius:12px; padding:.9rem 1rem; border:1px solid {P['border']}; background:{P['surface2']};}}
.vs .card .h {{font-size:.72rem; letter-spacing:.07em; text-transform:uppercase; color:{P['faint']};}}
.vs .card .big {{font-size:1.3rem; font-weight:700; margin:.2rem 0;}} .vs .card .sub {{color:{P['muted']}; font-size:.86rem;}}
/* stats */
.stats {{display:grid; grid-template-columns:repeat(4, 1fr); gap:.7rem;}}
.stat {{background:{P['surface2']}; border:1px solid {P['border']}; border-radius:12px; padding:.75rem .9rem;}}
.stat .v {{font-size:1.25rem; font-weight:650; color:{P['text']};}} .stat .l {{font-size:.78rem; color:{P['muted']}; margin-top:.15rem; line-height:1.4;}}
.strip {{display:flex; flex-wrap:wrap; gap:1.4rem; font-size:.82rem; color:{P['faint']}; padding:.9rem 0 0 0; border-top:1px solid {P['border']}; margin-top:2rem;}}
.strip b {{color:{P['muted']}; font-weight:600;}}
.recent {{display:flex; align-items:center; gap:.6rem; font-size:.86rem; color:{P['text']};}}
.recent .when {{color:{P['faint']}; font-size:.78rem; white-space:nowrap;}}
.steps4 {{display:grid; grid-template-columns:repeat(4, 1fr); gap:.7rem;}}
.steps4 div {{background:{P['surface2']}; border:1px solid {P['border']}; border-radius:12px; padding:.8rem .9rem; font-size:.85rem; color:{P['muted']}; line-height:1.5;}}
.steps4 b {{display:block; color:{P['text']}; margin-bottom:.2rem;}}
/* widgets */
div.stButton > button, div.stDownloadButton > button {{border-radius:10px; font-weight:550; transition: all .12s ease;}}
div.stButton > button:hover, div.stDownloadButton > button:hover {{transform: translateY(-1px);}}
.stTextArea textarea {{font-size:.95rem; line-height:1.55; background:{P['surface2']}; border-radius:10px;}}
[data-testid="stExpander"] details {{border-color:{P['border']}; border-radius:12px; background:{P['surface']};}}
[data-testid="stExpander"] summary p {{font-size:.9rem; font-weight:550;}}
@media (max-width: 900px) {{
  .stats, .steps4 {{grid-template-columns: 1fr 1fr;}} .vs {{grid-template-columns:1fr;}} .hero h1 {{font-size:1.6rem;}}
  .journey .arrow {{display:none;}}
}}
</style>""", unsafe_allow_html=True)

LOGO = f"""<svg width="34" height="34" viewBox="0 0 34 34" fill="none" xmlns="http://www.w3.org/2000/svg">
<rect x="0.5" y="0.5" width="33" height="33" rx="9" fill="{P['surface']}" stroke="{P['border2']}"/>
<ellipse cx="17" cy="17" rx="11" ry="4.3" stroke="{P['accent']}" stroke-width="1.4"/>
<ellipse cx="17" cy="17" rx="11" ry="4.3" stroke="{P['accent']}" stroke-width="1.4" transform="rotate(60 17 17)"/>
<ellipse cx="17" cy="17" rx="11" ry="4.3" stroke="{P['accent2']}" stroke-width="1.4" transform="rotate(-60 17 17)"/>
<circle cx="17" cy="17" r="2.6" fill="{P['accent']}"/></svg>"""


# --------------------------------------------------------------------------------------------- helpers
def esc(x) -> str:
    return _html.escape(str(x))


def md(html: str):
    st.markdown(html, unsafe_allow_html=True)


def card_head(n, title: str, sub: str = ""):
    md(f"<div class='ch'>{f'<span class=n>{n}</span>' if n else ''}<span class='t'>{esc(title)}</span></div>"
       + (f"<div class='cs'>{sub}</div>" if sub else ""))


def src_badge(source) -> str:
    label, cls = SOURCES.get(source, SOURCES[None])
    return f"<span class='src {cls}'>{label}</span>"


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


def recorded() -> dict:
    out = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "runs", "requests", "*")), key=os.path.getmtime, reverse=True):
        ev = events(d)
        if ev and ev[0]["event"] == "start" and any(e["event"] == "stop" for e in ev):
            out.setdefault(ev[0]["input"].strip(), d)
    return out


def recent_runs(n: int = 8) -> list:
    out = []
    for d in sorted(glob.glob(os.path.join(ROOT, "runs", "requests", "web_*")), key=os.path.getmtime, reverse=True):
        ev = events(d)
        stop = next((e for e in ev if e["event"] == "stop"), None)
        if ev and ev[0]["event"] == "start" and stop:
            out.append((d, ev[0]["input"].strip(), str(stop.get("stop", "")), os.path.getmtime(d)))
        if len(out) >= n:
            break
    return out


def ago(ts: float) -> str:
    s = time.time() - ts
    if s < 3600:
        return f"{max(1, int(s // 60))} min ago"
    if s < 86400:
        return f"{int(s // 3600)} h ago"
    return _dt.datetime.fromtimestamp(ts).strftime("%d %b")


@st.cache_data(show_spinner=False)
def perf_stats() -> dict:
    """Platform figures read from the project's own result files (not typed in by hand)."""
    out = {}
    try:
        rows = list(csv.DictReader(open(os.path.join(ROOT, "docs", "validator_matrix.csv"))))
        bad = [r for r in rows if r["kind"] == "corrupted"]
        out["caught"] = (sum(r["status"].startswith("CAUGHT") for r in bad), len(bad))
    except (OSError, KeyError):
        pass
    try:
        txt = open(os.path.join(ROOT, "docs", "PROPERTIES.md")).read()
        out["properties"] = int(re.search(r"Totals:\*\*\s*(\d+) properties", txt).group(1))
    except (OSError, AttributeError):
        pass
    tests = sorted(glob.glob(os.path.join(ROOT, "runs", "exp", "test_*", "agent", "results.json")))
    if tests:
        runs = json.load(open(tests[-1]))["runs"]
        out["test"] = (sum(bool(r.get("success")) for r in runs), len(runs))
        lat = [r["latency_s"] for r in runs if r.get("latency_s")]
        if lat:
            out["latency"] = statistics.mean(lat)            # the figure the report quotes (docs/RESULTS_TEST.md)
    return out


@st.cache_data(show_spinner=False)
def tier_checks(path: str, spec_json: str) -> list:
    """Tier 0-2 checks of the accepted file for the result panel (Tier 3 ran inside the agent's loop)."""
    res = validate(path, declared_config_for(json.loads(spec_json)), run_tier3=False)
    return [{"tier": c.tier, "property": c.property, "name": c.name.replace("_", " "), "verdict": c.verdict,
             "message": c.message} for c in res.checks]


@st.cache_data(show_spinner=False)
def catalogue() -> tuple:
    return A.mineral_catalogue(), A.usable_surfaces()


def viewer_html(path: str, height: int) -> str:
    return viewer.html(path, height=height, bg=P["viewer"], box=P["accent"], border=P["border"], panel=P["surface"],
                       text=P["text"], muted=P["muted"], accent=P["accent"])


def diff_html(a: str, b: str) -> str:
    """Word-level difference between the original and the suggested request."""
    wa, wb = a.split(), b.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=wa, b=wb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(esc(" ".join(wa[i1:i2])))
        if op in ("delete", "replace"):
            out.append(f"<del>{esc(' '.join(wa[i1:i2]))}</del>")
        if op in ("insert", "replace"):
            out.append(f"<ins>{esc(' '.join(wb[j1:j2]))}</ins>")
    return " ".join(out)


# --------------------------------------------------------------------------------------------- progress
STEPS = ["Understanding the molecular request", "Selecting the molecular builder", "Generating the molecular structure",
         "Structural validation (Tiers 0–1)", "Physical plausibility checks (Tier 2)",
         "LAMMPS compatibility test (Tier 3)", "Preparing the final data file"]


def step_states(evs: list) -> list:
    """[(name, state, detail)] from the agent's trace; a stage is done only when its event is in the trace."""
    responded = any(e["event"] == "response" for e in evs)
    tools = [e for e in evs if e["event"] == "tool" and e["name"] == "build_data_file"]
    oks = [i for i, e in enumerate(evs) if e["event"] == "tool" and e["name"] == "build_data_file" and (e.get("result") or {}).get("ok")]
    vals = [i for i, e in enumerate(evs) if e["event"] == "validation" and e.get("verdict") != "NO_BUILD"]
    stop = next((e for e in evs if e["event"] == "stop"), None)
    accepted = bool(stop) and str(stop.get("stop", "")).startswith("accepted")
    refused = sum(1 for e in tools if not (e.get("result") or {}).get("ok"))
    builder = (tools[-1].get("input") or {}).get("builder") if tools else None
    s = ["pending"] * 7
    d = [""] * 7
    s[0] = "done" if responded else "active"
    if tools:
        s[1], d[1] = "done", f"{builder} builder" if builder else ""
    elif responded:
        s[1] = "active"
    if oks:
        s[2] = "done"
        f = (evs[oks[-1]].get("result") or {}).get("facts") or {}
        d[2] = f"{f.get('atoms', 0):,} atoms" if f else ""
    elif tools:
        s[2] = "active"
    if refused and not oks:
        d[2] = f"builder asked for a revision ({refused}×)"
    if oks:
        last_val = evs[vals[-1]] if vals and vals[-1] > oks[-1] else None
        if last_val is None:
            s[3] = "active"
        elif last_val.get("passed"):
            s[3] = s[4] = s[5] = "done"
            d[5] = "passed"
        else:
            tiers = [int(c["property"][1]) for c in last_val.get("checks", []) if re.match(r"P\d", str(c.get("property", "")))]
            failed_stage = {0: 3, 1: 3, 2: 4, 3: 5}[min(tiers) if tiers else 3]
            for k in (3, 4, 5):
                s[k] = "done" if k < failed_stage else "failed" if k == failed_stage else "pending"
            d[failed_stage] = "issue found — the agent revises"
    if accepted:
        s[6] = "done"
    elif stop:
        s[6] = "stopped"
    elif s[5] == "done":
        s[6] = "active"
    names = list(STEPS)
    if stop and not accepted:
        names[6] = "Declined — no file written" if "declined" in str(stop.get("stop")) else "Stopped — no file written"
    return list(zip(names, s, d))


def progress_html(evs: list, elapsed: float = None) -> str:
    icons = {"done": "✓", "active": "•", "pending": "", "failed": "!", "stopped": "✕"}
    rows = "".join(f"<div class='ps {s}'><span class='ic'>{icons[s]}</span><span>{esc(n)}</span>"
                   f"<span class='d'>{esc(d)}</span></div>" for n, s, d in step_states(evs))
    att = max([int(e.get("attempt") or 1) for e in evs if e.get("attempt")] or [1])
    foot = f"<div class='faint' style='margin-top:.5rem'>Attempt {att}" + (f" · {elapsed:.0f} s" if elapsed is not None else "") + "</div>"
    return f"<div class='prog'>{rows}</div>{foot}"


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


# --------------------------------------------------------------------------------------------- configuration state
def set_request(text: str):
    """Callback: replace the request text (callbacks run before the widgets are drawn)."""
    reset_analysis()
    st.session_state["request"] = text


def use_suggestion():
    S = st.session_state
    S["request"] = S["sugg_text"]
    S["analysis"]["original"] = S["sugg_text"]


def reanalyse_suggestion():
    S = st.session_state
    S["request"] = S["sugg_text"]
    S["refine_now"] = True


def reset_analysis():
    for k in [k for k in st.session_state if k.startswith("c_")]:
        del st.session_state[k]
    for k in ("analysis", "sugg_custom", "sugg_text"):
        st.session_state.pop(k, None)


def widget_values(a: dict) -> dict:
    """Session-state widget values for an assistant spec (keys c_*)."""
    w = {"c_ff": a["force_field"]}
    if a["builder"] == "minerals":
        m = a["mineral"]
        w.update(c_model=m["model"], c_sc0=m["supercell"][0], c_sc1=m["supercell"][1], c_sc2=m["supercell"][2])
        return w
    p = a["pce"]
    ion = p.get("counterion")
    w.update(c_nch=int(p["n_chains"]), c_seq=p["sequence"]["mode"], c_head=p["end_groups"][0], c_tail=p["end_groups"][1],
             c_ion=ion if ion else "none", c_pad=float(p.get("box_padding") if p.get("box_padding") is not None else 2.0))
    counts = {c["label"]: int(c["count"]) for c in p["composition"]}
    for m in p["monomers"]:
        L, k = m["label"], m["kind"]
        w[f"c_u_{L}_count"] = counts.get(L, 0)
        if k == "acid":
            w[f"c_u_{L}_type"] = "meth" if m.get("alpha_methyl") else "acr"
            w[f"c_u_{L}_dep"] = 1 if m.get("deprotonated") else 0
        elif k == "diacid":
            w[f"c_u_{L}_type"] = "maleic"
            w[f"c_u_{L}_dep"] = int(m.get("deprotonated") or 0)
        else:
            w[f"c_u_{L}_type"] = ("meth" if m.get("alpha_methyl") else "acr") if k == "ester_peg" else \
                A.ETHER.get((bool(m.get("alpha_methyl")), int(m.get("spacer") or 1)), "APEG")
            w[f"c_u_{L}_eo"] = int(m.get("eo_units") or 1)
            w[f"c_u_{L}_end"] = m.get("end") or ("OCH3" if k == "ester_peg" else "OH")
    if a["builder"] == "composite":
        s = a["surface"]
        auto = s["supercell"] == "auto"
        sc = [1, 1, 1] if auto else list(s["supercell"])
        w.update(c_surf=s["model"], c_sauto=auto, c_ss0=sc[0], c_ss1=sc[1], c_ss2=sc[2],
                 c_h=float(a.get("height") if a.get("height") is not None else 3.0), c_orient=a.get("orientation") or "flat")
    return w


def spec_from_widgets(a0: dict) -> dict:
    """The assistant spec with the user's edits applied (inverse of widget_values)."""
    S = st.session_state
    a = copy.deepcopy(a0)
    a["force_field"] = S["c_ff"]
    if a["builder"] == "minerals":
        a["mineral"] = {"model": S["c_model"], "supercell": [int(S["c_sc0"]), int(S["c_sc1"]), int(S["c_sc2"])]}
        return a
    p = a["pce"]
    for m in p["monomers"]:
        L, k = m["label"], m["kind"]
        t = S.get(f"c_u_{L}_type")
        if k == "acid":
            m["alpha_methyl"], m["deprotonated"] = t == "meth", int(S[f"c_u_{L}_dep"])
        elif k == "diacid":
            m["deprotonated"] = int(S[f"c_u_{L}_dep"])
        else:
            if k == "ester_peg":
                m["alpha_methyl"] = t == "meth"
            else:
                m["alpha_methyl"], m["spacer"] = {v: k2 for k2, v in A.ETHER.items()}[t]
            m["eo_units"], m["end"] = int(S[f"c_u_{L}_eo"]), S[f"c_u_{L}_end"]
    counts = {m["label"]: int(S[f"c_u_{m['label']}_count"]) for m in p["monomers"]}
    p["composition"] = [{"label": L, "count": counts[L]} for L in [c["label"] for c in p["composition"]] if counts.get(L, 0) > 0]
    used = {c["label"] for c in p["composition"]}
    p["monomers"] = [m for m in p["monomers"] if m["label"] in used]
    p["n_chains"] = int(S["c_nch"])
    if S["c_seq"] != "explicit":
        p["sequence"] = {"mode": S["c_seq"], "explicit": None}
    p["end_groups"] = [S["c_head"], S["c_tail"]]
    p["counterion"] = None if S["c_ion"] == "none" else S["c_ion"]
    if a["builder"] == "pce":
        p["box_padding"] = float(S["c_pad"])
    else:
        p["box_padding"] = None
        a["surface"] = {"model": S["c_surf"],
                        "supercell": "auto" if S["c_sauto"] else [int(S["c_ss0"]), int(S["c_ss1"]), int(S["c_ss2"])]}
        a["height"], a["orientation"] = float(S["c_h"]), S["c_orient"]
    return a


def edited_keys(init: dict) -> set:
    return {k for k, v in init.items() if st.session_state.get(k) != v}


PARAM_OF = {"c_ff": "force_field", "c_model": "mineral.model", "c_sc0": "mineral.supercell", "c_sc1": "mineral.supercell",
            "c_sc2": "mineral.supercell", "c_nch": "n_chains", "c_seq": "sequence", "c_head": "end_groups",
            "c_tail": "end_groups", "c_ion": "counterion", "c_pad": "box_padding", "c_surf": "surface.model",
            "c_sauto": "surface.supercell", "c_ss0": "surface.supercell", "c_ss1": "surface.supercell",
            "c_ss2": "surface.supercell", "c_h": "height", "c_orient": "orientation"}


def param_key(widget_key: str) -> str:
    m = re.match(r"c_u_(.+)_(count|type|eo|end|dep)$", widget_key)
    if m:
        return f"unit.{m.group(1)}." + {"count": "count", "type": "type", "eo": "eo_units", "end": "end",
                                        "dep": "deprotonated"}[m.group(2)]
    return PARAM_OF.get(widget_key, widget_key)


def source_of(param: str, prov: dict, edited_params: set):
    if param in edited_params:
        return "edited"
    return (prov.get(param) or (None, ""))[0]


# --------------------------------------------------------------------------------------------- configuration panel
def prow(label: str, param: str, prov: dict, edited: set):
    """Left: label + where the value came from; right: the widget column."""
    left, right = st.columns([1, 1.25], vertical_alignment="center")
    note = (prov.get(param) or (None, ""))[1]
    left.markdown(f"<div class='plabel'>{esc(label)}{src_badge(source_of(param, prov, edited))}</div>"
                  + (f"<div class='pnote'>{esc(note)}</div>" if note and param not in edited else ""), unsafe_allow_html=True)
    return right


def config_panel(a0: dict, prov: dict) -> tuple:
    """Controls for the parameters this system uses. Returns (spec with edits, edited parameter keys)."""
    init = st.session_state["analysis"]["init"]
    edited = {param_key(k) for k in edited_keys(init)}
    minerals, surfaces = catalogue()
    names = {m["name"]: m for m in minerals}
    b = a0["builder"]
    md("<div class='eyebrow'>System</div>")
    c = st.columns(2, gap="large")
    with c[0]:
        prow("System type", "system", prov, edited).markdown(
            f"<div class='plabel' style='font-weight:500'>{ {'pce': 'PCE superplasticiser', 'minerals': 'Cement mineral', 'composite': 'PCE on a mineral surface'}[b]}</div>",
            unsafe_allow_html=True)
    with c[1]:
        prow("Force field", "force_field", prov, edited).selectbox(
            "Force field", ["pcff", "cvff"], key="c_ff", format_func=lambda x: {"pcff": "PCFF-INTERFACE (class II)", "cvff": "CVFF-INTERFACE (class I)"}[x],
            label_visibility="collapsed", help="INTERFACE FF 1.5. CVFF-INTERFACE covers PCE chemistry and, among minerals, only C3S and C3A.")
    if b == "minerals":
        md("<div class='eyebrow' style='margin-top:.9rem'>Mineral model</div>")
        c = st.columns(2, gap="large")
        with c[0]:
            opts = [m["name"] for m in minerals]
            if st.session_state["c_model"] not in opts:
                opts.insert(0, st.session_state["c_model"])
            prow("Model", "mineral.model", prov, edited).selectbox(
                "Model", opts, key="c_model", label_visibility="collapsed",
                format_func=lambda x: f"{x}" + (f"  ·  {', '.join(f.upper() for f in names[x]['ffs'])}" if x in names else ""))
        with c[1]:
            r = prow("Supercell (a × b × c)", "mineral.supercell", prov, edited)
            s = r.columns(3)
            for i in range(3):
                s[i].number_input(f"n{'abc'[i]}", 1, 20, key=f"c_sc{i}", label_visibility="collapsed")
        return spec_from_widgets(a0), edited
    p = a0["pce"]
    md("<div class='eyebrow' style='margin-top:1rem'>Molecular composition — per chain</div>")
    explicit = p["sequence"]["mode"] == "explicit"
    ucols = st.columns(2, gap="medium")
    for i, m in enumerate(p["monomers"]):
        Lb, k = m["label"], m["kind"]
        with ucols[i % 2]:
            with st.container(key=f"cardunit_{Lb}"):
                badges = " ".join(f"<span class='faint'>{n}</span>{src_badge(source_of(f'unit.{Lb}.{f}', prov, edited))}"
                                  for n, f in (("count", "count"), ("type", "type"), ("EO", "eo_units"), ("end", "end"),
                                               ("charge", "deprotonated"))
                                  if f in ("count", "type") or (f in ("eo_units", "end") and k in ("ester_peg", "ether_peg"))
                                  or (f == "deprotonated" and k in ("acid", "diacid")))
                md(f"<div class='unit-h'>Unit {esc(Lb)} · {esc(A.unit_name(m, short=True))}</div><div style='margin-bottom:.5rem'>{badges}</div>")
                w = st.columns(2)
                if k == "acid":
                    w[0].selectbox("Monomer", ["acr", "meth"], key=f"c_u_{Lb}_type",
                                   format_func=lambda x: {"acr": "Acrylic acid", "meth": "Methacrylic acid"}[x])
                    w[1].selectbox("Protonation", [1, 0], key=f"c_u_{Lb}_dep",
                                   format_func=lambda x: "Deprotonated (COO⁻)" if x else "Protonated (COOH)",
                                   help="Carboxylates (COO⁻) carry −1 e; the counter-ions neutralise them.")
                elif k == "diacid":
                    w[0].selectbox("Monomer", ["maleic"], key=f"c_u_{Lb}_type", format_func=lambda x: "Maleic acid")
                    w[1].selectbox("Carboxylates per unit", [2, 1, 0], key=f"c_u_{Lb}_dep",
                                   format_func=lambda x: {2: "2 COO⁻ (fully deprotonated)", 1: "1 COO⁻ (half)", 0: "0 (COOH, neutral)"}[x])
                else:
                    if k == "ester_peg":
                        w[0].selectbox("Side-chain type", ["meth", "acr"], key=f"c_u_{Lb}_type",
                                       format_func=lambda x: {"meth": "MPEG methacrylate ester", "acr": "PEG acrylate ester"}[x])
                    else:
                        w[0].selectbox("Side-chain type", ["APEG", "HPEG", "TPEG", "VPEG"], key=f"c_u_{Lb}_type",
                                       format_func=lambda x: A.ETHER_LONG[x])
                    w[1].selectbox("Side-chain end", ["OCH3", "OH"], key=f"c_u_{Lb}_end",
                                   format_func=lambda x: A.END[x],
                                   help="Default when unstated: OCH₃ for ester side chains, OH for ether side chains.")
                w = st.columns(2)
                w[0].number_input("Units per chain", 0, 1000, key=f"c_u_{Lb}_count", disabled=explicit,
                                  help="Set to 0 to remove this unit." + (" Locked: the sequence is given explicitly." if explicit else ""))
                if k in ("ester_peg", "ether_peg"):
                    w[1].number_input("EO units per side chain", 1, 500, key=f"c_u_{Lb}_eo")
    md("<div class='eyebrow' style='margin-top:1rem'>Architecture</div>")
    c = st.columns(2, gap="large")
    with c[0]:
        prow("Number of chains", "n_chains", prov, edited).number_input("Chains", 1, 100, key="c_nch", label_visibility="collapsed")
        seq_opts = ["random", "alternating", "block", "gradient"] + (["explicit"] if explicit else [])
        prow("Sequence", "sequence", prov, edited).selectbox(
            "Sequence", seq_opts, key="c_seq", label_visibility="collapsed",
            format_func=lambda x: {"random": "Random", "alternating": "Alternating", "block": "Block (in the order listed)",
                                   "gradient": "Gradient (side chains increase)", "explicit": "Explicit order (as interpreted)"}[x])
    with c[1]:
        r = prow("Backbone end groups (head, tail)", "end_groups", prov, edited)
        e = r.columns(2)
        e[0].selectbox("Head", ["CH3", "H"], key="c_head", label_visibility="collapsed")
        e[1].selectbox("Tail", ["CH3", "H"], key="c_tail", label_visibility="collapsed")
    md("<div class='eyebrow' style='margin-top:1rem'>Charge and counter-ions</div>")
    a_now = spec_from_widgets(a0)
    q = A.carboxylates(a_now) * int(st.session_state["c_nch"])
    c = st.columns(2, gap="large")
    with c[0]:
        prow("Counter-ion", "counterion", prov, edited).selectbox(
            "Counter-ion", ["Na+", "K+", "Ca2+", "none"], key="c_ion", label_visibility="collapsed",
            format_func=lambda x: {"Na+": "Na⁺ (sodium)", "K+": "K⁺ (potassium)", "Ca2+": "Ca²⁺ (calcium)", "none": "None — leave the system charged"}[x])
    with c[1]:
        ion = st.session_state["c_ion"]
        if ion == "none":
            txt = f"{q} carboxylates in total → net charge −{q} e (no counter-ions)."
        else:
            sym, z = A.ION[ion]
            txt = (f"{q} carboxylates in total → the builder adds {q // z} {sym} to reach 0 e." if q % z == 0 else
                   f"{q} carboxylates cannot be neutralised by {sym} (charge {z}+): the builder would refuse.")
        md(f"<div class='{'info' if ion == 'none' or q % A.ION[ion][1] == 0 else 'attn'}'>{esc(txt)}</div>")
    md("<div class='eyebrow' style='margin-top:1rem'>Box and placement</div>")
    c = st.columns(2, gap="large")
    if b == "pce":
        with c[0]:
            prow("Box padding (Å per face)", "box_padding", prov, edited).number_input(
                "Padding", 0.0, 20.0, step=0.5, key="c_pad", label_visibility="collapsed",
                help="Empty space on every side of the atoms; the validator accepts 1–5 Å (P2.10). Boundaries are periodic.")
    else:
        with c[0]:
            opts = list(surfaces)
            if st.session_state["c_surf"] not in opts:
                opts.insert(0, st.session_state["c_surf"])
            prow("Surface model", "surface.model", prov, edited).selectbox("Surface", opts, key="c_surf", label_visibility="collapsed")
            r = prow("Surface cells", "surface.supercell", prov, edited)
            r.toggle("Automatic (smallest that fits)", key="c_sauto")
            if not st.session_state["c_sauto"]:
                s = r.columns(3)
                for i in range(3):
                    s[i].number_input(f"s{i}", 1, 20, key=f"c_ss{i}", label_visibility="collapsed")
        with c[1]:
            prow("Height above the surface (Å)", "height", prov, edited).number_input(
                "Height", 0.0, 20.0, step=0.5, key="c_h", label_visibility="collapsed")
            prow("Orientation", "orientation", prov, edited).selectbox(
                "Orientation", ["flat", "as_built"], key="c_orient", label_visibility="collapsed",
                format_func=lambda x: {"flat": "Flat on the surface", "as_built": "As built"}[x])
    return spec_from_widgets(a0), edited


def summary_rows(a: dict) -> list:
    ff = A.FF[a["force_field"]]
    if a["builder"] == "minerals":
        m = a["mineral"]
        return [("System", "Cement mineral"), ("Model", m["model"]), ("Force field", ff),
                ("Supercell", " × ".join(map(str, m["supercell"])))]
    p = a["pce"]
    mons = {m["label"]: m for m in p["monomers"]}
    rows = [("System", A.polymer_type(p) + (" on a surface" if a["builder"] == "composite" else "")), ("Force field", ff),
            ("Backbone", f"{sum(c['count'] for c in p['composition'])} units per chain"),
            ("Composition", "<br>".join(f"{c['count']} × {esc(A.unit_name(mons[c['label']]))}" for c in p["composition"])),
            ("Chains", p["n_chains"]), ("Sequence", p["sequence"]["mode"]), ("End groups", " / ".join(p["end_groups"])),
            ("Counter-ion", A.ION[p["counterion"]][0] if p.get("counterion") else "none")]
    if a["builder"] == "pce":
        rows.append(("Box padding", f"{p.get('box_padding') if p.get('box_padding') is not None else 2.0:g} Å"))
    else:
        s = a["surface"]
        rows += [("Surface", s["model"]), ("Surface cells", s["supercell"] if s["supercell"] == "auto" else " × ".join(map(str, s["supercell"]))),
                 ("Placement", f"{a.get('height') or 3.0:g} Å, {(a.get('orientation') or 'flat').replace('_', ' ')}")]
    return rows


def kv_html(rows: list) -> str:
    return "<div class='kv'>" + "".join(f"<div class='k'>{esc(k)}</div><div class='v'>{v if '<br>' in str(v) else esc(v)}</div>"
                                        for k, v in rows) + "</div>"


# --------------------------------------------------------------------------------------------- generation
def generate(text: str, meta: dict):
    """Run the frozen agent on `text` (or replay a saved run offline) with a live progress panel."""
    with st.container(key="cardaccent_progress"):
        card_head("", "Generating your molecular structure", "Each stage is marked done only when the agent's trace records it.")
        box = st.empty()
        if not st.session_state.get("offline"):
            out = os.path.join(ROOT, "runs", "requests", "web_" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
            holder = {}

            def work():
                try:
                    holder["r"] = AgentSystem()({"id": "request", "input": text}, out)
                except BaseException as e:            # SystemExit on missing credentials included
                    holder["err"] = f"{type(e).__name__}: {e}"
            th = threading.Thread(target=work, daemon=True)
            t0 = time.time()
            th.start()
            while th.is_alive():
                box.markdown(progress_html(events(out), time.time() - t0), unsafe_allow_html=True)
                time.sleep(0.5)
            if "err" in holder:
                box.empty()
                st.error("The agent could not run: " + holder["err"])
                return
        else:
            out = recorded().get(text)
            if not out:
                box.empty()
                st.info("Offline mode replays saved results, and there is none for this exact request. Choose an example, "
                        "or turn offline mode off in Settings.")
                return
            ev = events(out)
            for k in range(1, len(ev) + 1):
                box.markdown(progress_html(ev[:k]), unsafe_allow_html=True)
                time.sleep(0.25)
    if meta and not st.session_state.get("offline"):
        json.dump(meta, open(os.path.join(out, "web_request.json"), "w"), indent=1)
    elif meta:
        st.session_state.setdefault("run_meta", {})[out] = meta        # a replay: never write into a saved run
    st.session_state["last_run"] = out
    st.session_state["view"] = "result"
    st.rerun()


# --------------------------------------------------------------------------------------------- result
def result_view(run_dir: str):
    ev = events(run_dir)
    stop = next((e for e in reversed(ev) if e["event"] == "stop"), None)
    if not stop:
        st.warning("This run did not finish.")
        return
    meta = (st.session_state.get("run_meta") or {}).get(run_dir) or {}
    if not meta and os.path.exists(os.path.join(run_dir, "web_request.json")):
        meta = json.load(open(os.path.join(run_dir, "web_request.json")))
    builds = [e for e in ev if e["event"] == "tool" and e["name"] == "build_data_file" and (e.get("result") or {}).get("ok")]
    reply = next((" ".join(b["text"] for b in e["content"] if b.get("type") == "text")
                  for e in reversed(ev) if e["event"] == "response"
                  and any(b.get("type") == "text" and b.get("text", "").strip() for b in e["content"])), "")
    accepted = str(stop.get("stop", "")).startswith("accepted")
    data_file = os.path.join(run_dir, stop["data_file"]) if stop.get("data_file") else None

    if not (accepted and builds and data_file):
        declined = "declined" in str(stop["stop"])
        with st.container(key="card_declined"):
            md(f"<span class='badge warn'>{'Declined' if declined else 'Not accepted'} · no file written</span>"
               f"<p class='note' style='margin-top:.7rem'>AtomForge does not substitute a different system for a request "
               f"its builders cannot make, and it never delivers a file that failed validation.</p>")
            if reply:
                md("<div class='eyebrow' style='margin-top:.6rem'>The agent's explanation</div>")
                st.markdown(reply)
            rep = os.path.join(run_dir, "REPORT.md")
            if os.path.exists(rep):
                st.download_button("Download the attempt report (REPORT.md)", open(rep, "rb").read(), file_name="REPORT.md")
        technical(run_dir, ev, None)
        return

    last = builds[-1]
    spec = to_builder_spec({**last["input"], "notes": ""})
    facts = last["result"]["facts"]
    n_att = len(stop.get("attempts") or []) or 1
    left, right = st.columns([2.15, 1], gap="large")
    with left:
        components.html(viewer_html(data_file, 700), height=712)
        md(f"<div class='desc'>{esc(A.describe_built(spec, facts))}</div>")
        if meta.get("config"):
            diffs = spec_diff(spec, to_builder_spec({**meta["config"], "notes": ""}))
            if diffs:
                md("<div class='attn'><b>Differs from your configuration:</b> " + "; ".join(esc(t) for _, t in diffs) + "</div>")
            else:
                md("<div class='info'>✓ The generated structure matches the configuration you reviewed.</div>")
        assumptions_card(spec, meta, reply)
    with right:
        with st.container(key="cardaccent_status"):
            md(f"<div class='status'><span class='ico'>✓</span><div><div class='big'>Validated — ready for download</div>"
               f"<div class='faint'>Every Tier 0–3 check passed</div></div></div>"
               f"<div class='meta'><div><div class='k'>Attempts</div><div class='v'>{n_att}</div></div>"
               f"<div><div class='k'>Total time</div><div class='v'>{float(stop.get('wall_s', 0)):.0f} s</div></div>"
               f"<div><div class='k'>Builder</div><div class='v'>{esc({'pce': 'PCE', 'minerals': 'Mineral', 'composite': 'Surface composite'}[spec['builder']])}</div></div>"
               f"<div><div class='k'>Force field</div><div class='v'>{esc(A.FF[spec['force_field']])}</div></div></div>")
            st.download_button("⬇  Download LAMMPS data file", open(data_file, "rb").read(), file_name="system.data",
                               width="stretch", type="primary")
            st.download_button("Builder specification (JSON)", json.dumps(spec, indent=1), file_name="spec.json",
                               width="stretch")
        with st.container(key="card_summary"):
            md("<div class='eyebrow'>Molecular system</div>")
            box = facts["box_A"]
            tilt = box.get("tilt_xy_xz_yz") or [0, 0, 0]
            n_chains = (spec.get("pce") or spec).get("n_chains") if spec["builder"] != "minerals" else None
            rows = [("System type", {"pce": "PCE superplasticiser", "minerals": "Cement mineral", "composite": "PCE on a mineral surface"}[spec["builder"]]),
                    ("Force field", A.FF[spec["force_field"]]), ("Atoms", f"{facts['atoms']:,}"), ("Atom types", facts.get("atom_types")),
                    ("Bonds", f"{facts.get('bonds', 0):,}"), ("Angles", f"{facts.get('angles', 0):,}"),
                    ("Dihedrals", f"{facts.get('dihedrals', 0):,}"), ("Impropers", f"{facts.get('impropers', 0):,}"),
                    ("Molecules", facts.get("molecule_ids"))]
            if n_chains:
                rows.append(("PCE chains", n_chains))
            rows += [("Net charge", f"{facts['net_charge_e']:+g} e"),
                     ("Box", " × ".join(f"{x:.2f}" for x in box["lengths"]) + " Å" + (" (triclinic)" if any(abs(t) > 1e-9 for t in tilt) else "")),
                     ("Elements", " · ".join(f"{e} {n:,}" for e, n in sorted(facts.get("elements", {}).items(), key=lambda x: -x[1])))]
            md(kv_html([(k, v) for k, v in rows if v not in (None, "")]))
        with st.container(key="card_validation"):
            md("<div class='eyebrow'>Validation</div>")
            checks = tier_checks(data_file, json.dumps(spec))
            last_val = next((e for e in reversed(ev) if e["event"] == "validation" and e.get("passed")), None)
            for t, name, sub in TIERS:
                if t < 3:
                    cs = [c for c in checks if c["tier"] == t]
                    bad = [c for c in cs if c["verdict"] == "FAIL"]
                    other = [c for c in cs if c["verdict"] in ("NOT_CALIBRATED", "NOT_EVALUATED")]
                    cls, ic = ("bad", "✕") if bad else ("warn", "!") if other else ("ok", "✓")
                    count = f"{len(cs) - len(bad) - len(other)}/{len(cs)} passed"
                else:
                    cls, ic = ("ok", "✓") if last_val else ("na", "–")
                    count = "passed" if last_val else "not run"
                colour = {"ok": "green", "bad": "red", "warn": "orange", "na": "gray"}[cls]
                with st.expander(f":{colour}[{ic}]  Tier {t} · {name} — {count}", expanded=False):
                    st.caption(sub)
                    if t < 3:
                        st.dataframe([{"": {"PASS": "✓", "FAIL": "✕", "NOT_APPLICABLE": "n/a"}.get(c["verdict"], "!"),
                                       "Property": c["property"], "Check": c["name"], "Message": c["message"][:160]} for c in cs],
                                     hide_index=True, width="stretch", height=min(38 + 35 * len(cs), 320))
                    else:
                        st.markdown("LAMMPS read the file (`read_data … nocoeff`), then ran it with the full force field "
                                    "(`run 0`, finite energy, warning policy) on this machine's LAMMPS build.")
    technical(run_dir, ev, spec)


def assumptions_card(spec: dict, meta: dict, reply: str):
    with st.container(key="card_assumptions"):
        card_head("", "Assumptions and molecular interpretation")
        if meta.get("config") and meta.get("provenance") is not None:
            prov = {k: tuple(v) for k, v in meta["provenance"].items()}
            edited = set(meta.get("edited") or [])
            a = meta["config"]
            rows = []
            for key, label, value in parameter_values(a):
                src = "edited" if key in edited else (prov.get(key) or (None, ""))[0]
                note = "" if key in edited else (prov.get(key) or (None, ""))[1]
                rows.append(f"<tr><td class='k'>{esc(label)}</td><td>{esc(value)}{src_badge(src)}</td><td class='n'>{esc(note)}</td></tr>")
            md("<p class='note'>Where each value of the configuration came from. Values marked <b>AI inferred</b> were "
               "read from loose wording; <b>Builder default</b> values were not in the request.</p>"
               f"<table class='atable'>{''.join(rows)}</table>")
        else:
            defaults = A.builder_defaults(spec)
            if defaults:
                md("<p class='note'>Values in this structure that equal the builders' documented defaults. They may or "
                   "may not have been stated in the request; the agent's own account is below.</p><table class='atable'>"
                   + "".join(f"<tr><td class='k'>{esc(k)}</td><td>{esc(v)}{src_badge('default')}</td></tr>" for k, v in defaults)
                   + "</table>")
            else:
                md("<p class='note'>No builder defaults apply to this structure.</p>")
        if reply:
            with st.expander("The agent's full explanation"):
                st.markdown(reply)


def parameter_values(a: dict) -> list:
    """[(param key, label, value)] for the assumptions table."""
    out = [("force_field", "Force field", A.FF[a["force_field"]])]
    if a["builder"] == "minerals":
        m = a["mineral"]
        return out + [("mineral.model", "Model", m["model"]), ("mineral.supercell", "Supercell", " × ".join(map(str, m["supercell"])))]
    p = a["pce"]
    counts = {c["label"]: c["count"] for c in p["composition"]}
    for m in p["monomers"]:
        Lb, k = m["label"], m["kind"]
        nm = A.unit_name(m, short=True)
        out.append((f"unit.{Lb}.count", f"{nm} — units per chain", counts.get(Lb, 0)))
        if k in ("ester_peg", "ether_peg"):
            out.append((f"unit.{Lb}.eo_units", f"{nm} — EO units", m.get("eo_units")))
            out.append((f"unit.{Lb}.end", f"{nm} — side-chain end", A.END[m.get("end") or "OH"]))
        else:
            out.append((f"unit.{Lb}.deprotonated", f"{nm} — protonation", A.unit_name(m).split("(", 1)[-1].rstrip(")")))
    ion = p.get("counterion")
    out += [("n_chains", "Number of chains", p["n_chains"]), ("sequence", "Sequence", p["sequence"]["mode"]),
            ("end_groups", "Backbone end groups", " / ".join(p["end_groups"])),
            ("counterion", "Counter-ion", A.ION[ion][0] if ion else "none")]
    if a["builder"] == "pce":
        out.append(("box_padding", "Box padding", f"{p.get('box_padding') if p.get('box_padding') is not None else 2.0:g} Å"))
    else:
        s = a["surface"]
        out += [("surface.model", "Surface", s["model"]),
                ("surface.supercell", "Surface cells", "auto" if s["supercell"] == "auto" else " × ".join(map(str, s["supercell"]))),
                ("height", "Height", f"{a.get('height') or 3.0:g} Å"), ("orientation", "Orientation", a.get("orientation") or "flat")]
    return out


def technical(run_dir: str, ev: list, spec):
    with st.expander("Technical execution details"):
        model = next((e.get("model") for e in ev if e["event"] == "response" and e.get("model")), MODEL)
        md(kv_html([("Run folder", os.path.relpath(run_dir, ROOT)), ("Trace", "trace.jsonl (every model call, tool call and validation)"),
                    ("Model", model), ("Agent", "frozen v1.0 (loop-v2)")]))
        st.markdown("")
        for line in log_lines(ev):
            st.markdown(f"- {line}")
        if spec:
            st.code(json.dumps(spec, indent=1), language="json")


# --------------------------------------------------------------------------------------------- pages
def page_build():
    S = st.session_state
    if S.get("view") == "result" and S.get("last_run"):
        ev = events(S["last_run"])
        text = ev[0]["input"].strip() if ev else ""
        c = st.columns([5, 1.2, 1.1], vertical_alignment="center")
        c[0].markdown(f"<div class='eyebrow'>Request</div><div class='note' style='font-size:.92rem;color:{P['text']}'>"
                      f"{esc(text[:400])}{'…' if len(text) > 400 else ''}</div>", unsafe_allow_html=True)
        if c[1].button("← Edit request", width="stretch"):
            S["view"] = "compose"
            if text and not S.get("request"):
                S["request"] = text
            st.rerun()
        if c[2].button("New request", width="stretch"):
            reset_analysis()
            S["request"] = ""
            S["view"] = "compose"
            S.pop("last_run", None)
            st.rerun()
        md("<div style='height:.8rem'></div>")
        result_view(S["last_run"])
        return

    md(f"""<div class='hero'><h1>From molecular intent to <span>simulation-ready structures</span>.</h1>
<p>Describe a PCE superplasticiser, a cement mineral or a polymer–cement interface in your own words. AtomForge
interprets the request, builds the LAMMPS data file with deterministic builders, and validates it — up to and including
LAMMPS itself — before you download it.</p></div>""")
    e1, e2 = st.columns(2, gap="medium")
    with e1.expander("What is a LAMMPS data file?"):
        st.markdown("A LAMMPS data file defines the molecular system a molecular-dynamics simulation starts from: the "
                    "**atoms** with their coordinates, atom types, masses and charges; the **bonds, angles, dihedrals "
                    "and impropers** that connect them; the **force-field coefficients** for those interactions; and "
                    "the **simulation box** and its periodic dimensions. LAMMPS reads it with `read_data`. You can use "
                    "the files to start simulations, study molecular conformations, investigate polymer–cement "
                    "interactions and explore material properties.")
    with e2.expander("How AtomForge works"):
        st.markdown("1. **Describe** the system in plain language.\n2. **Refine** (optional): the assistant shows how it "
                    "reads your request and what it had to assume.\n3. **Configure** the parameters it found.\n4. "
                    "**Generate**: an agent turns the request into a builder specification; deterministic builders "
                    "write the atoms, topology and INTERFACE FF parameters; the validator checks the file in four tiers, "
                    "LAMMPS included. Only a file that passes every check is delivered.")

    analysis = S.get("analysis")
    has_cfg = bool(analysis and analysis.get("ok") and analysis["result"].get("buildable"))
    stage = 3 if has_cfg else 1 if analysis else 0
    names = ["Describe", "Refine", "Configure", "Generate", "Visualise & download"]
    md("<div class='journey'>" + "<span class='arrow'>›</span>".join(
        f"<span class='j {'done' if i < stage else 'now' if i == stage else ''}'><b>{'✓' if i < stage else i + 1}</b>{n}</span>"
        for i, n in enumerate(names)) + "</div>")

    # 1 · describe
    with st.container(key="card_describe"):
        card_head(1, "Describe your molecular system",
                  "Tell us what you want to simulate. You can describe the polymer, backbone composition, side chains, "
                  "force field and counter-ions in your own words.")
        md("<div class='eyebrow'>Examples</div>")
        ex = st.columns(len(EXAMPLES))
        for col, (title, text) in zip(ex, EXAMPLES):
            col.button(title, key=f"ex_{title}", width="stretch", help=text, on_click=set_request, args=(text,))
        request = st.text_area("Your request", key="request", height=130, label_visibility="collapsed", placeholder=PLACEHOLDER,
                               max_chars=3000)
        text = (request or "").strip()
        b = st.columns([1.3, 1.15, 0.8, 2.2], vertical_alignment="center")
        refine = b[0].button("✦  Refine with the assistant", type="primary", disabled=not text, width="stretch",
                             help="Shows how the request is read, what is assumed, and lets you adjust every parameter.")
        direct = b[1].button("Generate as written", disabled=not text, width="stretch",
                             help="Send the request to the agent unchanged.")
        b[2].button("Clear", type="tertiary", width="stretch", on_click=set_request, args=("",))
        b[3].markdown(f"<div class='faint' style='text-align:right'>{len(request or '')} / 3000 characters</div>",
                      unsafe_allow_html=True)
    if S.pop("refine_now", False) and text:
        refine = True
    if refine and text:
        reset_analysis()
        if S.get("offline"):
            res = A.cached(text)
            if not res:
                st.info("Offline mode can only show saved analyses, and there is none for this exact request. Turn offline "
                        "mode off in Settings to use the assistant.")
                return
        else:
            with st.spinner("The assistant is reading your request…"):
                try:
                    res = A.analyse(text)
                except Exception as e:     # network, credentials, API errors: shown, never fatal
                    st.error(f"The assistant could not run: {type(e).__name__}: {str(e)[:300]}")
                    return
        res["original"] = text
        if res.get("ok") and res["result"].get("buildable"):
            res["init"] = widget_values(res["result"]["spec"])
            for k, v in res["init"].items():
                S[k] = v
        S["analysis"] = res
        st.rerun()
    if direct and text:
        generate(text, {"source": "as written", "original": text, "final": text})
        return

    if not analysis:
        bottom_sections()
        return
    if analysis.get("original") != text:
        md("<div class='attn'>Your request has changed since the assistant read it. Refine it again to update the "
           "suggestion and the configuration.</div>")

    # 2 · refine
    result = analysis.get("result") or {}
    with st.container(key="cardaccent_assistant"):
        card_head(2, "Assistant suggestion",
                  "A suggested interpretation, not a correction. Your explicit values are kept; anything the assistant "
                  "had to assume is marked so you can confirm or change it.")
        if not analysis.get("ok"):
            md("<div class='attn'>The assistant's answer could not be used: " + esc("; ".join(analysis.get("problems") or ["unknown problem"]))
               + ". You can still generate the request as written.</div>")
            return
        if not result.get("buildable"):
            md(f"<span class='badge warn'>Outside what AtomForge can build</span><p class='note' style='margin-top:.6rem'>"
               f"{esc(result.get('out_of_scope_reason') or '')}</p><p class='faint'>Supported: PCE superplasticisers of any "
               f"architecture, INTERFACE FF cement minerals and PCE on mineral surfaces, in CVFF-INTERFACE or PCFF-INTERFACE.</p>")
            st.button("Dismiss", on_click=reset_analysis)
            return
        a_cfg = spec_from_widgets(result["spec"])
        rendered = A.render_prompt(a_cfg)
        if not S.get("sugg_custom"):
            S["sugg_text"] = rendered
        c = st.columns(2, gap="medium")
        with c[0]:
            md("<div class='eyebrow'>Your original request</div>"
               f"<div class='quote'>{esc(analysis['original'])}</div>")
        with c[1]:
            md("<div class='eyebrow'>Suggested request · editable</div>")
            st.text_area("Suggested request", key="sugg_text", height=150, label_visibility="collapsed",
                         on_change=lambda: S.__setitem__("sugg_custom", True))
        if S.get("sugg_custom") and S.get("sugg_text", "").strip() != rendered:
            md("<div class='attn'>You edited the suggested text by hand, so the configuration below may no longer match it. "
               "Generation will use your text.</div>")
            r = st.columns([1, 1, 3])
            if r[0].button("Reset to configuration"):
                S["sugg_custom"] = False
                st.rerun()
            r[1].button("Re-analyse my text", on_click=reanalyse_suggestion)
        with st.expander("What changed", expanded=True):
            md(f"<div class='diff'>{diff_html(analysis['original'], S['sugg_text'])}</div>"
               "<div class='faint' style='margin-top:.4rem'><span style='color:#a7f3d0'>Green</span> = added or made "
               "explicit · <span style='color:#fecaca'>red</span> = replaced wording.</div>")
        prov = A.parameters(result)
        amb = A.ambiguities(result)
        inferred = [(k, n) for k, (s_, n) in prov.items() if s_ == "inferred"]
        if amb or result.get("missing") or inferred:
            md("<div class='eyebrow' style='margin-top:.8rem'>Needs your attention</div>")
            for issue, chosen, alts in amb:
                md(f"<div class='attn'><b>{esc(issue)}</b> — read as: {esc(chosen)}"
                   + (f"<div class='alt'>Alternatives: {esc(' · '.join(alts))}</div>" if alts else "") + "</div>")
            for m in result.get("missing") or []:
                md(f"<div class='attn'>Not specified: {esc(m)}</div>")
        r = st.columns([1.2, 1, 3])
        r[0].button("Use as my request", help="Copy the suggested text into the request box above.", on_click=use_suggestion)
        r[1].button("Keep my original", help="Discard the suggestion and the configuration.", on_click=reset_analysis)

    # 3 · configure
    with st.container(key="card_configure"):
        card_head(3, "Configure the parameters",
                  "Only the parameters this system uses. Each shows where its value came from: "
                  f"{src_badge('stated')} {src_badge('inferred')} {src_badge('default')} {src_badge('edited')}")
        a_cfg, edited = config_panel(result["spec"], prov)

    # 4 · review and generate
    problems = A.spec_problems(a_cfg)
    final_text = S["sugg_text"] if S.get("sugg_custom") else A.render_prompt(a_cfg)
    with st.container(key="cardaccent_review"):
        card_head(4, "Review and generate")
        c = st.columns([1.35, 1], gap="large")
        with c[0]:
            md(kv_html(summary_rows(a_cfg)))
        with c[1]:
            n_inf = sum(1 for k, (s_, _) in prov.items() if s_ == "inferred" and k not in edited)
            if problems:
                for p_ in problems:
                    md(f"<div class='issue'><div class='p'>Conflict</div><div class='m'>{esc(p_)}</div></div>")
            if n_inf or amb:
                md(f"<div class='attn'>{n_inf} inferred value{'s' if n_inf != 1 else ''} and {len(amb)} "
                   f"ambiguit{'ies' if len(amb) != 1 else 'y'} — review them above if they matter for your study.</div>")
            if not problems and not (n_inf or amb):
                md("<div class='info'>Every value is either stated by you or a documented default.</div>")
            md("<p class='faint'>The agent receives the suggested request text; the result page compares what it built "
               "with this configuration.</p>")
            go = st.button("Generate molecular structure  →", type="primary", width="stretch", disabled=bool(problems))
    if go:
        meta = {"source": "assistant", "original": analysis["original"], "final": final_text, "config": a_cfg,
                "provenance": {k: list(v) for k, v in prov.items()}, "edited": sorted(edited),
                "ambiguities": [list(x) for x in amb], "assistant": analysis.get("version"), "text_edited": bool(S.get("sugg_custom"))}
        generate(final_text, meta)
    bottom_sections()


def bottom_sections():
    S = st.session_state
    runs = recent_runs()
    if runs:
        with st.expander(f"Recent generations ({len(runs)})"):
            for d, text, stop, ts in runs:
                c = st.columns([0.25, 5, 1, 0.8, 0.8], vertical_alignment="center")
                ok = stop.startswith("accepted")
                c[0].markdown(f"<span style='color:{OK if ok else WARN}'>{'✓' if ok else '⏹'}</span>", unsafe_allow_html=True)
                c[1].markdown(f"<div class='recent'>{esc(text[:150])}{'…' if len(text) > 150 else ''}</div>", unsafe_allow_html=True)
                c[2].markdown(f"<div class='recent'><span class='when'>{ago(ts)}</span></div>", unsafe_allow_html=True)
                if c[3].button("Open", key=f"open_{d}"):
                    S["last_run"], S["view"] = d, "result"
                    st.rerun()
                c[4].button("Reuse", key=f"reuse_{d}", help="Put this request in the box above.", on_click=set_request, args=(text,))
    s = perf_stats()
    parts = []
    if "test" in s:
        parts.append(f"<b>{s['test'][0]}/{s['test'][1]}</b> held-out test runs correct")
    if "caught" in s:
        parts.append(f"<b>{s['caught'][0]}/{s['caught'][1]}</b> corrupted files caught")
    if "properties" in s:
        parts.append(f"<b>{s['properties']}</b> properties checked")
    if "latency" in s:
        parts.append(f"mean time <b>≈ {s['latency']:.0f} s</b> per file")
    if parts:
        md("<div class='strip'><span>Platform reliability</span>" + "".join(f"<span>{p}</span>" for p in parts)
           + "<span>· details under About</span></div>")


def page_validate():
    S = st.session_state
    md("<div class='hero'><h1>Validate an existing <span>LAMMPS data file</span>.</h1><p>Check any LAMMPS data file — from "
       "AtomForge, EMC, Materials Studio, msi2lmp or written by hand — against up to 44 properties in four tiers. Runs "
       "locally; nothing is uploaded anywhere.</p></div><div style='height:1.1rem'></div>")
    matrix = {}
    mpath = os.path.join(ROOT, "docs", "validator_matrix.csv")
    if os.path.exists(mpath):
        matrix = {r["id"]: r for r in csv.DictReader(open(mpath))}
    left, right = st.columns([1, 1.55], gap="large")
    with left:
        with st.container(key="card_vinput"):
            card_head(1, "Choose a file")
            src = st.segmented_control("Source", ["Example files", "Upload a file"], key="v_src", default="Example files",
                                       label_visibility="collapsed")
            path, cfg, row = None, None, None
            if src == "Upload a file":
                up = st.file_uploader("LAMMPS data file", label_visibility="collapsed", type=None,
                                      help="A LAMMPS data file as read by read_data (any extension, plain text).")
                md("<p class='faint'>Plain-text LAMMPS data files (<code>.data</code>, <code>.lmp</code>, <code>.txt</code> …). "
                   "Declare what the file should be: the validator checks it against that declaration.</p>")
                confs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "configs", "*.yaml")))
                conf = st.selectbox("System family and force field", confs, format_func=lambda c: CONFIG_NAMES.get(c, c),
                                    index=confs.index("interface_pcff_pce.yaml") if "interface_pcff_pce.yaml" in confs else 0,
                                    help="The declared validation configuration (configs/*.yaml): units, atom style, styles, "
                                         "boundary and policies.")
                shape = st.selectbox("Box shape", ["config", "orthogonal", "triclinic"],
                                     format_func=lambda x: {"config": "As in the configuration", "orthogonal": "Orthogonal",
                                                            "triclinic": "Triclinic (tilted cell)"}[x],
                                     help="Crystal unit cells are usually triclinic; PCE boxes and rectangular cells orthogonal.")
                if up is not None:
                    path = os.path.join(ROOT, "runs", "uploads", os.path.basename(up.name))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as fh:
                        fh.write(up.getbuffer())
                    cfg = load_config(declared=os.path.join("configs", conf),
                                      overrides={"declared": {"box_kind": shape}} if shape != "config" else None)
            else:
                choice = st.radio("Example", [f[0] for f in CHECK_FILES], key="v_example", label_visibility="collapsed")
                _, fname, note = next(f for f in CHECK_FILES if f[0] == choice)
                path = os.path.join(ROOT, "web", "examples", fname)
                cfg = config_for(path)
                row = matrix.get(fname[:-5])
                md(f"<div class='info'>{esc(note)}</div>")
            if path:
                md(f"<p class='faint'>Selected: <code>{esc(os.path.basename(path))}</code></p>")
            tier3 = st.toggle("Run LAMMPS as well (Tier 3)", value=True, help="Runs read_data and run 0 with the full force "
                              "field on this machine's LAMMPS build. Takes a few seconds.")
            if st.button("Validate file  →", type="primary", width="stretch", disabled=not path):
                with st.spinner("Checking the file…"):
                    S["check"] = (path, validate(path, cfg, run_tier3=tier3), row)
    with right:
        chk = S.get("check")
        if not chk or chk[0] != path:
            with st.container(key="card_vempty"):
                card_head("", "How to read the result")
                md("<p class='note'>Choose a file and press <b>Validate file</b>. The result compares <b>LAMMPS on its own</b> "
                   "with <b>this validator</b>. The four corrupted examples are files that LAMMPS reads and runs "
                   "<b>without any error or warning</b>; the validator rejects each one and says why.</p>")
                md("<div class='steps4'>" + "".join(f"<div><b>Tier {t} · {esc(n)}</b>{esc(s)}</div>" for t, n, s in TIERS) + "</div>")
            return
        _, res, row = chk
        fails = [c for c in res.checks if c.verdict == "FAIL"]
        incomplete = [c for c in res.checks if c.verdict in ("NOT_CALIBRATED", "NOT_EVALUATED")]
        lam = LAMMPS_ALONE.get((row or {}).get("lammps_alone", ""), None)
        if row and row.get("kind") == "positive":
            lam = ("Runs", "A correct file runs normally.")
        with st.container(key="card_vresult"):
            if fails:
                md(f"<span class='badge bad'>✕ Failed validation · {len(fails)} check{'s' if len(fails) != 1 else ''}</span>")
            elif incomplete:
                md(f"<span class='badge warn'>! Incomplete · {len(incomplete)} check{'s' if len(incomplete) != 1 else ''} not evaluated</span>")
            else:
                md(f"<span class='badge ok'>✓ Valid · all {len(res.checks)} checks passed</span>")
            lam_html = (f"<div class='card'><div class='h'>LAMMPS on its own</div><div class='big' style='color:{WARN if lam and lam[0].startswith('Runs') and fails else P['text']}'>"
                        f"{esc(lam[0])}</div><div class='sub'>{esc(lam[1])}</div></div>" if lam else
                        "<div class='card'><div class='h'>LAMMPS on its own</div><div class='big'>—</div>"
                        "<div class='sub'>Measured only for the example files.</div></div>")
            val_html = (f"<div class='card'><div class='h'>This validator</div><div class='big' style='color:{OK}'>✓ Passed</div>"
                        f"<div class='sub'>All {len(res.checks)} checks passed.</div></div>" if not fails and not incomplete else
                        f"<div class='card'><div class='h'>This validator</div><div class='big' style='color:{WARN}'>! Incomplete</div>"
                        f"<div class='sub'>{len(res.checks) - len(incomplete)} of {len(res.checks)} passed; {len(incomplete)} not "
                        f"evaluated, which never counts as a pass.</div></div>" if not fails else
                        f"<div class='card'><div class='h'>This validator</div><div class='big' style='color:{BAD}'>✕ Rejected</div>"
                        f"<div class='sub'>{len(fails)} check{'s' if len(fails) != 1 else ''} failed — explained below.</div></div>")
            md(f"<div style='height:.8rem'></div><div class='vs'>{lam_html}{val_html}</div>")
            rows = ""
            for t, name, sub in TIERS:
                cs = [c for c in res.checks if c.tier == t]
                bad = [c for c in cs if c.verdict == "FAIL"]
                inc = [c for c in cs if c.verdict in ("NOT_CALIBRATED", "NOT_EVALUATED")]
                if not cs:
                    cls, ic, count = "na", "–", "not run"
                else:
                    cls, ic = ("bad", "✕") if bad else ("warn", "!") if inc else ("ok", "✓")
                    count = f"{len(cs) - len(bad) - len(inc)}/{len(cs)} passed" + (f" · {len(bad)} failed" if bad else "") + \
                            (f" · {len(inc)} not evaluated" if inc else "")
                rows += (f"<div class='tierrow'><span class='ic {cls}'>{ic}</span><div><div class='t'>Tier {t} · {esc(name)}</div>"
                         f"<div class='s'>{esc(sub)}</div></div><span class='c'>{esc(count)}</span></div>")
            md(rows)
            if (res.lammps or {}).get("errors"):
                md("<div class='eyebrow' style='margin-top:.7rem'>LAMMPS errors</div>")
                for line in res.lammps["errors"][:4]:
                    md(f"<div class='issue'><div class='m mono'>{esc(line[:240])}</div></div>")
            if fails:
                md("<div class='eyebrow' style='margin-top:.8rem'>What is wrong</div>")
                for c in fails[:6]:
                    md(f"<div class='issue'><div class='p'>{esc(c.property)} · {esc(c.name.replace('_', ' '))}</div>"
                       f"<div class='m'>{esc(c.message[:300])}</div></div>")
            if fails and incomplete:
                md(f"<div class='attn'>{len(incomplete)} later check{'s' if len(incomplete) != 1 else ''} not evaluated: "
                   f"a tier stops the tiers above it when it fails.</div>")
            else:
                for c in incomplete[:4]:
                    md(f"<div class='attn'><b>{esc(c.property)} · {esc(c.verdict.replace('_', ' ').lower())}</b> — {esc(c.message[:220])}</div>")
    if not (S.get("check") and S["check"][0] == path):
        return
    _, res, _ = S["check"]
    md("<div style='height:1rem'></div>")
    v, t = st.columns([1.15, 1], gap="large")
    with v:
        md("<div class='eyebrow'>Structure</div>")
        components.html(viewer_html(path, 560), height=572)
    with t:
        md(f"<div class='eyebrow'>All {len(res.checks)} checks</div>")
        rows = sorted(res.checks, key=lambda c: ({"FAIL": 0, "NOT_CALIBRATED": 1, "NOT_EVALUATED": 1}.get(c.verdict, 2), str(c.tier), c.property))
        st.dataframe([{"": {"PASS": "✓", "FAIL": "✕", "NOT_APPLICABLE": "n/a"}.get(c.verdict, "!"), "Tier": str(c.tier),
                       "Property": c.property, "Check": c.name.replace("_", " "), "Message": c.message[:200]}
                      for c in rows], width="stretch", hide_index=True, height=560,
                     column_config={"": st.column_config.TextColumn(width=36), "Tier": st.column_config.TextColumn(width=44),
                                    "Property": st.column_config.TextColumn(width=70), "Message": st.column_config.TextColumn(width="large")})


def page_about():
    md("<div class='hero'><h1>About <span>AtomForge</span></h1><p>AtomForge is an AI-assisted molecular structure "
       "generation and validation platform for molecular-dynamics simulations with LAMMPS. Describe a system in natural "
       "language, configure its chemical parameters, and AtomForge translates the request into a structured "
       "configuration, builds the LAMMPS data file with deterministic builders, and validates its structural and "
       "physical consistency before delivering a simulation-ready file.</p></div><div style='height:1.2rem'></div>")
    with st.container(key="card_how"):
        card_head("", "How it works")
        md("<div class='steps4'>"
           "<div><b>1 · Understand</b>A language model reads the request and writes a structured builder specification. "
           "It never writes coordinates.</div>"
           "<div><b>2 · Build</b>Deterministic builders create atoms, bonds, angles, dihedrals and impropers with "
           "INTERFACE FF 1.5 typing and charges.</div>"
           "<div><b>3 · Validate</b>An independent validator checks the file in four tiers, finishing with LAMMPS "
           "itself. Failures go back to the agent, which revises.</div>"
           "<div><b>4 · Deliver</b>Only a file that passes every check is offered for download. Requests the builders "
           "cannot make are declined, never substituted.</div></div>")
    md("<div style='height:.9rem'></div>")
    c = st.columns(2, gap="large")
    with c[0]:
        with st.container(key="card_scope"):
            card_head("", "What it can build")
            md(kv_html([("PCE superplasticisers", "Any architecture: acrylic / methacrylic acid, maleic acid, MPEG, APEG, "
                         "HPEG, TPEG and VPEG side chains; any sequence; several chains; Na⁺, K⁺ or Ca²⁺"),
                        ("Cement minerals", "Every INTERFACE FF 1.5 model: C3S, C3A, ettringite, monosulfate, tobermorite 11 Å "
                         "and 14 Å — unit cells, supercells and surfaces"),
                        ("Interfaces", "A PCE placed on a cement-mineral surface"),
                        ("Force fields", "PCFF-INTERFACE (class II); CVFF-INTERFACE (class I) for PCE, C3S and C3A")]))
    with c[1]:
        with st.container(key="card_perf"):
            card_head("", "Platform reliability")
            s = perf_stats()
            stats = []
            if "test" in s:
                stats.append((f"{s['test'][0]} / {s['test'][1]}", "held-out test runs: a valid file of exactly the requested system"))
            if "caught" in s:
                stats.append((f"{s['caught'][0]} / {s['caught'][1]}", "deliberately corrupted files caught by the validator"))
            if "properties" in s:
                stats.append((str(s["properties"]), "properties checked in four tiers, LAMMPS included"))
            if "latency" in s:
                stats.append((f"≈ {s['latency']:.0f} s", "mean time from request to validated file (test runs)"))
            md("<div class='stats' style='grid-template-columns:1fr 1fr'>" + "".join(
                f"<div class='stat'><div class='v'>{esc(v)}</div><div class='l'>{esc(l)}</div></div>" for v, l in stats) + "</div>")
            md("<p class='faint' style='margin-top:.6rem'>Read from the project's result files (docs/validator_matrix.csv, "
               "docs/PROPERTIES.md and the latest test run). The figures refer to the generation pipeline; the request "
               "assistant is an interface helper on top of it.</p>")
    md("<p class='faint' style='margin-top:1.2rem'>Version 1.0 · validator 1.0.0 · INTERFACE FF 1.5 · LAMMPS 22 Jul 2025 · "
       "runs locally on this machine</p>")


# --------------------------------------------------------------------------------------------- shell
S = st.session_state
S.setdefault("view", "compose")
shown_run = st.query_params.get("show")          # ?show=<folder in runs/requests>: open a saved result directly
if shown_run and "shown" not in S:
    S["shown"] = True
    S["last_run"], S["view"] = os.path.join(ROOT, "runs", "requests", os.path.basename(shown_run)), "result"

h = st.columns([1.6, 1.4, 1.1], vertical_alignment="center")
h[0].markdown(f"<div class='brand'>{LOGO}<div><div class='name'>AtomForge</div>"
              f"<div class='tag'>From molecular intent to simulation-ready structures</div></div></div>", unsafe_allow_html=True)
with h[1]:
    nav = st.segmented_control("Navigation", ["Build", "Validate", "About"], key="nav", default="Build",
                               label_visibility="collapsed") or "Build"
with h[2]:
    r = st.columns([1.5, 1], vertical_alignment="center")
    offline = S.get("offline", False)
    if offline:
        pill = f"<span class='pill'><i style='background:{P['muted']}'></i>Offline · saved results</span>"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        pill = f"<span class='pill'><i style='background:{OK}'></i>Connected</span>"
    else:
        pill = f"<span class='pill'><i style='background:{BAD}'></i>No API key</span>"
    r[0].markdown(f"<div style='text-align:right'>{pill}</div>", unsafe_allow_html=True)
    with r[1].popover("Settings", width="stretch"):
        st.toggle("Offline mode", key="offline",
                  help="Replays saved results and assistant analyses. Needs no internet connection.")
        st.caption("Generation uses the model in config.yaml through the API key of this terminal.")
md("<div class='rule'></div>")

if nav == "Validate":
    page_validate()
elif nav == "About":
    page_about()
else:
    page_build()

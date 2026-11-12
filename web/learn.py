"""AtomForge Learn: a step-by-step tutorial on LAMMPS data files for first-time users.

Every fact shown comes from the project: data-file excerpts are read from a validated agent output
(web/examples/apeg_maleic_pcff_tutorial.data), atom-type meanings from the PCFF-INTERFACE parameter file,
force-field styles from builders/minerals.py, mineral compositions are computed from the reference models,
and PCE sequences are drawn by the builder's own make_sequence. General background (what C3S is, what a PCE
does) is marked as such. The page only reads files and calls the same assistant helpers as Build.
"""
from __future__ import annotations

import csv
import os
import sys
from string import Template

import numpy as np
import streamlit as st
import streamlit.components.v1 as components

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import assistant as A  # noqa: E402
import viewer  # noqa: E402

EXAMPLE = os.path.join(HERE, "examples", "apeg_maleic_pcff_tutorial.data")
EXAMPLE_REQUEST = "short APEG superplasticizer, maybe 6 maleic and 6 APEG units with 10 EO each, sodium, pcff"

STEPS = [("Start here", "What you will learn"), ("Simulations & LAMMPS", "Where a data file fits"),
         ("Anatomy of a data file", "Every section, from a real file"), ("Bonds, angles, dihedrals", "The topology lists"),
         ("Units & atom style", "real units, atom_style full"), ("Force fields", "The two used, and how they differ"),
         ("Cement minerals", "C3S, C3A, ettringite, tobermorite"), ("PCE superplasticisers", "Backbone, side chains, charge"),
         ("Box, supercells & surfaces", "Periodicity and placement"), ("Validation", "Why “it runs” is not enough"),
         ("Build your own", "Compose a request step by step"), ("Check yourself", "Five quick questions")]

ATOM_TYPES = [  # PCFF-INTERFACE 1.5 (#atom_types), the types in the example file plus the ions
    ("c1", "C", "sp3 carbon with 1 H and 3 heavy-atom neighbours"), ("c2", "C", "sp3 carbon with 2 H"),
    ("c3", "C", "sp3 carbon with 3 H (a methyl group)"), ("c-", "C", "C in a charged carboxylate"),
    ("o-", "O", "oxygen of a carboxylate (partial double bond)"), ("oc", "O", "sp3 oxygen in an ether (the EO units)"),
    ("oh", "O", "oxygen bonded to hydrogen"), ("h", "H", "hydrogen bound to C, Si or H"), ("ho", "H", "hydrogen bonded to oxygen"),
    ("na+", "Na", "sodium ion"), ("k+", "K", "potassium ion"), ("ca++", "Ca", "calcium ion")]

MINERALS = {  # key: (title, model shown, cement notation, background)
    "C3S": ("Tricalcium silicate", "c3s_unit_cell_minimized", "C₃S = 3CaO·SiO₂",
            "The main phase of Portland cement clinker (alite is its impure form). Its reaction with water forms "
            "calcium silicate hydrate (C‑S‑H), the binder that gives concrete most of its strength."),
    "C3A": ("Tricalcium aluminate", "c3a_unit_cell_minimized", "C₃A = 3CaO·Al₂O₃",
            "Reacts very quickly with water. Gypsum is added to cement to control it, and the sulfate turns it into "
            "ettringite."),
    "Ettringite": ("Ettringite (AFt)", "ettr_unit_cell", "a calcium sulfoaluminate hydrate",
                   "Needle-like crystals formed early in hydration from C₃A and sulfate. Rich in water: note the "
                   "hydrogen count."),
    "Monosulfate": ("Monosulfate (AFm)", "monosulfate_cell_221", "a layered calcium monosulfoaluminate hydrate",
                    "A layered phase that forms later, when the sulfate runs low and ettringite converts."),
    "Tobermorite 11 Å": ("Tobermorite 11 Å", "tob11_unit_cell", "a crystalline calcium silicate hydrate",
                         "A natural mineral used as a structural model for C‑S‑H. “11 Å” is the spacing between its "
                         "layers."),
    "Tobermorite 14 Å": ("Tobermorite 14 Å", "tob14_avg_cell", "a more hydrated tobermorite",
                         "The same layered family with more interlayer water, so the layers sit 14 Å apart."),
}

GLOSSARY = [
    ("Atom type", "A force-field label for an atom in a particular chemical environment (c1, oc, na+…). One element can have several types."),
    ("atom_style full", "The Atoms layout with atom ID, molecule ID, atom type, charge and x y z, plus optional image flags."),
    ("Angle", "Three bonded atoms i–j–k; its energy depends on the angle at j."),
    ("Bond", "Two bonded atoms; its energy depends on their distance."),
    ("Box / cell", "The simulation region. Periodic: it repeats in every direction."),
    ("Class I / class II", "Force-field families. Class II adds anharmonic terms and cross terms (CVFF is class I, PCFF class II)."),
    ("Counter-ion", "An ion (Na⁺, K⁺, Ca²⁺) added to cancel the charge of the carboxylates."),
    ("C‑S‑H", "Calcium silicate hydrate, the main binding phase of hydrated cement."),
    ("Data file", "The file LAMMPS reads with read_data: atoms, topology, coefficients and box."),
    ("Dihedral", "Four atoms i–j–k–l in a row; its energy depends on the twist about the j–k bond."),
    ("EO unit", "One ethylene-oxide repeat, –CH₂–CH₂–O–, of a PEG side chain."),
    ("Force field", "The set of equations and parameters that give the energy of a configuration."),
    ("Image flags", "Three integers per atom counting how many box lengths it has been shifted by periodicity."),
    ("Improper", "Four atoms with one central atom; keeps planar groups (like COO⁻) flat."),
    ("INTERFACE FF", "A force field built to describe inorganic surfaces together with organic molecules (Heinz et al., 2013)."),
    ("Input script", "The commands LAMMPS runs (what to simulate); separate from the data file (what is simulated)."),
    ("LAMMPS", "Large-scale Atomic/Molecular Massively Parallel Simulator, an open-source molecular dynamics code."),
    ("Lennard-Jones", "The pair term for repulsion at short range and attraction (van der Waals) further out."),
    ("PCE", "Polycarboxylate ether: a comb polymer used as a superplasticiser in concrete."),
    ("Supercell", "The unit cell repeated n_a × n_b × n_c times."),
    ("Surface slab", "A mineral cut along a crystal plane, with vacuum above it, so a molecule can be placed on top."),
    ("Tilt factors", "xy xz yz: how a triclinic (slanted) box leans. Crystals often need them."),
]

QUIZ = [
    ("In which section of a data file does each atom's charge live?",
     ["Masses", "Pair Coeffs", "Atoms", "Bonds"], 2,
     "With atom_style full, the 4th column of every Atoms row is the charge in units of e."),
    ("Which force field can build an ettringite crystal?",
     ["CVFF-INTERFACE", "PCFF-INTERFACE", "Both"], 1,
     "Among the minerals, CVFF-INTERFACE covers only C3S and C3A; PCFF-INTERFACE covers every model."),
    ("A PCE has 6 maleic units, each with 2 carboxylates, neutralised with Ca²⁺. How many Ca²⁺ ions are added?",
     ["3", "6", "12"], 1,
     "6 × 2 = 12 carboxylates carry −12 e; each Ca²⁺ carries +2 e, so 12 ÷ 2 = 6 ions."),
    ("LAMMPS reads and runs your data file without any error. Is the file correct?",
     ["Yes, LAMMPS would have complained", "Not necessarily"], 1,
     "In this project's test, LAMMPS ran 521 of 948 deliberately corrupted files without an error."),
    ("What does “C3S” stand for?",
     ["Calcium silicate hydrate", "Tricalcium silicate, Ca₃SiO₅", "Three silicate chains"], 1,
     "Cement notation: C = CaO, S = SiO₂, so C₃S = 3CaO·SiO₂ = Ca₃SiO₅."),
]

CSS = Template("""<style>
[class*="st-key-lstep_"] button {width:100%; justify-content:flex-start; border:1px solid transparent; background:transparent;
  padding:.38rem .6rem; min-height:0; border-radius:10px; transform:none !important;}
[class*="st-key-lstep_"] button p {text-align:left; font-size:.86rem; color:$muted; font-weight:500;}
[class*="st-key-lstep_"] button:hover {background:$surface2; border-color:$border;}
.st-key-lstep_$cur button {background:$accent1a; border-color:$accent55;}
.st-key-lstep_$cur button p {color:$text; font-weight:650;}
.lhead {display:flex; align-items:baseline; gap:.7rem; margin:.1rem 0 .3rem 0;}
.lhead .n {font-size:.78rem; font-weight:700; color:$accent; letter-spacing:.12em; text-transform:uppercase;}
.lhead .t {font-size:1.55rem; font-weight:700; color:$text; letter-spacing:-.02em;}
.llead {color:$muted; font-size:.98rem; line-height:1.65; margin:0 0 1rem 0; max-width:60rem;}
.lp {color:$text; font-size:.93rem; line-height:1.65; margin:.2rem 0 .7rem 0;}
.lp b {color:$text;} .lmuted {color:$muted;}
.lcards {display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:.8rem; margin:.4rem 0 .9rem 0;}
.lcard {background:$surface2; border:1px solid $border; border-radius:12px; padding:.85rem .95rem; font-size:.88rem; color:$muted; line-height:1.55;}
.lcard b {display:block; color:$text; font-size:.95rem; margin-bottom:.25rem;}
.lcard .big {font-size:1.35rem; font-weight:700; color:$accent; display:block;}
.tag {display:inline-block; font-size:.68rem; font-weight:650; letter-spacing:.08em; text-transform:uppercase; padding:.12rem .5rem;
  border-radius:6px; margin-right:.35rem;}
.tag.bg {background:$surface; border:1px solid $border2; color:$muted;} .tag.fr {background:$accent1a; color:$accent;}
.tok {display:inline-flex; flex-direction:column; align-items:center; margin:.15rem .18rem; vertical-align:top;}
.tok code {font-family:"JetBrains Mono", Menlo, monospace; font-size:.9rem; padding:.3rem .5rem; border-radius:8px; color:#fff;}
.tok span {font-size:.7rem; color:$muted; margin-top:.25rem; text-align:center; max-width:7.5rem; line-height:1.3;}
.fmap {display:flex; height:30px; border-radius:8px; overflow:hidden; border:1px solid $border; margin:.4rem 0 .3rem 0;}
.fmap div {height:100%;} .fleg {display:flex; flex-wrap:wrap; gap:.4rem .9rem; font-size:.76rem; color:$muted;}
.fleg i {display:inline-block; width:.7rem; height:.7rem; border-radius:3px; margin-right:.3rem; vertical-align:-1px;}
.excerpt {background:#070a10; border:1px solid $border; border-radius:10px; padding:.75rem .9rem; overflow-x:auto;
  font-family:"JetBrains Mono", Menlo, monospace; font-size:.8rem; line-height:1.5; color:#c9d4e5; white-space:pre;}
.excerpt .h {color:$accent; font-weight:600;} .excerpt .c {color:#6b7a92;}
.seq {display:flex; flex-wrap:wrap; gap:4px; margin:.5rem 0;}
.seq div {width:34px; height:34px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:.72rem;
  font-weight:700; color:#06101d;}
.ltable {width:100%; border-collapse:collapse; font-size:.86rem; margin:.3rem 0 .8rem 0;}
.ltable th {text-align:left; color:$muted; font-weight:600; font-size:.74rem; text-transform:uppercase; letter-spacing:.06em;
  padding:.4rem .5rem; border-bottom:1px solid $border2;}
.ltable td {padding:.42rem .5rem; border-bottom:1px solid $border; color:$text; vertical-align:top;}
.ltable td code {font-family:"JetBrains Mono", Menlo, monospace; color:$accent; font-size:.84rem;}
.tip {border-left:3px solid $accent; background:$accent0f; border-radius:8px; padding:.6rem .85rem; margin:.5rem 0 .8rem 0;
  font-size:.88rem; color:$text; line-height:1.55;}
.warnbox {border-left:3px solid $warn; background:$warn0f; border-radius:8px; padding:.6rem .85rem; margin:.5rem 0 .8rem 0;
  font-size:.88rem; color:$text; line-height:1.55;}
.formula {font-size:1.6rem; font-weight:700; color:$text; letter-spacing:.01em;}
.formula sub {font-size:.62em;}
.lprog {display:flex; align-items:center; gap:.7rem; margin:.2rem 0 1rem 0; font-size:.8rem; color:$muted;}
.lprog .bar {flex:1; height:6px; background:$surface2; border-radius:99px; overflow:hidden; border:1px solid $border;}
.lprog .bar i {display:block; height:100%; background:linear-gradient(90deg, $accent2, $accent);}
.reqbox {background:$surface2; border:1px solid $accent55; border-radius:12px; padding:.85rem 1rem; font-size:.92rem; line-height:1.6; color:$text;}
@media (max-width: 900px) {.lhead .t {font-size:1.25rem;}}
</style>""")

SECTION_COLOURS = {"Header & box": "#64748b", "Masses": "#a78bfa", "Pair Coeffs": "#f472b6", "Bonded coefficients": "#fb923c",
                   "Class II cross terms": "#facc15", "Atoms": "#38bdf8", "Bonds": "#34d399", "Angles": "#22c55e",
                   "Dihedrals": "#14b8a6", "Impropers": "#2dd4bf"}


# --------------------------------------------------------------------------------------------- data from the project
@st.cache_data(show_spinner=False)
def example_lines() -> list:
    return open(EXAMPLE).read().splitlines()


def section(name: str, rows: int = 3) -> list:
    """The section header line and its first `rows` data lines from the example file."""
    L = example_lines()
    i = next(k for k, l in enumerate(L) if l.split("#")[0].strip() == name)
    data = [l for l in L[i + 1:] if l.strip()][:rows]
    return [L[i]] + data


@st.cache_data(show_spinner=False)
def file_map() -> list:
    """[(group, lines)] for the example file, grouped for the file-map bar."""
    L = example_lines()
    heads = [(k, l.split("#")[0].strip()) for k, l in enumerate(L) if l and l[0].isalpha() and k > 0] + [(len(L), "END")]
    groups = {"Header & box": heads[0][0]}
    for (i, h), (j, _) in zip(heads, heads[1:]):
        g = ("Masses" if h == "Masses" else "Pair Coeffs" if h == "Pair Coeffs" else
             "Bonded coefficients" if h in ("Bond Coeffs", "Angle Coeffs", "Dihedral Coeffs", "Improper Coeffs") else
             h if h in ("Atoms", "Bonds", "Angles", "Dihedrals", "Impropers") else "Class II cross terms")
        groups[g] = groups.get(g, 0) + (j - i)
    return list(groups.items())


@st.cache_data(show_spinner=False)
def header_counts() -> dict:
    out = {}
    for l in example_lines()[:17]:
        p = l.split()
        if len(p) >= 2 and p[0].isdigit():
            out[" ".join(p[1:])] = int(p[0])
    return out


@st.cache_data(show_spinner=False)
def mineral_scene(model: str) -> dict:
    return viewer.scene(os.path.join(ROOT, "data", "reference", "minerals", f"{model}_pcff.data"))


@st.cache_data(show_spinner=False)
def lammps_alone() -> dict:
    p = os.path.join(ROOT, "docs", "validator_matrix.csv")
    out = {}
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            if r["kind"] == "corrupted":
                out[r["lammps_alone"]] = out.get(r["lammps_alone"], 0) + 1
    return out


def formula(el: dict) -> str:
    from functools import reduce
    from math import gcd
    g = reduce(gcd, el.values())
    order = ["Ca", "Al", "Si", "S", "O", "H"]
    return "".join(f"{e}<sub>{el[e] // g}</sub>" if el[e] // g > 1 else e for e in order if e in el)


def demo_sequence(mode: str, seed: int) -> list:
    from builders.pce import ArchitectureSpec, make_sequence
    spec = ArchitectureSpec(name="demo", monomers={"A": {"kind": "acid"}, "S": {"kind": "ether_peg"}},
                            composition={"A": 12, "S": 4}, sequence=mode)
    return make_sequence(spec, np.random.default_rng(seed))


# --------------------------------------------------------------------------------------------- small drawings
def topology_svg(term: str, P: dict) -> str:
    pos = {1: (60, 140), 2: (150, 70), 3: (250, 140), 4: (340, 70)}
    bonds = [(1, 2), (2, 3), (3, 4)]
    hi = {"Bond": [1, 2], "Angle": [1, 2, 3], "Dihedral": [1, 2, 3, 4]}.get(term, [])
    if term == "Improper":
        pos = {1: (200, 105), 2: (95, 160), 3: (305, 160), 4: (200, 25)}
        bonds = [(1, 2), (1, 3), (1, 4)]
        hi = [1, 2, 3, 4]
    acc, mut = P["accent"], P["border2"]
    out = [f'<svg viewBox="0 0 400 200" width="100%" style="max-width:460px">']
    for a, b in bonds:
        on = a in hi and b in hi
        (x1, y1), (x2, y2) = pos[a], pos[b]
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{acc if on else mut}" stroke-width="{7 if on else 4}" stroke-linecap="round"/>')
    if term == "Angle":
        out.append(f'<path d="M 120 91 Q 150 110 180 91" fill="none" stroke="{P["warn"]}" stroke-width="3"/>')
    if term == "Dihedral":
        out.append(f'<path d="M 185 92 A 30 14 0 1 1 215 118" fill="none" stroke="{P["warn"]}" stroke-width="3"/>')
    for k, (x, y) in pos.items():
        on = k in hi
        out.append(f'<circle cx="{x}" cy="{y}" r="22" fill="{acc if on else P["surface2"]}" stroke="{acc if on else mut}" stroke-width="2"/>'
                   f'<text x="{x}" y="{y + 6}" text-anchor="middle" font-size="17" font-weight="700" fill="{"#06101d" if on else P["muted"]}">{k}</text>')
    out.append("</svg>")
    return "".join(out)


def bond_energy_svg(P: dict) -> str:
    """E(r) of the c1–c1 bond from the example file: class II (r0, K2, K3, K4) vs a harmonic term with the same K2."""
    r0, K2, K3, K4 = 1.5300, 299.6700, -501.7700, 679.8100
    rs = np.linspace(1.30, 1.80, 101)
    d = rs - r0
    c2 = K2 * d ** 2 + K3 * d ** 3 + K4 * d ** 4
    h = K2 * d ** 2
    emax = 25.0
    X = lambda r: 50 + (r - 1.30) / 0.50 * 330  # noqa: E731
    Y = lambda e: 190 - min(e, emax) / emax * 170  # noqa: E731
    path = lambda e: "M " + " L ".join(f"{X(r):.1f} {Y(v):.1f}" for r, v in zip(rs, e))  # noqa: E731
    ticks = "".join(f'<text x="{X(r):.0f}" y="207" font-size="11" fill="{P["muted"]}" text-anchor="middle">{r:.1f}</text>'
                    for r in (1.3, 1.4, 1.5, 1.6, 1.7, 1.8))
    yt = "".join(f'<text x="42" y="{Y(e) + 4:.0f}" font-size="11" fill="{P["muted"]}" text-anchor="end">{e:.0f}</text>'
                 f'<line x1="50" y1="{Y(e):.0f}" x2="380" y2="{Y(e):.0f}" stroke="{P["border"]}"/>' for e in (0, 10, 20))
    return (f'<svg viewBox="0 0 400 225" width="100%" style="max-width:520px">{yt}{ticks}'
            f'<line x1="{X(r0):.0f}" y1="20" x2="{X(r0):.0f}" y2="190" stroke="{P["border2"]}" stroke-dasharray="4 4"/>'
            f'<text x="{X(r0) + 4:.0f}" y="30" font-size="11" fill="{P["muted"]}">r₀ = 1.53 Å</text>'
            f'<path d="{path(h)}" fill="none" stroke="{P["muted"]}" stroke-width="2.5" stroke-dasharray="6 4"/>'
            f'<path d="{path(c2)}" fill="none" stroke="{P["accent"]}" stroke-width="3"/>'
            f'<text x="215" y="222" font-size="11" fill="{P["muted"]}" text-anchor="middle">bond length r (Å)</text>'
            f'<text x="12" y="105" font-size="11" fill="{P["muted"]}" transform="rotate(-90 12 105)" text-anchor="middle">E (kcal/mol)</text></svg>')


def pce_svg(P: dict) -> str:
    """A schematic comb (not to scale): backbone, charged acid units, PEG side chains."""
    out = ['<svg viewBox="0 0 520 170" width="100%" style="max-width:600px">',
           f'<line x1="20" y1="40" x2="500" y2="40" stroke="{P["text"]}" stroke-width="4" stroke-linecap="round"/>']
    for k, x in enumerate(range(45, 500, 40)):
        if k % 3 == 1:
            out.append(f'<path d="M {x} 40 q -14 22 0 40 q 14 22 0 40 q -14 18 0 34" fill="none" stroke="{P["accent"]}" stroke-width="3"/>'
                       f'<circle cx="{x}" cy="154" r="4" fill="{P["accent"]}"/>')
        else:
            out.append(f'<circle cx="{x}" cy="40" r="9" fill="{P["warn"]}"/><text x="{x}" y="44" font-size="11" text-anchor="middle" '
                       f'font-weight="700" fill="#1a1205">−</text>')
    out.append(f'<text x="20" y="20" font-size="12" fill="{P["muted"]}">backbone (acid units, COO⁻)</text>'
               f'<text x="300" y="120" font-size="12" fill="{P["accent"]}">PEG side chains (EO units)</text></svg>')
    return "".join(out)


# --------------------------------------------------------------------------------------------- the page
def render(ctx: dict):
    S = st.session_state
    P, md, esc = ctx["P"], ctx["md"], ctx["esc"]
    S.setdefault("learn_step", 0)
    S.setdefault("learn_seen", {0})
    cur = S["learn_step"]
    tok = {k: v for k, v in P.items()}
    tok.update(cur=cur, accent1a=P["accent"] + "1a", accent55=P["accent"] + "55", accent0f=P["accent"] + "0f",
               warn=ctx["WARN"], warn0f=ctx["WARN"] + "0f")
    md(CSS.substitute(tok))
    ctx["page_header"]("Learn", "Learn the <span>LAMMPS data file</span>.",
                       "A step-by-step guide for first-time users: what a data file contains, the force fields, the "
                       "cement minerals and polymers AtomForge builds, and how to ask for your own. No prior knowledge needed.")

    def goto(i):
        S["learn_step"] = i
        S["learn_seen"] = set(S.get("learn_seen", set())) | {i}
        S["scroll_top"] = S.get("scroll_top", 0) + 1

    left, right = st.columns([1, 3.3], gap="large")
    with left:
        with st.container(key="card_lnav"):
            md("<div class='eyebrow'>Steps</div>")
            for i, (t, _) in enumerate(STEPS):
                done = i in S["learn_seen"] and i != cur
                st.button(f"{'✓' if done else f'{i + 1:02d}'}  {t}", key=f"lstep_{i}", on_click=goto, args=(i,),
                          width="stretch", type="tertiary")
    with right:
        pct = int((cur + 1) / len(STEPS) * 100)
        md(f"<div class='lprog'><span>Step {cur + 1} of {len(STEPS)}</span><div class='bar'><i style='width:{pct}%'></i></div>"
           f"<span>{pct}%</span></div>")
        with st.container(key="card_lbody"):
            md(f"<div class='lhead'><span class='n'>Step {cur + 1:02d}</span><span class='t'>{esc(STEPS[cur][0])}</span></div>")
            [step_start, step_md, step_anatomy, step_topology, step_units, step_ff, step_minerals, step_pce, step_box,
             step_validation, step_build, step_quiz][cur](ctx)
        a, _, b = st.columns([1, 2, 1])
        if cur > 0:
            a.button(f"← {STEPS[cur - 1][0]}", key="lbtn_prev", on_click=goto, args=(cur - 1,), width="stretch")
        if cur < len(STEPS) - 1:
            b.button(f"{STEPS[cur + 1][0]} →", key="lbtn_next", on_click=goto, args=(cur + 1,), width="stretch", type="primary")
        with st.expander("Glossary: every term in one place"):
            q = st.text_input("Search the glossary", key="learn_gq", placeholder="Type a term, e.g. dihedral").strip().lower()
            rows = [(t, d) for t, d in GLOSSARY if not q or q in t.lower() or q in d.lower()]
            md("<table class='ltable'>" + "".join(f"<tr><td style='width:28%'><b>{esc(t)}</b></td><td class='lmuted'>{esc(d)}</td></tr>"
                                                  for t, d in rows) + "</table>" if rows else "<p class='lmuted'>No match.</p>")


def step_start(ctx):
    md = ctx["md"]
    md("<p class='llead'>AtomForge writes LAMMPS data files for you, but you will use them better if you know what is inside. "
       "This guide walks through the ideas one at a time, using a real file the agent built. Each step takes a minute or two; "
       "click any step on the left to jump around.</p>")
    md("<div class='lcards'>"
       "<div class='lcard'><b>1 · The file</b>What a LAMMPS data file is, section by section, and the topology lists.</div>"
       "<div class='lcard'><b>2 · The physics</b>Units, atom styles and the two force fields AtomForge uses.</div>"
       "<div class='lcard'><b>3 · The materials</b>Cement minerals (C3S, C3A, ettringite, tobermorite…) and PCE polymers.</div>"
       "<div class='lcard'><b>4 · Your own file</b>Compose a precise request, then check what you learned.</div></div>")
    md("<div class='tip'><span class='tag fr'>How to read this guide</span> Boxes marked <span class='tag fr'>from the file</span> "
       "show values read from real project files. Boxes marked <span class='tag bg'>background</span> give general context "
       "from cement and polymer science.</div>")


def step_md(ctx):
    md = ctx["md"]
    md("<p class='llead'>Molecular dynamics (MD) follows every atom of a system in time. At each small time step (in "
       "<i>real</i> units, typically about 1 fs) it computes the force on each atom from a <b>force field</b> and moves the atoms "
       "by Newton's laws. Averaging over millions of steps gives properties such as structure, adsorption and diffusion.</p>")
    md("<p class='lp'><b>LAMMPS</b> (Large-scale Atomic/Molecular Massively Parallel Simulator) is a widely used open-source MD "
       "code. It needs two inputs:</p>")
    md("<div class='lcards'>"
       "<div class='lcard'><b>The data file: what is simulated</b>Every atom with its type, charge and position; the bonds, angles, "
       "dihedrals and impropers; the force-field coefficients; and the box. Read with <code>read_data</code>. "
       "<b style='display:inline;color:inherit'>AtomForge writes this.</b></div>"
       "<div class='lcard'><b>The input script: what to do</b>Units, styles, temperature control, time step, run length and "
       "outputs. You write this for your study; it reads the data file.</div></div>")
    md("<div class='warnbox'><b>Why the data file matters.</b> A data file can be wrong in ways LAMMPS never reports: a swapped "
       "mass, a missing bond, a box that is too small. The simulation still runs and gives plausible but wrong results. "
       "Step 10 shows how AtomForge guards against this.</div>")


def step_anatomy(ctx):
    md, esc, P = ctx["md"], ctx["esc"], ctx["P"]
    hc = header_counts()
    md(f"<p class='llead'>Below is a real file AtomForge built: an APEG–maleic PCE with sodium counter-ions in "
       f"PCFF-INTERFACE. It has <b>{hc.get('atoms', 0):,} atoms</b> and {len(example_lines()):,} lines. The bar shows how "
       f"much of the file each part takes; pick a part to see it.</p>")
    fm = file_map()
    tot = sum(n for _, n in fm)
    md("<div class='fmap'>" + "".join(f"<div title='{esc(g)}: {n} lines' style='width:{n / tot * 100:.2f}%;background:{SECTION_COLOURS[g]}'></div>"
                                     for g, n in fm) + "</div><div class='fleg'>" +
       "".join(f"<span><i style='background:{SECTION_COLOURS[g]}'></i>{esc(g)} · {n}</span>" for g, n in fm) + "</div>")
    md("<div style='height:.7rem'></div>")
    part = st.pills("Part of the file", ["Header & box", "Masses", "Pair Coeffs", "Bonded coefficients", "Class II cross terms",
                                          "Atoms", "Topology lists"], key="learn_part", default="Header & box",
                    label_visibility="collapsed") or "Header & box"

    def show(lines, note=None):
        html = []
        for l in lines:
            body, _, com = l.partition("#")
            if l.strip() and l[0].isalpha():
                html.append(f"<span class='h'>{esc(body)}</span>" + (f"<span class='c'>#{esc(com)}</span>" if com else ""))
            else:
                html.append(esc(body) + (f"<span class='c'>#{esc(com)}</span>" if com else ""))
        md("<div style='margin:.3rem 0 .2rem 0'><span class='tag fr'>from the file</span></div><div class='excerpt'>" + "\n".join(html) + "</div>")
        if note:
            md(f"<p class='lmuted' style='font-size:.8rem;margin-top:.3rem'>{note}</p>")

    if part == "Header & box":
        L = example_lines()
        show(L[:17])
        md("<p class='lp'>The first line is a free comment. Then come the <b>counts</b> (atoms, bonds, angles, dihedrals, "
           "impropers), the number of <b>types</b> of each, and three lines giving the <b>box</b> limits in Å along x, y and z. "
           "A slanted (triclinic) crystal cell adds a fourth line, <code>xy xz yz</code>, with its tilt factors.</p>")
        md("<div class='warnbox'><b>Can go wrong silently:</b> if a box line is missing, LAMMPS uses a default of −0.5 to 0.5 "
           "and squeezes every atom into it, with only a generic warning. If a count is lowered to hide deleted bonds, the "
           "file still reads.</div>")
    elif part == "Masses":
        show(section("Masses", 10))
        md("<p class='lp'>One mass per <b>atom type</b>, in g/mol. LAMMPS has no idea which element an atom is: it only knows "
           "its type number and this mass. The comment after <code>#</code> is the force-field type name.</p>")
        md("<div class='warnbox'><b>Can go wrong silently:</b> swap two masses and LAMMPS treats calcium as silicon without "
           "complaint. AtomForge's validator checks every mass against the element its type name implies.</div>")
    elif part == "Pair Coeffs":
        show(section("Pair Coeffs", 5))
        md("<p class='lp'>The <b>non-bonded</b> (Lennard-Jones) parameters for each type: an energy depth ε (kcal/mol) and a "
           "size σ (Å). They describe repulsion when atoms are too close and weak attraction further out. Electrostatics come "
           "from the charges in the Atoms section.</p>")
    elif part == "Bonded coefficients":
        show(section("Bond Coeffs", 2) + [""] + section("Angle Coeffs", 1) + [""] + section("Dihedral Coeffs", 1) + [""] +
             section("Improper Coeffs", 1))
        md("<p class='lp'>One row per <b>bond, angle, dihedral and improper type</b>. For a class II bond the numbers are "
           "r₀ (Å) and K₂, K₃, K₄: the energy is K₂(r−r₀)² + K₃(r−r₀)³ + K₄(r−r₀)⁴. Step 6 plots it.</p>")
    elif part == "Class II cross terms":
        L = example_lines()
        names = [l.split("#")[0].strip() for l in L if l.strip().endswith("Coeffs") and l.split()[0] in
                 ("BondBond", "BondAngle", "AngleAngle", "AngleAngleTorsion", "EndBondTorsion", "MiddleBondTorsion", "BondBond13", "AngleTorsion")]
        show(section("BondBond Coeffs", 2))
        md(f"<p class='lp'>Class II force fields (PCFF) couple neighbouring terms: how stretching one bond changes an angle, "
           f"and so on. They add {len(names)} extra sections: {esc(', '.join(names))}. Class I files (CVFF) do not have them.</p>")
    elif part == "Atoms":
        show(section("Atoms", 3))
        row = section("Atoms", 1)[1]
        body, _, com = row.partition("#")
        t = body.split()
        lab = [("atom ID", "#38bdf8"), ("molecule ID", "#a78bfa"), ("atom type", "#f472b6"), ("charge (e)", "#facc15"),
               ("x (Å)", "#34d399"), ("y (Å)", "#34d399"), ("z (Å)", "#34d399"), ("image x", "#64748b"), ("image y", "#64748b"),
               ("image z", "#64748b")]
        md("<p class='lp'>Each Atoms row, for <code>atom_style full</code>, read column by column:</p><div>" +
           "".join(f"<div class='tok'><code style='background:{c}'>{esc(v if len(v) < 9 else v[:7] + '…')}</code><span>{esc(n)}</span></div>"
                   for v, (n, c) in zip(t, lab)) +
           f"<div class='tok'><code style='background:{P['surface2']};color:{P['muted']}'>#{esc(com.strip())}</code><span>type name</span></div></div>")
        md("<p class='lp'>The <b>molecule ID</b> groups atoms into molecules (each chain, each ion). The <b>charge</b> is a "
           "partial charge from the force field; together they must add up to the system's net charge, here zero. "
           "<b>Image flags</b> count how many box lengths an atom was shifted through the periodic boundaries.</p>")
    else:
        show(section("Bonds", 2) + [""] + section("Angles", 2) + [""] + section("Dihedrals", 2) + [""] + section("Impropers", 2))
        md("<p class='lp'>Each row is: an ID, a <b>type</b> (pointing to a row of the matching Coeffs section), then the atom "
           "IDs involved: 2 for a bond, 3 for an angle, 4 for a dihedral or improper. Step 4 shows what each means.</p>")


def step_topology(ctx):
    md, P = ctx["md"], dict(ctx["P"], warn=ctx["WARN"])
    hc = header_counts()
    md("<p class='llead'>Bonded interactions are listed explicitly in the data file. LAMMPS never guesses them: whatever is "
       "listed is what gets simulated.</p>")
    term = st.segmented_control("Term", ["Bond", "Angle", "Dihedral", "Improper"], key="learn_term", default="Bond",
                                label_visibility="collapsed") or "Bond"
    info = {"Bond": ("2 atoms", "the distance between bonded atoms", "bonds"),
            "Angle": ("3 atoms", "the angle at the middle atom", "angles"),
            "Dihedral": ("4 atoms in a row", "the twist about the middle bond", "dihedrals"),
            "Improper": ("1 central atom + 3", "how far the centre leaves the plane of its 3 neighbours (keeps COO⁻ flat)", "impropers")}
    n_atoms, what, key = info[term]
    c1, c2 = st.columns([1.2, 1], gap="large")
    with c1:
        md(f"<div style='background:{P['surface2']};border:1px solid {P['border']};border-radius:12px;padding:.6rem'>{topology_svg(term, P)}</div>")
    with c2:
        md(f"<div class='lcards' style='grid-template-columns:1fr'>"
           f"<div class='lcard'><b>{term}</b>Involves {n_atoms}; its energy depends on {what}.</div>"
           f"<div class='lcard'><span class='tag fr'>from the file</span><span class='big'>{hc.get(key, 0):,}</span>{key} in the example "
           f"file, for {hc.get('atoms', 0):,} atoms.</div></div>")
    md("<div class='tip'>There are more angles and dihedrals than atoms: every chain of 3 or 4 bonded atoms counts. A builder "
       "generates them all; writing them by hand (or by a language model) is where files go wrong.</div>")


def step_units(ctx):
    md = ctx["md"]
    md("<p class='llead'>A data file is only meaningful together with its <b>units</b> and <b>atom style</b>, which are set in "
       "the input script. Every file AtomForge writes uses <code>units real</code> and <code>atom_style full</code>, with "
       "periodic boundaries in all three directions.</p>")
    md("<span class='tag fr'>from the project configuration</span><table class='ltable'><tr><th>Quantity</th><th>Unit in <code>real</code></th></tr>"
       "<tr><td>Distance</td><td>Å (ångström, 10⁻¹⁰ m)</td></tr><tr><td>Energy</td><td>kcal/mol</td></tr>"
       "<tr><td>Mass</td><td>g/mol</td></tr><tr><td>Charge</td><td>multiples of the electron charge e</td></tr>"
       "<tr><td>Time</td><td>fs (femtosecond)</td></tr><tr><td>Temperature</td><td>K</td></tr></table>")
    md("<p class='lp'><code>atom_style full</code> means each atom carries a molecule ID and a charge, and the file can hold "
       "bonds, angles, dihedrals and impropers: what charged molecules like PCE need.</p>")
    md("<div class='warnbox'><b>Can go wrong silently:</b> read the same file with a different atom style and LAMMPS may "
       "interpret columns differently (molecule IDs become types, types become charges) without an error. Use the "
       "units and atom style the file was written for.</div>")


def step_ff(ctx):
    md, esc, P = ctx["md"], ctx["esc"], dict(ctx["P"], warn=ctx["WARN"])
    md("<p class='llead'>A force field is the recipe for the energy of a configuration: <b>bonded</b> terms (bonds, angles, "
       "dihedrals, impropers) plus <b>non-bonded</b> terms (Lennard-Jones and electrostatics). Its parameters are fitted so "
       "that simulations reproduce experiments.</p>")
    md("<p class='lp'>AtomForge uses <b>two</b> force fields, both from <b>INTERFACE FF 1.5</b> (Heinz et al., 2013), which "
       "was built to treat mineral surfaces and organic molecules consistently:</p>")
    md("<span class='tag fr'>from the builders</span><table class='ltable'><tr><th></th><th>CVFF-INTERFACE</th><th>PCFF-INTERFACE</th></tr>"
       "<tr><td>Family</td><td>class I</td><td>class II</td></tr>"
       "<tr><td>Bonds, angles</td><td>harmonic, E = K(r−r₀)²</td><td>anharmonic: K₂, K₃, K₄ terms</td></tr>"
       "<tr><td>Cross terms</td><td>none</td><td>bond–bond, bond–angle, angle–torsion…</td></tr>"
       "<tr><td>Lennard-Jones</td><td>12-6 (<code>lj/cut/coul/long</code>)</td><td>9-6 (<code>lj/class2/coul/long</code>)</td></tr>"
       "<tr><td>Cut-off</td><td>9.5 Å, long-range Coulomb</td><td>9.5 Å, long-range Coulomb</td></tr>"
       "<tr><td>Covers</td><td>PCE; among minerals only C3S and C3A</td><td>PCE and every mineral model</td></tr></table>")
    md("<p class='lp'><b>Anharmonic in practice.</b> The c1–c1 carbon bond of the example file, with its real class II "
       "coefficients (solid), against a harmonic term with the same K₂ (dashed). The class II curve is asymmetric: "
       "compressing the bond costs more than stretching it, as in real bonds.</p>")
    md(f"<div style='background:{P['surface2']};border:1px solid {P['border']};border-radius:12px;padding:.6rem .8rem'>"
       f"{bond_energy_svg(P)}<div class='fleg'><span><i style='background:{P['accent']}'></i>class II (PCFF): K₂ = 299.67, K₃ = −501.77, K₄ = 679.81</span>"
       f"<span><i style='background:{P['muted']}'></i>harmonic, same K₂</span></div></div>")
    md("<p class='lp' style='margin-top:1rem'><b>Atom types.</b> A force field gives each atom a type from its chemical "
       "environment, so one element can have several types. The types in the example file, and the ions:</p>")
    md("<span class='tag fr'>from the PCFF-INTERFACE file</span><table class='ltable'><tr><th>Type</th><th>Element</th><th>Meaning</th></tr>" +
       "".join(f"<tr><td><code>{esc(t)}</code></td><td>{e}</td><td class='lmuted'>{esc(d)}</td></tr>" for t, e, d in ATOM_TYPES) + "</table>")


def step_minerals(ctx):
    md, esc, P = ctx["md"], ctx["esc"], ctx["P"]
    md("<p class='llead'>Cement chemists abbreviate oxides: <b>C</b> = CaO, <b>S</b> = SiO₂, <b>A</b> = Al₂O₃, <b>H</b> = H₂O. "
       "So C₃S = 3CaO·SiO₂ = Ca₃SiO₅. AtomForge can build every cement-mineral model of the INTERFACE FF 1.5 database. "
       "Pick one to see it and what it is made of.</p>")
    key = st.pills("Mineral", list(MINERALS), key="learn_mineral", default="C3S", label_visibility="collapsed") or "C3S"
    title, model, notation, bg = MINERALS[key]
    S = mineral_scene(model)
    cat = {m["name"]: m for m in ctx["catalogue"]()[0]}
    prefix = model.split("_")[0]
    forms = sorted(n for n in cat if n.split("_")[0] == prefix)
    ffs = cat.get(model, {}).get("ffs", [])
    c1, c2 = st.columns([1.15, 1], gap="large")
    with c1:
        with st.container(key="lmin3d"):
            components.html(viewer.showcase(S, 360, bg=P["surface2"], spin_speed=0.25, interactive=True, box=P["accent"]), height=360)
        md(f"<p class='lmuted' style='font-size:.78rem;text-align:center'>Drag to rotate · {esc(model)} · {S['atoms']} atoms</p>")
    with c2:
        md(f"<div class='formula'>{esc(title)}</div><p class='lmuted' style='margin:.1rem 0 .6rem 0'>{esc(notation)}</p>"
           f"<span class='tag bg'>background</span><p class='lp'>{esc(bg)}</p>"
           f"<span class='tag fr'>from the model</span><table class='ltable'>"
           f"<tr><td>Element ratio</td><td><span class='formula' style='font-size:1.05rem'>{formula(S['elements'])}</span></td></tr>"
           f"<tr><td>Atoms in this cell</td><td>{S['atoms']} (" + ", ".join(f"{e} {n}" for e, n in S["elements"].items()) + ")</td></tr>"
           f"<tr><td>Force fields</td><td>{' and '.join({'pcff': 'PCFF-INTERFACE', 'cvff': 'CVFF-INTERFACE'}[f] for f in ffs)}</td></tr>"
           f"<tr><td>Models available</td><td class='lmuted'>{esc(', '.join(forms))}</td></tr></table>")
    md("<div class='tip'>The model names tell you the form: <b>unit_cell</b> is the crystal's repeating cell; "
       "<b>rectangular_cell</b> is an equivalent orthogonal cell; <b>…_surface</b> is a slab cut along a crystal plane (the "
       "numbers, like 040, name the plane) with vacuum above it, ready for a molecule to be placed on top.</div>")


def step_pce(ctx):
    md, esc, P = ctx["md"], ctx["esc"], dict(ctx["P"], warn=ctx["WARN"])
    S = st.session_state
    md("<p class='llead'>Polycarboxylate ethers (PCEs) are <b>comb polymers</b> added to concrete as superplasticisers. The "
       "negatively charged <b>backbone</b> adsorbs on cement particles, and the long neutral <b>side chains</b> keep the "
       "particles apart, so the mix flows with less water. <span class='tag bg'>background</span></p>")
    md(f"<div style='background:{P['surface2']};border:1px solid {P['border']};border-radius:12px;padding:.7rem .9rem'>{pce_svg(P)}"
       f"<p class='lmuted' style='font-size:.76rem;margin:.2rem 0 0 0'>Schematic, not to scale.</p></div>")
    md("<p class='lp' style='margin-top:1rem'><b>The building blocks AtomForge knows</b> <span class='tag fr'>from the builders</span></p>"
       "<table class='ltable'><tr><th>Unit</th><th>Role</th><th>Notes</th></tr>"
       "<tr><td>Acrylic acid · methacrylic acid</td><td>backbone acid</td><td class='lmuted'>one carboxyl group: COO⁻ (deprotonated, −1 e) or COOH</td></tr>"
       "<tr><td>Maleic acid</td><td>backbone diacid</td><td class='lmuted'>two carboxyl groups: 0, 1 or 2 COO⁻</td></tr>"
       "<tr><td>MPEG methacrylate</td><td>side chain (ester anchor)</td><td class='lmuted'>default end: methoxy, OCH₃</td></tr>"
       "<tr><td>APEG · HPEG · TPEG · VPEG</td><td>side chain (ether anchors)</td><td class='lmuted'>allyl · methallyl · isoprenyl · 4-hydroxybutyl vinyl; default end OH</td></tr>"
       "<tr><td>EO unit</td><td>side-chain repeat</td><td class='lmuted'>–CH₂–CH₂–O–; “45 EO” means 45 of them</td></tr></table>")
    md("<p class='lp'><b>Charge.</b> Each COO⁻ carries −1 e. AtomForge adds <b>counter-ions</b> to make the system neutral: "
       "one Na⁺ or K⁺ per carboxylate, or one Ca²⁺ per two. With Ca²⁺ the number of carboxylates must be even.</p>")
    md("<p class='lp'><b>Sequence.</b> The order of units along the backbone. Below is a 16-unit chain (12 acid, 4 side "
       "chains) arranged by the builder's own sequence generator:</p>")
    c1, c2 = st.columns([3, 1])
    mode = c1.segmented_control("Sequence", ["random", "alternating", "block", "gradient"], key="learn_seq", default="random",
                                label_visibility="collapsed") or "random"
    if c2.button("Draw again", key="lbtn_reseed", width="stretch", help="A new random draw (random and gradient change)."):
        S["learn_seed"] = S.get("learn_seed", 1) + 1
    seq = demo_sequence(mode, S.get("learn_seed", 1))
    md("<div class='seq'>" + "".join(f"<div style='background:{P['accent'] if u == 'S' else P['warn']}'>{'PEG' if u == 'S' else 'A'}</div>"
                                    for u in seq) + "</div>")
    expl = {"random": "Units shuffled at random: any order with the right counts.",
            "alternating": "Side chains spread as evenly as possible along the backbone.",
            "block": "All units of one kind first, then the next (the order they are listed in).",
            "gradient": "Side-chain density increases along the chain."}
    md(f"<p class='lmuted' style='font-size:.85rem'>{expl[mode]}</p>")
    md("<div class='tip'>Unless you say otherwise, AtomForge caps the two backbone ends with CH₃ and puts the PCE in a box "
       "2 Å larger than its atoms on every side.</div>")


def step_box(ctx):
    md, P = ctx["md"], ctx["P"]
    md("<p class='llead'>LAMMPS boxes are <b>periodic</b>: the box repeats in every direction, so an atom leaving one face "
       "re-enters through the opposite one. A small box therefore behaves like an endless crystal.</p>")
    view = st.segmented_control("Example", ["Unit cell", "2 × 2 × 2 supercell", "PCE on a surface"], key="learn_box",
                                default="Unit cell", label_visibility="collapsed") or "Unit cell"
    c1, c2 = st.columns([1.15, 1], gap="large")
    with c1:
        S = mineral_scene("c3s_unit_cell_minimized") if view == "Unit cell" else \
            ctx["structure"]("c3s_supercell" if view.startswith("2") else "pce_on_c3s")
        components.html(viewer.showcase(S, 340, bg=P["surface2"], spin_speed=0.22, interactive=True, box=P["accent"]), height=340)
    with c2:
        text = {"Unit cell": ("The C3S unit cell: the smallest repeating piece of the crystal, 54 atoms. Its box is slanted "
                              "(triclinic), so the file carries tilt factors."),
                "2 × 2 × 2 supercell": ("The same cell repeated twice along each axis: 8 × 54 = 432 atoms. Bigger cells reduce "
                                        "artefacts from periodic images. AtomForge replicates cells itself, because LAMMPS's "
                                        "<code>replicate</code> can join the wrong atoms in tilted cells."),
                "PCE on a surface": ("A PCE laid flat about 3 Å above a hydroxylated C3S (040) surface slab. The vacuum above the "
                                     "slab leaves room for the polymer; the surface is repeated sideways until the chain fits.")}[view]
        md(f"<p class='lp'>{text}</p>")
        md("<div class='lcards' style='grid-template-columns:1fr'><div class='lcard'><b>What you can choose</b>Supercell size "
           "(e.g. 2 × 2 × 1), the surface and its repetition, the height above the surface, flat or as built, and the box "
           "padding for a free PCE.</div></div>")


def step_validation(ctx):
    md, esc = ctx["md"], ctx["esc"]
    la = lammps_alone()
    tot = sum(la.values())
    md(f"<p class='llead'>AtomForge never delivers a file it has not checked. Its validator was tested on {tot} deliberately "
       f"corrupted files: LAMMPS on its own ran <b>{la.get('Silent', 0)}</b> of them without any message and <b>{la.get('Warn', 0)}</b> "
       f"with only a warning. The validator rejected every one.</p>")
    md("<span class='tag fr'>from the validator</span><div class='lcards'>" +
       "".join(f"<div class='lcard'><b>Tier {t} · {esc(n)}</b>{esc(s)}</div>" for t, n, s in ctx["TIERS"]) + "</div>")
    md("<div class='tip'>A file passes only if every check passes. A check the validator cannot calibrate is reported as "
       "<b>not evaluated</b>, never as a pass. You can check any data file, from any tool, on the <b>Validate</b> page.</div>")
    st.button("Try the Validate page  →", key="lbtn_val", on_click=ctx["go"], args=("Validate",))


def step_build(ctx):
    md, esc = ctx["md"], ctx["esc"]
    md("<p class='llead'>A good request states everything that matters. Compose one here; the text is written from your "
       "choices with the same code the Build page uses, so it is exactly what the builders understand.</p>")
    kind = st.segmented_control("System", ["PCE", "Cement mineral", "PCE on a surface"], key="learn_kind", default="PCE",
                                label_visibility="collapsed") or "PCE"
    ff = st.radio("Force field", ["pcff", "cvff"], key="learn_ff", horizontal=True,
                  format_func=lambda x: {"pcff": "PCFF-INTERFACE (class II)", "cvff": "CVFF-INTERFACE (class I)"}[x])
    minerals, surfaces = ctx["catalogue"]()
    cover = {m["name"]: m["ffs"] for m in minerals}
    a = {"builder": {"PCE": "pce", "Cement mineral": "minerals", "PCE on a surface": "composite"}[kind], "force_field": ff,
         "mineral": None, "pce": None, "surface": None, "height": None, "orientation": None, "notes": ""}
    if kind == "Cement mineral":
        opts = [m["name"] for m in minerals if ff in m["ffs"]]
        c = st.columns([2, 1, 1, 1])
        model = c[0].selectbox("Model", opts, key="learn_model",
                               index=opts.index("c3s_unit_cell_minimized") if "c3s_unit_cell_minimized" in opts else 0)
        sc = [c[i + 1].number_input(f"n{'abc'[i]}", 1, 6, 2 if i < 2 else 1, key=f"learn_sc{i}") for i in range(3)]
        a["mineral"] = {"model": model, "supercell": [int(x) for x in sc]}
    else:
        c = st.columns(3)
        acid = c[0].selectbox("Backbone acid", ["methacrylic", "acrylic", "maleic"], key="learn_acid",
                              format_func=lambda x: f"{x} acid")
        n_acid = c[1].number_input("Acid units per chain", 1, 60, 12, key="learn_nacid")
        if acid == "maleic":
            dep = c[2].selectbox("Carboxylates per unit", [2, 1, 0], key="learn_depm")
        else:
            dep = 1 if c[2].toggle("Deprotonated (COO⁻)", True, key="learn_dep") else 0
        c = st.columns(4)
        side = c[0].selectbox("Side chain", ["MPEG", "APEG", "HPEG", "TPEG", "VPEG"], key="learn_side")
        n_side = c[1].number_input("Side chains per chain", 0, 40, 4, key="learn_nside")
        eo = c[2].number_input("EO units each", 1, 120, 10, key="learn_eo")
        seq = c[3].selectbox("Sequence", ["random", "alternating", "block", "gradient"], key="learn_seq2")
        c = st.columns(3)
        ion = c[0].selectbox("Counter-ion", ["Na+", "K+", "Ca2+", "none"], key="learn_ion",
                             format_func=lambda x: {"Na+": "Na⁺", "K+": "K⁺", "Ca2+": "Ca²⁺", "none": "none"}[x])
        n_ch = c[1].number_input("Chains", 1, 6, 1, key="learn_nch")
        mons = [{"label": "A", "kind": "diacid" if acid == "maleic" else "acid",
                 "alpha_methyl": None if acid == "maleic" else acid == "methacrylic", "deprotonated": int(dep),
                 "eo_units": None, "end": None, "spacer": None}]
        comp = [{"label": "A", "count": int(n_acid)}]
        if n_side:
            am, sp, kind_ = {"MPEG": (True, None, "ester_peg"), "APEG": (False, 1, "ether_peg"), "HPEG": (True, 1, "ether_peg"),
                             "TPEG": (True, 2, "ether_peg"), "VPEG": (False, 2, "ether_peg")}[side]
            mons.append({"label": "P", "kind": kind_, "alpha_methyl": am, "deprotonated": None, "eo_units": int(eo),
                         "end": "OCH3" if kind_ == "ester_peg" else "OH", "spacer": sp})
            comp.append({"label": "P", "count": int(n_side)})
        a["pce"] = {"monomers": mons, "composition": comp, "sequence": {"mode": seq, "explicit": None},
                    "end_groups": ["CH3", "CH3"], "n_chains": int(n_ch), "counterion": None if ion == "none" else ion,
                    "box_padding": None if kind == "PCE on a surface" else 2.0, "seed": 1}
        if kind == "PCE on a surface":
            opts = [s for s in surfaces if ff in cover.get(s, [])]
            if not opts:
                md("<div class='warnbox'>No surface is available in this force field.</div>")
                return
            surf = c[2].selectbox("Surface", opts, key="learn_surf",
                                  index=opts.index("c3s_040_surface_hydroxylated") if "c3s_040_surface_hydroxylated" in opts else 0)
            a["surface"] = {"model": surf, "supercell": "auto"}
            a["height"], a["orientation"] = 3.0, "flat"
    problems = A.spec_problems(a)
    text = A.render_prompt(a)
    md("<div class='eyebrow' style='margin-top:.6rem'>Your request</div>"
       f"<div class='reqbox'>{esc(text)}</div>")
    for p in problems:
        md(f"<div class='warnbox'>{esc(p)}</div>")
    if not problems:
        st.button("Open this request in Build  →", key="lbtn_use", type="primary", on_click=ctx["use_request"], args=(text,))
    md("<div class='tip'><b>Checklist for any request:</b> the system (PCE, mineral or both) · the force field · for a PCE "
       "the acid units, side chains and their EO length, the sequence and the counter-ion · for a mineral the model and "
       "supercell · for a surface, which one. Anything you leave out gets a documented default, and the assistant on the "
       "Build page shows you which values it assumed.</div>")


def step_quiz(ctx):
    md, esc = ctx["md"], ctx["esc"]
    S = st.session_state
    md("<p class='llead'>Five quick questions. Pick your answers, then check them.</p>")
    for i, (q, opts, ans, why) in enumerate(QUIZ):
        md(f"<p class='lp' style='margin:.8rem 0 .2rem 0'><b>{i + 1}. {esc(q)}</b></p>")
        st.radio(q, opts, key=f"learn_q{i}", index=None, label_visibility="collapsed")
        if S.get("learn_checked"):
            got = S.get(f"learn_q{i}")
            ok = got == opts[ans]
            md(f"<div class='{'tip' if ok else 'warnbox'}'>{'✓ Correct' if ok else ('✕ Not quite' if got else '– Not answered')} — "
               f"{esc(why)}</div>")
    c = st.columns([1, 1, 2])
    c[0].button("Check answers", key="lbtn_check", type="primary", on_click=lambda: S.__setitem__("learn_checked", True))
    if S.get("learn_checked"):
        score = sum(S.get(f"learn_q{i}") == QUIZ[i][1][QUIZ[i][2]] for i in range(len(QUIZ)))
        c[1].markdown(f"<div class='lp' style='margin-top:.45rem'><b>{score} / {len(QUIZ)}</b></div>", unsafe_allow_html=True)
        if score == len(QUIZ):
            md("<div class='tip'><b>All correct.</b> You are ready to build your own data file.</div>")
    st.button("Start building  →", key="lbtn_build", on_click=ctx["go"], args=("Build",))
    st.download_button("Download the example data file", open(EXAMPLE, "rb").read(), file_name="apeg_maleic_pcff_example.data",
                       key="lbtn_dl", help="The real file used throughout this guide; open it in any text editor.")

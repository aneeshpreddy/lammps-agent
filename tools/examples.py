"""Known-good examples for get_reference_example (plan Day 26: "a small known-good snippet").

Each example is a request in the style of the eval tasks plus the build_data_file input that answers
it. They are written by hand to differ from every eval task (dev and test): tests/test_tools.py checks
that no example shares its key parameters (mineral model and supercell; PCE monomer chemistry and
composition) with any task, and scripts/tool_checks.py builds every example and validates it
(Tiers 0-3 PASS; docs/TOOLS.md).
"""
from __future__ import annotations

EXAMPLES = {
    "mineral": {
        "request": "A 1x2x1 supercell of the rectangular (orthogonal) cell of tobermorite 14 Å with averaged "
                   "occupancies (INTERFACE FF model), in PCFF-INTERFACE.",
        "spec": {"builder": "minerals", "model": "tob14_avg_rectangular_cell", "supercell": [1, 2, 1],
                 "force_field": "pcff"},
        "explanation": "Replications are along the model's a, b, c. Pick the model by name from the catalogue; "
                       "'rectangular' models are the orthogonal cells.",
    },
    "pce_ester": {
        "request": "An MPEG-type PCE in PCFF-INTERFACE: a methacrylic backbone with 5 carboxylate units and 3 "
                   "methoxy-PEG methacrylate side chains of 8 EO units, random sequence, methyl end groups, "
                   "sodium counter-ions.",
        "spec": {"builder": "pce", "force_field": "pcff",
                 "monomers": {"A": {"kind": "acid", "alpha_methyl": True, "deprotonated": True},
                              "E": {"kind": "ester_peg", "alpha_methyl": True, "eo_units": 8, "end": "OCH3"}},
                 "composition": {"A": 5, "E": 3}, "sequence": "random", "end_groups": ["CH3", "CH3"],
                 "n_chains": 1, "counterion": "Na+", "seed": 4},
        "explanation": "MPEG = methacrylate ester (ester_peg, alpha_methyl true). Methoxy-capped side chain = "
                       "end OCH3. Backbone length = 5 + 3 = 8 units.",
    },
    "pce_ether_explicit": {
        "request": "A TPEG-type PCE in CVFF-INTERFACE with the exact backbone sequence A-T-A-A-T-A-A-A: "
                   "A = acrylate (carboxylate), T = isoprenyl-ether PEG side chain of 9 EO units with an OH end; "
                   "H at the head, CH3 at the tail, calcium counter-ions.",
        "spec": {"builder": "pce", "force_field": "cvff",
                 "monomers": {"A": {"kind": "acid", "alpha_methyl": False, "deprotonated": True},
                              "T": {"kind": "ether_peg", "alpha_methyl": True, "spacer": 2, "eo_units": 9, "end": "OH"}},
                 "composition": {"A": 6, "T": 2}, "sequence": ["A", "T", "A", "A", "T", "A", "A", "A"],
                 "end_groups": ["H", "CH3"], "n_chains": 1, "counterion": "Ca2+", "seed": 2},
        "explanation": "TPEG = isoprenyl ether: ether_peg, alpha_methyl true, spacer 2. An explicit sequence lists "
                       "every unit in chain order; composition must count the same units. 6 carboxylates need "
                       "3 Ca2+.",
    },
    "pce_maleic": {
        "request": "An alternating maleic-HPEG PCE in PCFF-INTERFACE: 4 maleate units with one of the two "
                   "carboxyls deprotonated, alternating with 4 methallyl-ether PEG side chains of 5 EO units "
                   "(OH ends); potassium counter-ions.",
        "spec": {"builder": "pce", "force_field": "pcff",
                 "monomers": {"M": {"kind": "diacid", "deprotonated": 1},
                              "P": {"kind": "ether_peg", "alpha_methyl": True, "spacer": 1, "eo_units": 5, "end": "OH"}},
                 "composition": {"M": 4, "P": 4}, "sequence": "alternating", "end_groups": ["CH3", "CH3"],
                 "n_chains": 1, "counterion": "K+", "seed": 6},
        "explanation": "Maleic unit = diacid; deprotonated counts carboxylates per unit (0, 1 or 2). "
                       "HPEG = methallyl ether: ether_peg, alpha_methyl true, spacer 1.",
    },
    "pce_partial_two_chains": {
        "request": "Two identical PCE chains in PCFF-INTERFACE, each a block copolymer: 3 acrylate (COO-) "
                   "units, then 3 acrylic acid (COOH) units, then 2 acrylate-ester PEG side chains of 6 EO "
                   "units with OH ends; sodium counter-ions.",
        "spec": {"builder": "pce", "force_field": "pcff",
                 "monomers": {"A": {"kind": "acid", "alpha_methyl": False, "deprotonated": True},
                              "H": {"kind": "acid", "alpha_methyl": False, "deprotonated": False},
                              "E": {"kind": "ester_peg", "alpha_methyl": False, "eo_units": 6, "end": "OH"}},
                 "composition": {"A": 3, "H": 3, "E": 2}, "sequence": "block", "end_groups": ["CH3", "CH3"],
                 "n_chains": 2, "counterion": "Na+", "seed": 8},
        "explanation": "Partial deprotonation = two acid labels (deprotonated and not). 'block' keeps the order "
                       "of the composition list. n_chains repeats the architecture; each chain gets its own "
                       "counter-ions.",
    },
    "composite": {
        "request": "A small MPEG-type PCE (2 methacrylate carboxylates, 1 methoxy-PEG methacrylate side chain "
                   "of 3 EO units) lying flat 3.5 Å above the (002) surface of monosulfate (AFm), in "
                   "PCFF-INTERFACE, sodium counter-ions; repeat the surface laterally as needed.",
        "spec": {"builder": "composite", "force_field": "pcff",
                 "surface": {"model": "monosulfate_002_surface", "supercell": "auto"},
                 "pce": {"monomers": {"A": {"kind": "acid", "alpha_methyl": True, "deprotonated": True},
                                      "E": {"kind": "ester_peg", "alpha_methyl": True, "eo_units": 3, "end": "OCH3"}},
                         "composition": {"A": 2, "E": 1}, "sequence": "random", "end_groups": ["CH3", "CH3"],
                         "n_chains": 1, "counterion": "Na+", "seed": 5},
                 "height": 3.5, "orientation": "flat"},
        "explanation": "surface.model must be a slab with a vacuum gap; 'auto' repeats it laterally until the "
                       "PCE fits (or give [na, nb, nc] with 1 along the surface normal). height is measured "
                       "from the topmost slab atom.",
    },
}

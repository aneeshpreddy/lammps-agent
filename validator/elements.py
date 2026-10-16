"""Standard atomic weights for the elements that can occur in the project's systems.

Values: IUPAC 2021 abridged/conventional standard atomic weights (CIAAW). Older force-field tables
use earlier editions (e.g. H 1.00794 or 1.00797, Ca 40.08); the P2.6 tolerance τ_m covers that.
"""
STANDARD_MASS = {
    "H": 1.008, "Li": 6.94, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06,
    "Cl": 35.45, "K": 39.098, "Ar": 39.95, "Ca": 40.078, "Fe": 55.845, "Zn": 65.38,
    "Sr": 87.62, "Cs": 132.91, "Ba": 137.33,
}


def nearest_element(mass: float):
    """Element whose standard mass is closest to `mass` (diagnostic only, never a verdict)."""
    return min(STANDARD_MASS.items(), key=lambda kv: abs(kv[1] - mass))

"""Deterministic validator for LAMMPS DATA FILEs (Tiers 0-3 + TC). See docs/PROPERTIES.md."""
__version__ = "1.0.0"

from .config import load_config  # noqa: E402
from .core import validate  # noqa: E402
from .result import ValidationResult, CheckResult  # noqa: E402

__all__ = ["validate", "load_config", "ValidationResult", "CheckResult", "__version__"]

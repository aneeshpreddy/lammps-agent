"""Result types shared by every tier (schema: plan Appendix B, PROPERTIES §8.2)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PASS = "PASS"
FAIL = "FAIL"
NOT_EVALUATED = "NOT_EVALUATED"      # a dependency failed or required input is missing
NOT_CALIBRATED = "NOT_CALIBRATED"    # tolerance not derived yet; never counts as PASS
NOT_APPLICABLE = "NOT_APPLICABLE"    # property does not apply under the declared configuration
VERDICTS = (PASS, FAIL, NOT_EVALUATED, NOT_CALIBRATED, NOT_APPLICABLE)

TIERS = (0, 1, 2, 3)


@dataclass
class CheckResult:
    name: str
    property: str
    tier: Any                      # 0..3 or "TC"
    verdict: str
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    calibration: Optional[str] = None   # e.g. "provisional:pce_emc_solvated@v1"

    def __post_init__(self):
        if self.verdict not in VERDICTS:
            raise ValueError(f"unknown verdict {self.verdict!r}")

    @property
    def passed(self) -> bool:
        return self.verdict == PASS

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "name": self.name,
            "property": self.property,
            "tier": self.tier,
            "verdict": self.verdict,
            "passed": self.passed,
            "message": self.message,
        }
        if self.details:
            d["details"] = self.details
        if self.warnings:
            d["warnings"] = self.warnings
        if self.calibration:
            d["calibration"] = self.calibration
        return d


def _tier_ok(checks: List[CheckResult]) -> bool:
    return all(c.verdict in (PASS, NOT_APPLICABLE) for c in checks)


@dataclass
class ValidationResult:
    file: str
    config_id: str
    checks: List[CheckResult] = field(default_factory=list)
    lammps: Dict[str, Any] = field(default_factory=lambda: {"ran": False, "returncode": None, "errors": []})
    elapsed_s: float = 0.0
    sha256: str = ""
    validator_version: str = ""

    # --- derived -------------------------------------------------------------------------
    def by_tier(self, tier) -> List[CheckResult]:
        return [c for c in self.checks if c.tier == tier]

    @property
    def tier_reached(self) -> int:
        """Highest tier t such that every check in tiers 0..t is PASS/NOT_APPLICABLE (-1: none)."""
        reached = -1
        for t in TIERS:
            checks = self.by_tier(t)
            if not checks or not _tier_ok(checks):
                break
            reached = t
        return reached

    @property
    def passed(self) -> bool:
        """True only if every Tier 0-3 check is PASS or NOT_APPLICABLE."""
        core = [c for c in self.checks if c.tier in TIERS]
        return bool(core) and _tier_ok(core) and self.tier_reached == 3

    @property
    def verdict(self) -> str:
        core = [c for c in self.checks if c.tier in TIERS]
        if any(c.verdict == FAIL for c in core):
            return FAIL
        return PASS if self.passed else "INCOMPLETE"

    @property
    def tc_passed(self) -> Optional[bool]:
        """None if no TC check could be evaluated; else True only if every evaluated TC check PASSed."""
        evaluated = [c for c in self.checks if c.tier == "TC" and c.verdict in (PASS, FAIL, NOT_CALIBRATED)]
        if not evaluated:
            return None
        return all(c.verdict == PASS for c in evaluated)

    def failing(self) -> List[CheckResult]:
        return [c for c in self.checks if c.verdict == FAIL]

    def get(self, prop: str) -> Optional[CheckResult]:
        for c in self.checks:
            if c.property == prop:
                return c
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "sha256": self.sha256,
            "config_id": self.config_id,
            "validator_version": self.validator_version,
            "passed": self.passed,
            "verdict": self.verdict,
            "tier_reached": self.tier_reached,
            "tc_passed": self.tc_passed,
            "checks": [c.to_dict() for c in self.checks],
            "lammps": self.lammps,
            "elapsed_s": round(self.elapsed_s, 3),
        }

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_dict(), indent=kw.pop("indent", 2), default=str, **kw)

    def summary(self) -> str:
        lines = [f"{self.file}: {self.verdict} (tier_reached={self.tier_reached}, config={self.config_id})"]
        for c in self.checks:
            if c.verdict in (PASS, NOT_APPLICABLE):
                continue
            lines.append(f"  [{c.verdict}] T{c.tier} {c.property} {c.name}: {c.message}")
        return "\n".join(lines)

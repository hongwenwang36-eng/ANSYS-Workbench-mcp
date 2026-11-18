"""Read numerical evidence and locate potentially actionable solver messages."""
import csv
import math
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, FiniteFloat, model_validator


class MetricLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    unit: str
    minimum: FiniteFloat | None = None
    maximum: FiniteFloat | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if not self.metric.strip() or (self.minimum is None and self.maximum is None):
            raise ValueError("Specify a metric and at least one bound")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum exceeds maximum")
        return self


def verify(path, criteria):
    if not criteria or len({rule.metric for rule in criteria}) != len(criteria):
        raise ValueError("Provide a nonempty list of unique metric criteria")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"metric", "unit", "value"}.issubset(reader.fieldnames or ()):
            raise ValueError("CSV requires metric,unit,value columns")
        measured = {}
        for row in reader:
            metric = row["metric"]
            if metric in measured:
                raise ValueError(f"Duplicate metric: {metric}")
            measured[metric] = row
    checks = []
    for rule in criteria:
        row = measured.get(rule.metric)
        check = {**rule.model_dump(), "passed": False}
        if row is None:
            check["reason"] = "missing metric"
        elif row["unit"] != rule.unit:
            check.update(reason="unit mismatch", measured_unit=row["unit"])
        else:
            try:
                value = float(row["value"])
                if not math.isfinite(value):
                    raise ValueError()
                passed = ((rule.minimum is None or value >= rule.minimum)
                          and (rule.maximum is None or value <= rule.maximum))
                check.update(value=value, passed=passed)
            except (TypeError, ValueError):
                check["reason"] = "invalid numerical value"
        checks.append(check)
    return {"ok": all(c["passed"] for c in checks), "source": str(path.resolve()), "checks": checks}


RULES = [
    ("license", r"license checkout failed|licensing error|no valid licen[cs]e|licensed number of users already reached|cannot connect to license server", "Check feature availability and license server connectivity."),
    ("mesh", r"negative (?:cell )?volume|highly distorted|excessive element distortion", "Inspect affected cells/elements and the last valid geometry."),
    ("constraint", r"zero pivot|small equation solver pivot|singular matrix", "Check material stiffness, constraints and contact status."),
    ("convergence", r"floating point exception|divergence detected|did not converge|not converged|convergence failure", "Inspect load step, residual history and monitored quantities."),
    ("file", r"file not found|no such file|cannot open (?:the )?file", "Resolve the path against the solver working directory."),
    ("script", r"syntaxerror|traceback \(most recent call last\)|unknown command|unrecognized command", "Check the failing command in the interpreter for this solver version."),
    ("solver", r"\*{3}\s*(?:fatal|error)\s*\*{3}|^\s*(?:fatal error|error)\s*:", "Read the error and preceding solver messages."),
]
PATTERNS = [(kind, re.compile(expr, re.I), hint) for kind, expr, hint in RULES]


def diagnose(path: Path):
    findings = []
    total = 0
    with path.open(encoding="utf-8-sig", errors="replace") as stream:
        for index, line in enumerate(stream, 1):
            for kind, pattern, hint in PATTERNS:
                if pattern.search(line):
                    total += 1
                    if len(findings) < 50:
                        findings.append({"line": index, "category": kind,
                                         "text": line.strip()[:800], "suggestion": hint})
                    break
    return {"source": str(path.resolve()), "matches": total, "findings": findings}

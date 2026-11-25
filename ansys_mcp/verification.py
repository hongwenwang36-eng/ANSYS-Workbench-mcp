"""Numerical checks against measured quantities with explicit signs, scales and units."""

import csv
import math

from pydantic import BaseModel, Field, FiniteFloat, ConfigDict


class Equation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    unit: str
    terms: dict[str, FiniteFloat] = Field(min_length=1)
    reference: FiniteFloat = 0
    atol: FiniteFloat = Field(ge=0)
    rtol: FiniteFloat = Field(default=0, ge=0)
    scale: FiniteFloat | None = Field(default=None, gt=0)


def equations(path, rules):
    if not rules:
        raise ValueError("Supply at least one check")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"metric", "value", "unit"}.issubset(reader.fieldnames or ()):
            raise ValueError("Expected metric,unit,value CSV")
        data = {}
        for row in reader:
            if row["metric"] in data:
                raise ValueError("Duplicate metric: " + row["metric"])
            data[row["metric"]] = row
    checks = []
    for rule in rules:
        check = dict(name=rule.name, unit=rule.unit, passed=False)
        try:
            values = []
            for key, weight in rule.terms.items():
                row = data[key]
                if row["unit"] != rule.unit:
                    raise ValueError("Unit mismatch for " + key)
                value = float(row["value"])
                if not math.isfinite(value) or weight == 0:
                    raise ValueError("Nonfinite measurement or zero coefficient")
                values.append(weight * value)
            measured = math.fsum(values)
            scale = (
                rule.scale
                if rule.scale is not None
                else max(abs(rule.reference), max(map(abs, values)))
            )
            error = abs(measured - rule.reference)
            tolerance = rule.atol + rule.rtol * scale
            check.update(
                measured=measured,
                reference=rule.reference,
                error=error,
                tolerance=tolerance,
                passed=math.isfinite(error)
                and math.isfinite(tolerance)
                and error <= tolerance,
            )
        except (ValueError, KeyError, OverflowError) as exc:
            check["reason"] = str(exc)
        checks.append(check)
    return {
        "ok": all(c["passed"] for c in checks),
        "source": str(path),
        "checks": checks,
    }


def refinement(path, quantity, unit, tolerance, atol=0):
    if not (0 <= tolerance and 0 <= atol and math.isfinite(tolerance + atol)):
        raise ValueError("Provide finite nonnegative tolerances")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["metric"] == quantity]
    if len(rows) < 3 or any(r["unit"] != unit for r in rows):
        raise ValueError("Supply >=3 refinements of one quantity in the requested unit")
    samples = sorted(
        ((float(r["spacing"]), float(r["value"])) for r in rows), reverse=True
    )
    if any(
        h <= 0 or not math.isfinite(h) or not math.isfinite(v) for h, v in samples
    ) or len({h for h, v in samples}) != len(samples):
        raise ValueError("Spacings must be distinct, finite, positive values")
    changes = [abs(curr[1] - prev[1]) for prev, curr in zip(samples, samples[1:])]
    bound = atol + tolerance * abs(samples[-1][1])
    return {
        "ok": changes[-1] <= bound and changes[-1] <= changes[-2],
        "source": str(path),
        "quantity": quantity,
        "unit": unit,
        "samples": samples,
        "changes": changes,
        "fine_pair_tolerance": bound,
    }


def coupling(path, end_time, rms_limit, force_rtol, force_atol):
    if (
        not all(
            math.isfinite(x) and x >= 0
            for x in (end_time, rms_limit, force_rtol, force_atol)
        )
        or end_time == 0
    ):
        raise ValueError("Supply a positive end time and finite nonnegative tolerances")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        rms = [k for k in headers if "RMS Change in Target Value" in k]
        forces = [
            k for k in headers if k.startswith("Force (Sum):") and k.endswith(" x")
        ]
        if (
            len(rms) < 2
            or len(forces) != 2
            or not all(
                any(word in k.casefold() for k in rms)
                for word in ("force", "displacement")
            )
        ):
            raise ValueError(
                "Expected a two-way System Coupling force/displacement interface CSV"
            )
        final = {}
        previous_iteration = -1
        previous_step = None
        for row in reader:
            step = int(row["Step"])
            iteration = int(row["Iteration"])
            if previous_step is not None and (
                step < previous_step
                or step > previous_step + 1
                or (step == previous_step and iteration <= previous_iteration)
            ):
                raise ValueError("Missing steps or unordered coupling history")
            previous_step = step
            previous_iteration = iteration
            final[step] = row
    records = []
    previous_time = 0
    for step, row in final.items():
        t = float(row["Time"])
        changes = [float(row[k]) for k in rms]
        a, b = ([float(row[column[:-1] + axis]) for axis in "xyz"] for column in forces)
        if (
            not all(math.isfinite(x) for x in [t, *changes, *a, *b])
            or t <= previous_time
            or min(changes) < 0
        ):
            raise ValueError("Invalid time or interface data")
        previous_time = t
        difference = math.dist(a, b)
        bound = force_atol + force_rtol * max(math.hypot(*a), math.hypot(*b))
        records.append(
            dict(
                step=step,
                time=t,
                rms=dict(zip(rms, changes)),
                force_difference=difference,
                force_tolerance=bound,
                passed=max(changes) <= rms_limit and difference <= bound,
            )
        )
    complete = (
        bool(records)
        and records[0]["step"] == 1
        and math.isclose(previous_time, end_time, rel_tol=1e-7, abs_tol=1e-12)
    )
    return {
        "ok": complete and all(r["passed"] for r in records),
        "source": str(path),
        "completed_requested_time": complete,
        "steps": records,
    }

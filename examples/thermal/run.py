"""Run the thermal acceptance cases via the repository MCP implementations."""
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
import mcp_server as mcp


def main():
    out = ROOT / "runs" / ("thermal_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    out.mkdir(parents=True)
    print(out, flush=True)
    rows = []
    for name, hot in [("steady", 100), ("steady", 60), ("transient_expansion", None)]:
        case = out / (name if hot is None else f"{name}_{hot}")
        case.mkdir()
        deck = (HERE / f"{name}.dat").read_text("ascii")
        if hot is not None:
            deck = deck.replace("hotend=100", f"hotend={hot}")
        source = case / "input.dat"
        source.write_text(deck, encoding="ascii")
        job = json.loads(mcp.run_mapdl_input(str(source), str(case), "bar"))
        (case / "execution.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        if not job["ok"]:
            raise RuntimeError(f"Inspect {case / 'bar.out'}")
        log_text = (case / "bar.out").read_text(encoding="utf-8", errors="replace")
        if "*** ERROR ***" in log_text or "*** FATAL ***" in log_text:
            raise RuntimeError(f"Solver error in {case / 'bar.out'}")
        required = ["bar.rth"] + (["bar.rst"] if hot is None else [])
        if any(not (case / name).is_file() or (case / name).stat().st_size == 0 for name in required):
            raise RuntimeError(f"Missing result file in {case}")
        specs = ([("mid_temperature", "degC", (20 + hot) / 2),
                  ("hot_end_heat", "W", 45 * 0.0004 * (hot - 20) / 0.1),
                  ("cold_end_heat", "W", -45 * 0.0004 * (hot - 20) / 0.1)]
                 if hot is not None else [("temperature_5s", "degC", 30),
                   ("temperature_10s", "degC", 40), ("tip_ux", "m", 2.4e-5)])
        metrics = case / ("steady_metrics.csv" if hot is not None else "expansion_metrics.csv")
        with metrics.open() as f:
            measured = [float(x) for x in next(csv.reader(f))]
        if len(measured) != len(specs):
            raise RuntimeError(f"Missing metric in {metrics}")
        for actual, (metric, unit, reference) in zip(measured, specs):
            # Linear benchmarks have exact discrete solutions on this mesh.
            passed = math.isclose(actual, reference, rel_tol=1e-5, abs_tol=1e-12)
            rows.append([case.name, metric, unit, actual, reference, passed])
        images = sorted(case.glob("*.png"))
        expected_images = 2
        if len(images) != expected_images or not all(p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for p in images):
            raise RuntimeError(f"Expected {expected_images} fresh PNG images in {case}")
    with (out / "verification.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "metric", "unit", "actual", "reference", "passed"])
        writer.writerows(rows)
    if not all(row[-1] for row in rows):
        raise RuntimeError(f"Physical check failed; inspect {out / 'verification.csv'}")
    print("Passed all nine scalar checks.", flush=True)


if __name__ == "__main__":
    main()

"""Create a new SpaceClaim bar, solve in Mechanical, and re-open the project."""
import csv
import json
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
import mcp_server as mcp


def main():
    root = ROOT / "runs" / ("thermal_mech_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    root.mkdir()
    print(root, flush=True)
    solid = root / "bar.scdocx"
    geometry = root / "geometry.py"
    geometry.write_text("BlockBody.Create(Point.Create(0, 0, 0), Point.Create(0.1, 0.02, 0.02))\n"
                        f"DocumentSave.Execute({str(solid)!r})\n", encoding="utf-8")
    sc = json.loads(mcp.run_spaceclaim_script(str(geometry), str(root), expected_output=str(solid)))
    (root / "geometry.json").write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
    if not sc["ok"]:
        raise RuntimeError(root / "geometry.json")
    shutil.copyfile(HERE / "mechanical.py", root / "mechanical.py")
    journal = root / "run.wbjn"
    journal.write_text((HERE / "mechanical.wbjn").read_text().replace("__RUN_DIR__", repr(str(root))), encoding="utf-8")
    result = json.loads(mcp.run_workbench_journal(str(journal), str(root), log_file=str(root / "workbench.log"),
        completion_marker="REOPEN_MECHANICAL_PASSED", expected_output=str(root / "thermal_mechanical.wbpj"), timeout_seconds=900))
    (root / "execution.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if not result["ok"]:
        raise RuntimeError(root / "workbench.log")
    for name in ("temperature", "heat_flux"):
        if not (root / (name + ".png")).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(f"Invalid PNG for {name}")
        with (root / (name + ".csv")).open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        if not rows or any(not math.isfinite(float(row["value"])) for row in rows):
            raise RuntimeError(f"Missing or non-finite nodal data for {name}")
        if name == "temperature":
            error = max(abs(float(row["value"]) - (20 + 80 * float(row["x_fraction"]))) for row in rows)
            if error > 1e-4:
                raise RuntimeError(f"Nodal temperature error: {error}")
            (root / "verification.json").write_text(json.dumps({
                "passed": True, "nodes": len(rows), "max_temperature_error_degC": error,
                "absolute_tolerance_degC": 1e-4
            }, indent=2), encoding="utf-8")
    print(root / "thermal_mechanical.wbpj")


if __name__ == "__main__":
    main()

"""Run isolated CFD and FSI acceptance cases with the repository MCP functions."""
import argparse
import base64
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import mcp_server as mcp
from duct_mesh import duct
from cht_mesh import generate

EXAMPLES = Path(__file__).parent
DATA_REV = "c283ea5a153158b62fa429ae06e7cc802f7263c2"


def download(relative, target):
    url = f"https://api.github.com/repos/ansys/example-data/contents/{relative}?ref={DATA_REV}"
    with urlopen(Request(url, headers={"User-Agent": "ANSYS-Workbench-mcp"}), timeout=60) as response:
        info = json.load(response)
    payload = base64.b64decode(info["content"])
    if len(payload) != info["size"]:
        raise ValueError(f"Incomplete download: {relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def call(directory, name, function, *args, **kwargs):
    result = json.loads(function(*args, **kwargs))
    (directory / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    process = result.get("process", {})
    messages = process.get("stdout", "") + process.get("stderr", "")
    if not result.get("ok") or "Error Object:" in messages:
        raise RuntimeError(f"{name} failed, inspect {directory / (name + '.json')}")
    return result


def write_metrics(directory, checks):
    units = {"outlet_temperature":"K", "outlet_temperature_K":"K",
             "interface_heat":"W", "shadow_heat":"W", "heat_balance_W":"W",
             "outlet_velocity":"m/s", "outlet_velocity_m_s":"m/s",
             "force_x_difference_N":"N", "final_time_s":"s",
             "outlet_pressure_Pa":"Pa", "image_bytes":"byte"}
    with (directory / "metrics.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream)
        writer.writerow(["metric","unit","value"])
        writer.writerows((name, units.get(name,"1"), value)
                         for name,value in checks.items() if type(value) in (float,int))


def run(case, directory, post_only=False):
    directory.mkdir(parents=True, exist_ok=post_only)
    if case == "fsi":
        if not post_only:
            for file in ("fluent.scp", "mapdl.scp", "Fluent/plate.cas.gz", "MAPDL/mapdl.dat"):
                download("pysystem-coupling/oscillating_plate/" + file, directory / file)
            call(directory, "solver", mcp.run_system_coupling_script,
                 str(EXAMPLES / "plate.py"), str(directory), 600)
        with (directory / "SyC/Interface-1.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        final = rows[-1]
        values = list(final.values())
        checks = {"final_time_s": float(final["Time"]), "force_transfer_rms": float(values[3]),
                  "displacement_transfer_rms": float(values[10]),
                  "force_x_difference_N": abs(float(values[4]) - float(values[7]))}
        call(directory, "post", mcp.run_mapdl_input, str(EXAMPLES / "fsi_post.inp"),
             str(directory / "MAPDL"), "fsi_post", 180)
        checks["passed"] = abs(checks["final_time_s"] - 1) < 1e-9 and max(checks["force_transfer_rms"], checks["displacement_transfer_rms"]) < .01 and checks["force_x_difference_N"] < 1e-8
    elif case == "cfx":
        definition = mcp.CFX_SOLVE.parents[1] / "examples/StaticMixer.def"
        if not post_only:
            call(directory, "solver", mcp.run_cfx_solver, str(definition), str(directory), "mixer")
        result_file = next(directory.glob("*.res"))
        call(directory, "post", mcp.run_cfx_post_session, str(EXAMPLES / "outlet.cse"),
             str(directory), str(result_file), expected_output=str(directory / "outlet.png"))
        log = next(directory.glob("*.out")).read_text(errors="replace")
        checks = {"target_criteria_reached": "All target criteria reached" in log,
                  "image_bytes": (directory / "outlet.png").stat().st_size}
        with (directory / "outlet.csv").open() as stream:
            row = list(csv.reader(stream))[1]
        checks["outlet_temperature_K"] = float(row[1])
        checks["outlet_pressure_Pa"] = float(row[0])
        checks["passed"] = checks["target_criteria_reached"] and checks["image_bytes"] > 1000 and abs(checks["outlet_temperature_K"] - 300) < .01
    else:
        if case == "duct":
            if not post_only:
                duct(directory / "duct.msh")
            journal = "duct.jou"
        elif case == "cht":
            if not post_only:
                generate(directory / "cht.msh")
            journal = "cht.py"
        else:
            if not post_only:
                download("pyfluent/cavitation/cav.msh.gz", directory / "cav.msh.gz")
            journal = "cavitation.py"
        if not post_only:
            result = call(directory, "solver", mcp.run_fluent_journal,
                          str(EXAMPLES / journal), str(directory), dimension="2d", timeout_seconds=600)
        else:
            result = json.loads((directory / "solver.json").read_text(encoding="utf-8"))
        transcript = result["process"]["stdout"] + result["process"]["stderr"]
        checks = {"converged": "solution is converged" in transcript,
                  "journal_error": "Error Object:" in transcript,
                  "case_files": [p.name for p in directory.glob("*.cas.h5")],
                  "data_files": [p.name for p in directory.glob("*.dat.h5")]}
        if case == "cavitation":
            rows = [line.split() for line in transcript.splitlines()
                    if re.match(r"^\s*\d+\s+\d+\.\d+e[-+]\d+", line)]
            residuals = [float(value) for value in rows[-1][1:7]] if rows else []
            checks["maximum_final_residual"] = max(residuals) if residuals else 1.0
            checks["residuals_passed"] = len(residuals) == 6 and max(residuals) < 1e-5
        if case == "duct":
            velocity = re.findall(r"outlet\s+([\d.eE+-]+)", transcript)
            checks["outlet_velocity_m_s"] = float(velocity[-1]) if velocity else None
            checks["velocity_passed"] = checks["outlet_velocity_m_s"] is not None and abs(checks["outlet_velocity_m_s"] - 1) < 1e-5
        checks["passed"] = checks["converged"] and not checks["journal_error"] and bool(checks["case_files"]) and bool(checks["data_files"]) and checks.get("velocity_passed", True) and checks.get("residuals_passed", True)
    if case in {"duct", "cht", "cavitation"}:
        call(directory, "post", mcp.run_fluent_journal,
             str(EXAMPLES / (case + "_post.py")), str(directory), dimension="2d", gui=True, extra_args="-gu", timeout_seconds=240)
        if case in {"duct", "cht"}:
            metrics = json.loads((directory / "metrics.json").read_text())
            checks.update({key: value[0] for group in metrics for key,value in group.items()})
        if case == "cht":
            checks["heat_balance_W"] = abs(checks["interface_heat"] + checks["shadow_heat"])
            checks["passed"] = checks["passed"] and checks["heat_balance_W"] < 1e-6 and 300 < checks["outlet_temperature"] <= 350.001
    checks["image_files"] = [p.name for p in directory.rglob("*.png") if p.stat().st_size > 1000]
    checks["passed"] = checks["passed"] and bool(checks["image_files"])
    write_metrics(directory, checks)
    (directory / "verification.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(directory)
    print(json.dumps(checks, indent=2))
    if not checks["passed"]:
        raise RuntimeError("Acceptance checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=["duct", "cfx", "cht", "cavitation", "fsi"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--post-only", action="store_true", help="Re-evaluate an existing run selected by --output")
    args = parser.parse_args()
    output = args.output or ROOT / "runs" / ("fluid-" + args.case + "-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    if args.post_only and not args.output:
        parser.error("--post-only requires --output")
    run(args.case, output.resolve(), args.post_only)

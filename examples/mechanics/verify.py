"""Run structural verification cases through this checkout's MAPDL tool (SI units)."""

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mcp_server import run_mapdl_input

DECKS = Path(__file__).parent / "decks"
CASES = (
    "static",
    "contact",
    "plastic",
    "modal",
    "prestress",
    "harmonic",
    "transient",
    "spectrum",
    "random",
)

OMEGA2 = [5000 * (3 - math.sqrt(5)), 5000 * (3 + math.sqrt(5))]
# Modal mass is 1 after normalisation (M=I).
RATIOS = [2 - w2 / 10000 for w2 in OMEGA2]
TIP = [r / math.sqrt(1 + r * r) for r in RATIOS]
PARTICIPATION = [(1 + r) / math.sqrt(1 + r * r) for r in RATIOS]


def reference(case):
    if case == "prestress":
        return math.sqrt(100 + 2 * 10) / (2 * math.pi)
    if case == "plastic":
        return 50.0 + 1000.0 * (0.01 - 0.005)
    if case == "contact":
        return -100.0
    if case == "static":
        return 0.02
    if case == "modal":
        return math.sqrt(OMEGA2[0]) / (2 * math.pi)
    if case == "harmonic":
        return 100 * sum(
            u * u / (w2 - (10 * math.pi) ** 2) for u, w2 in zip(TIP, OMEGA2)
        )
    if case == "transient":
        return 100 * sum(
            u * u * (1 - math.cos(math.sqrt(w2) * 0.02)) / w2
            for u, w2 in zip(TIP, OMEGA2)
        )
    if case == "spectrum":
        return math.sqrt(
            sum((u * g / w2) ** 2 for u, g, w2 in zip(TIP, PARTICIPATION, OMEGA2))
        )
    if case == "random":
        # One-sided unit force PSD over [1,100] Hz, integrate the full transfer function.
        n = 20000
        df = 99 / n
        variance = 0
        for i in range(n):
            w = 2 * math.pi * (1 + (i + 0.5) * df)
            h = sum(
                u * u / complex(w2 - w * w, 0.04 * w * math.sqrt(w2))
                for u, w2 in zip(TIP, OMEGA2)
            )
            variance += abs(h) ** 2 * df
        return math.sqrt(variance)
    raise ValueError(case)


def deck(case):
    parts = []
    if case not in ("contact", "prestress"):
        parts.append("axial_model")
    if case in ("modal", "random", "spectrum"):
        parts.append("extract_modes")
    if case != "modal":
        parts.append(case)
    commands = ["/batch"]
    commands.extend(
        (DECKS / (part + ".inp")).read_text(encoding="ascii") for part in parts
    )
    readset = {
        "modal": "set,1,1",
        "prestress": "set,1,1",
        "random": "set,3,1",
        "spectrum": "*get,jobbase,active,0,jobnam\n/input,%jobbase%,mcom",
    }.get(case, "set,last")
    quantity = "*get,value,node,9,u,x"
    plot = "plnsol,u,x"
    if case in ("modal", "prestress"):
        quantity = "*get,value,mode,1,freq"
        plot = "plnsol,u,sum"
    elif case == "plastic":
        quantity = "*get,value,node,9,rf,fx"
        plot = "plnsol,s,x"
    elif case == "contact":
        quantity = """value=0
*do,i,13,16
*get,rfpart,node,i,rf,fx
value=value+rfpart
*enddo"""
    commands.extend(["save", "/post1"])
    if case in ("transient", "harmonic"):
        count_command = (
            "*get,nsets,active,0,set,nset" if case == "transient" else "nsets=5"
        )
        commands.extend(
            [
                count_command,
                """*cfopen,response,csv
*do,ii,1,nsets
set,1,ii,,real
*get,abscissa,active,0,set,time
*get,ux,node,9,u,x
*vwrite,abscissa,ux
(E23.15,',',E23.15)
*enddo
*cfclos""",
            ]
        )
    commands.extend(
        [
            readset,
            quantity,
            "*cfopen,measurement,csv",
            "*vwrite,value",
            "(E23.15)",
            "*cfclos",
            "/graphics,full",
            "/view,1,1,2,3",
            "/show,png",
            plot,
            "/show,close",
            "finish",
            "/exit,nosave",
            "",
        ]
    )
    return "\n".join(commands)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", metavar="CASE", help=", ".join(CASES))
    args = parser.parse_args()
    if len(args.cases) != len(set(args.cases)) or set(args.cases) - set(CASES):
        parser.error("Choose distinct cases from " + ", ".join(CASES))
    runs = ROOT / "runs" / "mechanics"
    runs.mkdir(parents=True, exist_ok=True)
    session = Path(mkdtemp(dir=runs, prefix="bench-"))
    rows = []
    for case in args.cases or CASES:
        expected = reference(case)
        folder = session / case
        folder.mkdir()
        inp = folder / "benchmark.inp"
        inp.write_text(deck(case), encoding="ascii")
        reply = json.loads(run_mapdl_input(str(inp), str(folder), "bench", 180))
        measured = None
        evidence = folder / "measurement.csv"
        if evidence.exists():
            try:
                measured = float(evidence.read_text().strip())
            except ValueError:
                pass
        tolerance = 0.03 if case == "random" else 0.005
        relative_error = (
            None if measured is None else abs(measured - expected) / abs(expected)
        )
        log = folder / "bench.out"
        png = list(folder.glob("*.png"))
        ok = (
            reply["ok"]
            and log.exists()
            and "*** ERROR ***" not in log.read_text(errors="replace")
            and (folder / "bench.rst").is_file()
            and (folder / "bench.db").is_file()
            and any(p.stat().st_size > 1000 for p in png)
            and relative_error is not None
            and relative_error <= tolerance
        )
        if case in ("harmonic", "transient"):
            history = folder / "response.csv"
            count = 5 if case == "harmonic" else 400
            records = (
                list(csv.reader(history.read_text().splitlines()))
                if history.exists()
                else []
            )
            ok = (
                ok
                and len(records) == count
                and all(
                    len(record) == 2 and all(math.isfinite(float(v)) for v in record)
                    for record in records
                )
            )
        row = dict(
            case=case,
            unit="Hz"
            if case in ("modal", "prestress")
            else "N"
            if case in ("contact", "plastic")
            else "m",
            measured=measured,
            expected=expected,
            relative_error=relative_error,
            tolerance=tolerance,
            passed=ok,
        )
        rows.append(row)
        print(case, row, folder, flush=True)
    with (session / "checks.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

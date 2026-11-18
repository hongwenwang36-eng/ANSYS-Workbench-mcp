"""Build, solve, reopen, and verify a Workbench project of Mechanical APDL systems."""

import argparse
import csv
import json
import math
from pathlib import Path
from tempfile import mkdtemp

from verify import CASES, ROOT, deck, reference
from mcp_server import run_workbench_journal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", help=", ".join(CASES))
    cases = parser.parse_args().cases or list(CASES)
    if set(cases) - set(CASES) or len(set(cases)) != len(cases):
        parser.error("Select distinct cases from " + ", ".join(CASES))
    runs = ROOT / "runs" / "mechanics"
    runs.mkdir(parents=True, exist_ok=True)
    folder = Path(mkdtemp(prefix="workbench-", dir=runs))
    project = folder / "mechanics.wbpj"
    marker = folder / "reopen.log"
    journal = folder / "build.wbjn"
    inputs = []
    for case in cases:
        source = folder / (case + ".dat")
        # Distinct names allow auditing the Workbench solver directories after reopening.
        script = deck(case).replace("/exit,nosave", "").replace(
            "*cfopen,measurement,csv", "*cfopen," + case + "_value,csv"
        )
        source.write_text(script, encoding="ascii")
        inputs.append((case, str(source)))
    journal.write_text(
        f"""# encoding: utf-8
import traceback
log = open({str(marker)!r}, "w")
try:
    Reset()
    project = {str(project)!r}
    inputs = {inputs!r}
    for label, source in inputs:
        system = GetTemplate(TemplateName="Mechanical APDL").CreateSystem()
        system.DisplayText = label
        system.GetContainer(ComponentName="Setup").AddInputFile(FilePath=source)
    Save(FilePath=project, Overwrite=True)
    Update()
    Save(FilePath=project, Overwrite=True)
    Reset()
    Open(FilePath=project)
    labels = sorted([system.DisplayText for system in GetAllSystems()])
    log.write(str(labels) + "\\n")
    if labels != sorted([label for label, source in inputs]):
        raise ValueError("Unexpected system list after reopen")
    log.write("PROJECT_REOPENED")
except:
    log.write(traceback.format_exc())
    raise
finally:
    log.close()
""",
        encoding="utf-8",
    )
    result = json.loads(
        run_workbench_journal(
            str(journal),
            str(folder),
            log_file=str(marker),
            completion_marker="PROJECT_REOPENED",
            expected_output=str(project),
            timeout_seconds=1800,
        )
    )
    (folder / "tool_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(folder, result["ok"], result.get("log_tail"), flush=True)
    if not result["ok"]:
        return 1
    rows = []
    for case in cases:
        files = list((folder / "mechanics_files").rglob(case + "_value.csv"))
        if len(files) != 1:
            print(case, "expected one measurement; found", files)
            rows.append([case, None, reference(case), False])
            continue
        actual = float(files[0].read_text().strip())
        solved = files[0].parent
        ok = (
            math.isclose(
                actual, reference(case), rel_tol=0.03 if case == "random" else 0.005
            )
            and any(p.stat().st_size > 0 for p in solved.glob("*.rst"))
            and any(p.stat().st_size > 0 for p in solved.glob("*.db"))
            and (solved / "workbench_main.out").exists()
            and "*** ERROR ***" not in (solved / "workbench_main.out").read_text(errors="replace")
            and any(p.stat().st_size > 1000 for p in solved.glob("*.png"))
        )
        if case in ("harmonic", "transient"):
            history = solved / "response.csv"
            records = list(csv.reader(history.read_text().splitlines())) if history.exists() else []
            expected_count = 5 if case == "harmonic" else 400
            ok = ok and len(records) == expected_count and all(
                len(row) == 2 and all(math.isfinite(float(value)) for value in row)
                for row in records
            )
        rows.append([case, actual, reference(case), ok])
    with (folder / "checks.csv").open("w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["case", "measured", "expected", "passed"])
        writer.writerows(rows)
    print(rows)
    return 0 if all(row[-1] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the two-system Workbench project and verify its retained design point."""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from mcp_server import run_workbench_journal


def main():
    root = ROOT / "runs" / ("thermal_wb_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    root.mkdir()
    print(root, flush=True)
    for name in ("steady.dat", "transient_expansion.dat"):
        shutil.copyfile(HERE / name, root / name)
    journal = root / "run.wbjn"
    journal.write_text((HERE / "parameter_study.wbjn").read_text().replace("__RUN_DIR__", repr(str(root))), encoding="utf-8")
    result = json.loads(run_workbench_journal(
        str(journal), str(root), log_file=str(root / "workbench.log"),
        completion_marker="REOPEN_AND_DP_CHECK_PASSED", expected_output=str(root / "design_points.csv"),
        timeout_seconds=900))
    (root / "execution.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if not result["ok"]:
        raise RuntimeError(f"Inspect {root / 'workbench.log'} and execution.json")
    print(root / "thermal.wbpj")


if __name__ == "__main__":
    main()

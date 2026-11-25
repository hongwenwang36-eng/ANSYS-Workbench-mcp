from __future__ import annotations
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path


def run_spaceclaim_script(
    script_path: str,
    workdir: str = "",
    script_api: str = "V251",
    headless: bool = True,
    expected_output: str = "",
    extra_args: str = "",
    timeout_seconds: int = 600,
) -> str:
    """Run a SpaceClaim Python script and optionally verify its expected artifact."""
    import mcp_server as runtime
    if not runtime.SPACECLAIM.exists():
        return runtime._json({"ok": False, "error": f"SpaceClaim not found: {runtime.SPACECLAIM}"})

    script = runtime._as_path(script_path)
    if not script.exists():
        return runtime._json({"ok": False, "error": f"SpaceClaim script not found: {script}"})
    if script.suffix.lower() != ".py":
        return runtime._json({"ok": False, "error": "SpaceClaim script must use the .py extension"})

    cwd = runtime._as_path(workdir) if workdir else script.parent
    cwd.mkdir(parents=True, exist_ok=True)
    log_file = cwd / f"{script.stem}.spaceclaim.log"
    args = [
        str(runtime.SPACECLAIM),
        f"/Headless={'True' if headless else 'False'}",
        "/Splash=False",
        f"/RunScript={script}",
        f"/ScriptAPI={script_api}",
        f"/ScriptOutput={log_file}",
        "/ExitAfterScript=True",
    ]
    args.extend(runtime._split_extra_args(extra_args))
    artifact_before = runtime._expected_output_status(expected_output)

    try:
        result = runtime._run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "script": str(script)})

    artifact = runtime._expected_output_status(expected_output, before=artifact_before)
    ok = result["returncode"] == 0 and (
        not artifact["required"] or (artifact["updated"] is True and (artifact["size_bytes"] or 0) > 0)
    )
    return runtime._json(
        {
            "ok": ok,
            "script": str(script),
            "workdir": str(cwd),
            "command": args,
            "log_file": str(log_file),
            "log_tail": runtime._read_tail(log_file),
            "expected_output": artifact,
            "process": result,
        }
    )


def run_cfx_pre_session(
    session_file: str,
    workdir: str = "",
    expected_output: str = "",
    extra_args: str = "",
    timeout_seconds: int = 900,
) -> str:
    """Run a CFX-Pre session in batch mode and optionally verify a .cfx or .def output."""
    import mcp_server as runtime
    if not runtime.CFX_PRE.exists():
        return runtime._json({"ok": False, "error": f"CFX-Pre not found: {runtime.CFX_PRE}"})

    session = runtime._as_path(session_file)
    if not session.exists():
        return runtime._json({"ok": False, "error": f"CFX-Pre session not found: {session}"})
    cwd = runtime._as_path(workdir) if workdir else session.parent
    cwd.mkdir(parents=True, exist_ok=True)
    args = [str(runtime.CFX_PRE), "-batch", str(session)]
    args.extend(runtime._split_extra_args(extra_args))
    artifact_before = runtime._expected_output_status(expected_output)

    try:
        result = runtime._run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "session_file": str(session)})

    artifact = runtime._expected_output_status(expected_output, before=artifact_before)
    ok = result["returncode"] == 0 and (
        not artifact["required"] or (artifact["updated"] is True and (artifact["size_bytes"] or 0) > 0)
    )
    return runtime._json(
        {
            "ok": ok,
            "session_file": str(session),
            "workdir": str(cwd),
            "command": args,
            "expected_output": artifact,
            "process": result,
        }
    )


def run_cfx_post_session(
    session_file: str,
    workdir: str = "",
    result_file: str = "",
    state_file: str = "",
    rendering: str = "software",
    expected_output: str = "",
    extra_args: str = "",
    timeout_seconds: int = 900,
) -> str:
    """Run a CFD-Post .cse session in batch mode and verify an optional output.

    rendering must be software or gpu. result_file and state_file are optional
    initial inputs; a session may also load its own result/state files.
    """
    import mcp_server as runtime
    if not runtime.CFX_POST.exists():
        return runtime._json({"ok": False, "error": f"CFD-Post not found: {runtime.CFX_POST}"})

    session = runtime._as_path(session_file)
    if not session.exists():
        return runtime._json({"ok": False, "error": f"CFD-Post session not found: {session}"})

    mode = rendering.strip().lower()
    render_flags = {
        "software": "-batch-software-rendering",
        "gpu": "-batch-gpu-rendering",
    }
    if mode not in render_flags:
        return runtime._json({"ok": False, "error": "rendering must be software or gpu"})

    cwd = runtime._as_path(workdir) if workdir else session.parent
    cwd.mkdir(parents=True, exist_ok=True)
    args = [str(runtime.CFX_POST)]
    loaded_result = ""
    loaded_state = ""
    if result_file:
        result_path = runtime._as_path(result_file)
        if not result_path.exists():
            return runtime._json({"ok": False, "error": f"CFX result file not found: {result_path}"})
        loaded_result = str(result_path)
        args.extend(["-results", loaded_result])
    if state_file:
        state_path = runtime._as_path(state_file)
        if not state_path.exists():
            return runtime._json({"ok": False, "error": f"CFD-Post state file not found: {state_path}"})
        loaded_state = str(state_path)
        args.extend(["-state", loaded_state])
    args.extend([render_flags[mode], str(session)])
    args.extend(runtime._split_extra_args(extra_args))
    artifact_before = runtime._expected_output_status(expected_output)

    try:
        result = runtime._run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "session_file": str(session)})

    artifact = runtime._expected_output_status(expected_output, before=artifact_before)
    ok = result["returncode"] == 0 and (
        not artifact["required"] or (artifact["updated"] is True and (artifact["size_bytes"] or 0) > 0)
    )
    return runtime._json(
        {
            "ok": ok,
            "session_file": str(session),
            "workdir": str(cwd),
            "rendering": mode,
            "result_file": loaded_result,
            "state_file": loaded_state,
            "command": args,
            "expected_output": artifact,
            "process": result,
        }
    )


def run_workbench_journal(
    journal_path: str,
    workdir: str = "",
    batch: bool = True,
    log_file: str = "",
    completion_marker: str = "",
    expected_output: str = "",
    timeout_seconds: int = 600,
) -> str:
    """Run a Workbench journal and optionally verify its log marker and output.

    A non-empty completion_marker requires log_file. expected_output can point
    to a converged project, result, or iteration report that must exist.
    """
    import mcp_server as runtime
    if not runtime.RUNWB2.exists():
        return runtime._json({"ok": False, "error": f"RunWB2 not found: {runtime.RUNWB2}"})

    journal = runtime._as_path(journal_path)
    if not journal.exists():
        return runtime._json({"ok": False, "error": f"Journal not found: {journal}"})

    cwd = runtime._as_path(workdir) if workdir else journal.parent
    cwd.mkdir(parents=True, exist_ok=True)
    if completion_marker and not log_file:
        return runtime._json({"ok": False, "error": "completion_marker requires log_file"})
    log_path = runtime._as_path(log_file) if log_file else None
    log_before = runtime._path_state(log_path) if log_path else None
    artifact_before = runtime._expected_output_status(expected_output)

    try:
        result = runtime._run_process(runtime._workbench_command(journal, batch=batch), cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(journal)})

    log_text = runtime._read_tail(log_path) if log_path else ""
    log_after = runtime._path_state(log_path) if log_path else None
    log_updated = runtime._state_changed(log_before, log_after) if log_before and log_after else None
    marker_seen = completion_marker in log_text if completion_marker else None
    artifact = runtime._expected_output_status(expected_output, before=artifact_before)
    ok = (
        result["returncode"] == 0
        and (marker_seen is not False)
        and (log_updated is not False if completion_marker else True)
        and (
            not artifact["required"]
            or (artifact["updated"] is True and (artifact["size_bytes"] or 0) > 0)
        )
    )
    return runtime._json(
        {
            "ok": ok,
            "journal": str(journal),
            "workdir": str(cwd),
            "log_file": str(log_path) if log_path else "",
            "completion_marker": completion_marker,
            "marker_seen": marker_seen,
            "log_updated": log_updated,
            "log_tail": log_text,
            "expected_output": artifact,
            **result,
        }
    )


def generate_ansys_mesh(
    geometry_file: str,
    project_dir: str = "",
    element_size_mm: float | None = None,
    controls_script: str = "",
    timeout_seconds: int = 900,
) -> str:
    """Generate a mesh from geometry in a standalone Workbench Ansys Meshing system.

    Optionally set a global element size in mm and run a Meshing Python script
    to add custom controls before generation. Return mesh statistics, a
    reopened .wbpj and the exported .meshdat. No physics setup or solve.
    """
    import mcp_server as runtime
    geometry = runtime._as_path(geometry_file)
    if not geometry.is_file():
        return runtime._json({"ok": False, "error": f"Geometry file not found: {geometry}"})
    if element_size_mm is not None and (not math.isfinite(element_size_mm) or element_size_mm <= 0):
        return runtime._json({"ok": False, "error": "element_size_mm must be finite and positive"})
    if timeout_seconds <= 0:
        return runtime._json({"ok": False, "error": "timeout_seconds must be positive"})
    script = runtime._as_path(controls_script) if controls_script else None
    if script is not None and (script.suffix.lower() != ".py" or not script.is_file()):
        return runtime._json({"ok": False, "error": f"Expected a Meshing Python script: {script}"})

    parent = runtime._as_path(project_dir) if project_dir else runtime.RUNS_DIR
    parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="ansys-meshing-", dir=parent))
    project = directory / "meshing.wbpj"
    project_files = directory / "meshing_files"
    mesh_file = directory / "meshing.meshdat"
    stats_file = directory / "mesh-stats.json"
    journal = directory / "generate_mesh.wbjn"
    log = directory / "meshing.log"
    config = {
        "directory": str(directory), "geometry": str(geometry),
        "project": str(project), "mesh_file": str(mesh_file), "log": str(log),
        "element_size_mm": element_size_mm,
        "controls_script": str(script) if script else "",
    }
    template = (runtime.SERVER_ROOT / "ansys_meshing.wbjn").read_text(encoding="utf-8")
    journal.write_text("import json\nconfig = json.loads(%r)\n" % json.dumps(config) + template, encoding="utf-8")

    execution = json.loads(runtime.run_workbench_journal(
        str(journal), str(directory), log_file=str(log),
        completion_marker="ANSYS_MESH_REOPENED", expected_output=str(project),
        timeout_seconds=timeout_seconds,
    ))
    artifacts_ready = project_files.is_dir() and mesh_file.is_file() and mesh_file.stat().st_size > 0
    reopened = execution["ok"] and artifacts_ready
    return runtime._json({
        "ok": reopened, "reopened": reopened, "geometry_file": str(geometry),
        "project_file": str(project), "project_files": str(project_files), "mesh_file": str(mesh_file),
        "statistics_file": str(stats_file), "statistics": runtime._read_json(stats_file),
        "journal": str(journal), "log_file": str(log), "execution": execution,
    })


def create_workbench_analysis_system(
    analysis_type: str,
    project_dir: str,
    project_name: str = "",
    geometry_file: str = "",
    refresh_model: bool = False,
    template_name: str = "",
    solver: str = "",
    timeout_seconds: int = 600,
) -> str:
    """Create a Workbench analysis system through a direct batch journal.

    This one-shot tool does not require the bridge to be running.
    """
    import mcp_server as runtime
    if not runtime.RUNWB2.exists():
        return runtime._json({"ok": False, "error": f"RunWB2 not found: {runtime.RUNWB2}"})

    try:
        candidates = runtime._analysis_candidates(analysis_type, template_name, solver)
    except ValueError as exc:
        return runtime._json({"ok": False, "error": str(exc)})

    if geometry_file:
        geom = runtime._as_path(geometry_file)
        if not geom.exists():
            return runtime._json({"ok": False, "error": f"Geometry file not found: {geom}"})
        geometry_file = str(geom)

    analysis_key = runtime._analysis_key(analysis_type)
    final_project_name = project_name or runtime._default_project_name(analysis_key)
    out_dir = runtime._as_path(project_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    project_file = out_dir / f"{final_project_name}.wbpj"
    journal_file = out_dir / f"{final_project_name}_create_{analysis_key}.wbjn"
    log_file = out_dir / f"{final_project_name}_create_{analysis_key}.log"
    marker = "ANSYS_WORKBENCH_MCP_DONE"

    geometry_literal = repr(geometry_file)
    refresh_line = "        model.Refresh()\n" if refresh_model else ""
    journal = f"""# encoding: utf-8
import traceback

log = open({str(log_file)!r}, "w")

def w(message):
    log.write(str(message) + "\\n")
    log.flush()

def resolve_template(candidates):
    errors = []
    for candidate in candidates:
        name = candidate.get("template_name", "")
        solver = candidate.get("solver", "")
        try:
            if solver:
                return GetTemplate(TemplateName=name, Solver=solver), name, solver
            return GetTemplate(TemplateName=name), name, solver
        except Exception as e:
            errors.append(name + "|" + solver + "|" + str(e))
    raise RuntimeError("No matching Workbench template. Tried: " + "; ".join(errors))

try:
    Reset()
    ClearMessages()
    template, used_name, used_solver = resolve_template({json.dumps(candidates, ensure_ascii=False)})
    system = template.CreateSystem()
    if {bool(geometry_file)!r}:
        geometry = system.GetContainer(ComponentName="Geometry")
        geometry.SetFile(FilePath={geometry_literal})
    try:
        model = system.GetContainer(ComponentName="Model")
{refresh_line if refresh_model else "        model = None\n"}    except Exception:
        model = None
    Save(FilePath={str(project_file)!r}, Overwrite=True)
    w("Analysis type: " + {analysis_key!r})
    w("Template: " + used_name + " (" + used_solver + ")")
    w("Project saved: " + {str(project_file)!r})
    for message in GetMessages():
        try:
            w("%s: %s" % (message.MessageType, message.Summary))
        except:
            w(str(message))
    w("{marker}")
except Exception:
    w("ERROR")
    w(traceback.format_exc())
    raise
finally:
    log.close()
"""
    journal_file.write_text(journal, encoding="utf-8")

    try:
        process_result = runtime._run_process(runtime._workbench_command(journal_file, batch=True), out_dir, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(journal_file)})

    marker_seen = runtime._wait_for_log_marker(log_file, marker, min(timeout_seconds, 120))
    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    ok = project_file.exists() and marker_seen and "ERROR" not in log_text
    return runtime._json(
        {
            "ok": ok,
            "analysis_type": analysis_key,
            "project_file": str(project_file),
            "journal_file": str(journal_file),
            "log_file": str(log_file),
            "marker_seen": marker_seen,
            "process": process_result,
            "log_tail": log_text[-8000:],
        }
    )


def create_steady_state_thermal_system(
    project_dir: str,
    project_name: str = "steady_state_thermal",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 600,
) -> str:
    """Create a Workbench Steady-State Thermal system using a direct batch journal.

    This one-shot tool does not require the bridge to be running.
    """
    import mcp_server as runtime
    if not runtime.RUNWB2.exists():
        return runtime._json({"ok": False, "error": f"RunWB2 not found: {runtime.RUNWB2}"})

    out_dir = runtime._as_path(project_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    project_file = out_dir / f"{project_name}.wbpj"
    journal_file = out_dir / f"{project_name}_create_steady_thermal.wbjn"
    log_file = out_dir / f"{project_name}_create_steady_thermal.log"

    geom_line = ""
    if geometry_file:
        geom = runtime._as_path(geometry_file)
        if not geom.exists():
            return runtime._json({"ok": False, "error": f"Geometry file not found: {geom}"})
        geom_line = (
            "geometry = system.GetContainer(ComponentName='Geometry')\n"
            f"geometry.SetFile(FilePath={str(geom)!r})\n"
        )

    refresh_line = "model.Refresh()\n" if refresh_model else ""
    marker = "ANSYS_WORKBENCH_MCP_DONE"
    journal = f"""# encoding: utf-8
import traceback

log = open({str(log_file)!r}, "w")

def w(message):
    log.write(str(message) + "\\n")
    log.flush()

try:
    Reset()
    ClearMessages()
    template = GetTemplate(TemplateName="Steady-State Thermal", Solver="ANSYS")
    system = template.CreateSystem()
{geom_line}    model = system.GetContainer(ComponentName="Model")
{refresh_line}    Save(FilePath={str(project_file)!r}, Overwrite=True)
    w("Project saved: " + {str(project_file)!r})
    for message in GetMessages():
        try:
            w("%s: %s" % (message.MessageType, message.Summary))
        except:
            w(str(message))
    w("{marker}")
except Exception:
    w("ERROR")
    w(traceback.format_exc())
    raise
finally:
    log.close()
"""
    journal_file.write_text(journal, encoding="utf-8")

    try:
        process_result = runtime._run_process(runtime._workbench_command(journal_file, batch=True), out_dir, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(journal_file)})

    marker_seen = runtime._wait_for_log_marker(log_file, marker, min(timeout_seconds, 120))
    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    ok = project_file.exists() and marker_seen and "ERROR" not in log_text
    return runtime._json(
        {
            "ok": ok,
            "project_file": str(project_file),
            "journal_file": str(journal_file),
            "log_file": str(log_file),
            "marker_seen": marker_seen,
            "process": process_result,
            "log_tail": log_text[-8000:],
        }
    )


def run_mapdl_input(
    input_file: str,
    workdir: str = "",
    job_name: str = "ansys_mcp_job",
    timeout_seconds: int = 600,
) -> str:
    """Run a Mechanical APDL input file with MAPDL."""
    import mcp_server as runtime
    if not runtime.MAPDL.exists():
        return runtime._json({"ok": False, "error": f"MAPDL not found: {runtime.MAPDL}"})

    inp = runtime._as_path(input_file)
    if not inp.exists():
        return runtime._json({"ok": False, "error": f"Input file not found: {inp}"})

    cwd = runtime._as_path(workdir) if workdir else inp.parent
    cwd.mkdir(parents=True, exist_ok=True)
    out_file = cwd / f"{job_name}.out"
    args = [str(runtime.MAPDL), "-b", "-i", str(inp), "-o", str(out_file), "-j", job_name]

    try:
        result = runtime._run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "input_file": str(inp)})

    out_tail = runtime._read_tail(out_file)
    return runtime._json(
        {
            "ok": result["returncode"] == 0,
            "input_file": str(inp),
            "out_file": str(out_file),
            "process": result,
            "out_tail": out_tail,
        }
    )


def run_fluent_journal(
    journal_path: str,
    workdir: str = "",
    dimension: str = "3d",
    precision: str = "double",
    processors: int = 1,
    gui: bool = False,
    extra_args: str = "",
    timeout_seconds: int = 3600,
) -> str:
    """Run an Ansys Fluent journal directly with fluent.exe.

    dimension is 2d or 3d. precision is single or double.
    extra_args is appended to the Fluent command line for advanced cases.
    """
    import mcp_server as runtime
    if not runtime.FLUENT.exists():
        return runtime._json({"ok": False, "error": f"Fluent not found: {runtime.FLUENT}"})

    journal = runtime._as_path(journal_path)
    if not journal.exists():
        return runtime._json({"ok": False, "error": f"Journal not found: {journal}"})

    cwd = runtime._as_path(workdir) if workdir else journal.parent
    cwd.mkdir(parents=True, exist_ok=True)

    dim = dimension.strip().lower()
    if dim not in {"2d", "3d"}:
        return runtime._json({"ok": False, "error": "dimension must be 2d or 3d"})
    prec = precision.strip().lower()
    if prec in {"double", "dp"}:
        fluent_mode = dim + "dp"
    elif prec in {"single", "sp"}:
        fluent_mode = dim
    else:
        return runtime._json({"ok": False, "error": "precision must be single or double"})

    args = [str(runtime.FLUENT), fluent_mode]
    if int(processors) > 1:
        args.append(f"-t{int(processors)}")
    if not gui:
        args.append("-g")
    args.extend(["-i", str(journal)])
    args.extend(runtime._split_extra_args(extra_args))

    try:
        result = runtime._run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(journal)})

    return runtime._json(
        {
            "ok": result["returncode"] == 0,
            "journal": str(journal),
            "workdir": str(cwd),
            "command": args,
            "process": result,
        }
    )


def run_cfx_solver(
    definition_file: str,
    workdir: str = "",
    run_name: str = "",
    processors: int = 1,
    double_precision: bool = False,
    extra_args: str = "",
    timeout_seconds: int = 3600,
) -> str:
    """Run an Ansys CFX solver input file directly with cfx5solve.exe."""
    import mcp_server as runtime
    if not runtime.CFX_SOLVE.exists():
        return runtime._json({"ok": False, "error": f"CFX solver not found: {runtime.CFX_SOLVE}"})

    definition = runtime._as_path(definition_file)
    if not definition.exists():
        return runtime._json({"ok": False, "error": f"Definition file not found: {definition}"})

    cwd = runtime._as_path(workdir) if workdir else definition.parent
    cwd.mkdir(parents=True, exist_ok=True)

    args = [str(runtime.CFX_SOLVE), "-batch", "-def", str(definition), "-chdir", str(cwd)]
    if run_name:
        args.extend(["-name", run_name])
    if double_precision:
        args.append("-double")
    if int(processors) > 1:
        args.extend(["-par-local", "-partition", str(int(processors))])
    args.extend(runtime._split_extra_args(extra_args))

    try:
        result = runtime._run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "definition_file": str(definition)})

    return runtime._json(
        {
            "ok": result["returncode"] == 0,
            "definition_file": str(definition),
            "workdir": str(cwd),
            "command": args,
            "process": result,
        }
    )


def create_and_run_thermal_bar_demo(
    project_dir: str = r"D:\ansys-workbench-mcp\runs\thermal_bar_demo",
    timeout_seconds: int = 600,
) -> str:
    """Create and solve a small steady thermal bar demo through direct Workbench batch."""
    import mcp_server as runtime
    out_dir = runtime._as_path(project_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    inp = out_dir / "thermal_bar.dat"
    result_txt = out_dir / "thermal_nodal_temperatures.txt"
    wbjn = out_dir / "run_thermal_bar.wbjn"
    wbpj = out_dir / "thermal_bar_demo.wbpj"
    log_file = out_dir / "workbench_run.log"
    marker = "ANSYS_WORKBENCH_MCP_DONE"

    apdl = f"""/TITLE,Workbench MCP thermal bar demo
/PREP7
ET,1,SOLID70
MP,KXX,1,45
BLOCK,0,0.1,0,0.02,0,0.02
ESIZE,0.005
VMESH,ALL
FINISH

/SOLU
ANTYPE,STATIC
NSEL,S,LOC,X,0
D,ALL,TEMP,100
NSEL,S,LOC,X,0.1
D,ALL,TEMP,20
ALLSEL,ALL
SOLVE
FINISH

/POST1
SET,LAST
ALLSEL,ALL
/OUTPUT,{str(result_txt.with_suffix('')).replace(chr(92), '/')!r},txt
PRNSOL,TEMP
/OUTPUT
FINISH
"""
    inp.write_text(apdl, encoding="utf-8")

    journal = f"""# encoding: utf-8
import traceback

log = open({str(log_file)!r}, "w")

def w(message):
    log.write(str(message) + "\\n")
    log.flush()

try:
    Reset()
    ClearMessages()
    template = GetTemplate(TemplateName="Mechanical APDL")
    system = template.CreateSystem()
    setup = system.GetContainer(ComponentName="Setup")
    setup.AddInputFile(FilePath={str(inp)!r})
    Save(FilePath={str(wbpj)!r}, Overwrite=True)
    Update()
    Save(FilePath={str(wbpj)!r}, Overwrite=True)
    w("Project saved: " + {str(wbpj)!r})
    w("{marker}")
except Exception:
    w("ERROR")
    w(traceback.format_exc())
    raise
finally:
    log.close()
"""
    wbjn.write_text(journal, encoding="utf-8")

    try:
        process_result = runtime._run_process(runtime._workbench_command(wbjn, batch=True), out_dir, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(wbjn)})

    marker_seen = runtime._wait_for_log_marker(log_file, marker, min(timeout_seconds, 180))
    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    temp_text = result_txt.read_text(encoding="utf-8", errors="replace") if result_txt.exists() else ""
    temps: list[float] = []
    for line in temp_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit():
            try:
                temps.append(float(parts[1]))
            except ValueError:
                pass
    ok = result_txt.exists() and marker_seen and "ERROR" not in log_text
    return runtime._json(
        {
            "ok": ok,
            "project_file": str(wbpj),
            "input_file": str(inp),
            "journal_file": str(wbjn),
            "log_file": str(log_file),
            "result_file": str(result_txt),
            "node_count": len(temps),
            "min_temperature": min(temps) if temps else None,
            "max_temperature": max(temps) if temps else None,
            "process": process_result,
            "log_tail": log_text[-8000:],
        }
    )


def run_system_coupling_script(script_path: str, workdir: str = "", timeout_seconds: int = 3600) -> str:
    """Run a standalone System Coupling Python script in batch mode."""
    import mcp_server as runtime
    executable = Path(os.environ.get("ANSYS_SYSTEM_COUPLING",
        str(runtime.RUNWB2.parents[3] / "SystemCoupling" / "bin" / "systemcoupling.bat")))
    script = runtime._as_path(script_path)
    if not executable.is_file() or not script.is_file():
        return runtime._json({"ok": False, "error": "Executable or script does not exist",
                      "executable": str(executable), "script": str(script)})
    cwd = runtime._as_path(workdir) if workdir else script.parent
    cwd.mkdir(parents=True, exist_ok=True)
    # Windows executes the vendor batch launcher through cmd.exe.
    values = [str(executable), "-R", str(script)]
    if any(any(c in value for c in ['"', "%", "\n", "\r"]) for value in values):
        return runtime._json({"ok": False, "error": "Unsupported batch argument character"})
    command = '"' + " ".join('"' + value + '"' for value in values) + '"'
    args = '"' + os.environ.get("COMSPEC", "cmd.exe") + '" /d /v:off /s /c ' + command
    try:
        result = runtime._run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return runtime._json({"ok": False, "error": "System Coupling timed out", "workdir": str(cwd)})
    return runtime._json({"ok": result["returncode"] == 0, "process": result, "workdir": str(cwd)})


TOOLS = (
    run_spaceclaim_script,
    run_cfx_pre_session,
    run_cfx_post_session,
    run_workbench_journal,
    generate_ansys_mesh,
    create_workbench_analysis_system,
    create_steady_state_thermal_system,
    run_mapdl_input,
    run_fluent_journal,
    run_cfx_solver,
    create_and_run_thermal_bar_demo,
    run_system_coupling_script,
)

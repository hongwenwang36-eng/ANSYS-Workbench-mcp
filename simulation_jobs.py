"""Persistent Windows batch jobs using the same tool implementations as stdio MCP."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

BATCH_TOOLS = {
    "generate_ansys_mesh", "run_workbench_journal", "run_spaceclaim_script", "run_cfx_pre_session",
    "run_system_coupling_script", "run_icem_replay", "run_cfx_post_session", "run_mapdl_input", "run_fluent_journal", "run_cfx_solver",
}


def write_record(path, value):
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def job_path(root, job_id):
    return root / uuid.UUID(job_id).hex


def object_name(path):
    digest = hashlib.sha256(str(path.resolve()).casefold().encode()).hexdigest()
    return "Local\\AnsysMCP_" + digest


def open_job(path, access):
    import pywintypes
    import win32job
    try:
        return win32job.OpenJobObject(access, False, object_name(path))
    except pywintypes.error as exc:
        if exc.winerror == 2:
            return None
        raise


def status(path):
    import win32job
    if not path.is_dir():
        raise ValueError("Unknown job_id")
    result_file = path / "result.json"
    record = {"job_id": path.name, "directory": str(path), "console_log": str(path / "console.log")}
    if result_file.is_file():
        result = json.loads(result_file.read_text(encoding="utf-8"))
        return {**record, "state": "finished" if result.get("ok") else "failed", "result": result}
    handle = open_job(path, win32job.JOB_OBJECT_QUERY)
    stopping = (path / "stop").exists()
    if handle:
        return {**record, "state": "stopping" if stopping else "running"}
    if stopping:
        return {**record, "state": "stopped"}
    if (path / "started").exists() or time.time() - path.stat().st_ctime > 120:
        if result_file.exists():
            return status(path)
        return {**record, "state": "interrupted"}
    return {**record, "state": "starting"}


def submit(root, tool, arguments, request_id):
    import mcp_server
    if tool not in BATCH_TOOLS:
        raise ValueError("Supported tools: " + ", ".join(sorted(BATCH_TOOLS)))
    bound = inspect.signature(getattr(mcp_server, tool)).bind(**arguments)
    bound.apply_defaults()
    arguments = bound.arguments
    paths = {"geometry_file", "project_dir", "controls_script", "input_file", "journal_path", "script_path", "session_file",
             "definition_file", "replay_file", "workdir", "expected_output",
             "log_file", "result_file", "state_file", "project_file"}
    arguments = {name: str(Path(value).expanduser().resolve()) if name in paths and value
                 else value for name, value in arguments.items()}
    interactive_gui = arguments.get("gui") and "-gu" not in mcp_server._split_extra_args(
        arguments.get("extra_args", ""))
    if arguments.get("batch") is False or arguments.get("headless") is False or interactive_gui:
        raise ValueError("Background jobs require a batch/headless tool")
    path = job_path(root, request_id or str(uuid.uuid4()))
    request = {"tool": tool, "arguments": arguments}
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        stored = path / "request.json"
        if not stored.is_file():
            raise ValueError("Request is being initialized. Query the same job_id.")
        if json.loads(stored.read_text(encoding="utf-8")) != request:
            raise ValueError("request_id already belongs to different inputs")
        return status(path)
    try:
        write_record(path / "request.json", request)
        with (path / "worker.log").open("wb") as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), str(path)],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=process.wait, daemon=True).start()
    except Exception as exc:
        write_record(path / "result.json", {"ok": False, "error": str(exc)})
    return status(path)


def stop(path):
    import win32job
    current = status(path)
    if current["state"] in {"starting", "running", "stopping"}:
        (path / "stop").touch()
        handle = open_job(path, win32job.JOB_OBJECT_TERMINATE)
        if handle:
            win32job.TerminateJobObject(handle, 1)
    return status(path)


def work(path):
    import win32api
    import win32job
    # A unique kernel object ties cancellation to this tree, even after an MCP restart.
    handle = win32job.CreateJobObject(None, object_name(path))
    limits = win32job.QueryInformationJobObject(handle, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(handle, win32job.JobObjectExtendedLimitInformation, limits)
    win32job.AssignProcessToJobObject(handle, win32api.GetCurrentProcess())
    (path / "started").touch()
    if (path / "stop").exists():
        return
    os.environ["ANSYS_MCP_JOB_DIRECTORY"] = str(path)
    os.environ["ANSYS_MCP_JOB_CONSOLE"] = str(path / "console.log")
    import mcp_server
    request = json.loads((path / "request.json").read_text(encoding="utf-8"))
    if request["tool"] not in BATCH_TOOLS:
        raise ValueError("Unsupported batch tool")
    try:
        result = json.loads(getattr(mcp_server, request["tool"])(**request["arguments"]))
    except Exception as exc:
        result = {"ok": False, "error": repr(exc)}
    write_record(path / "result.json", result)


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    try:
        work(directory)
    except Exception as exc:
        write_record(directory / "result.json", {"ok": False, "error": repr(exc)})

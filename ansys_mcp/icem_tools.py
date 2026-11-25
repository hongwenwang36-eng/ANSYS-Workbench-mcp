from __future__ import annotations
import subprocess
import time
import uuid
from typing import Any


def check_icem_installation() -> str:
    """Check the configured ICEM CFD launcher and persistent bridge script."""
    import mcp_server as runtime
    return runtime._json(
        {
            "version": runtime.__version__,
            "icem_cfd": str(runtime.ICEM_CFD),
            "icem_cfd_exists": runtime.ICEM_CFD.exists(),
            "bridge_script": str(runtime.ICEM_BRIDGE_SCRIPT),
            "bridge_script_exists": runtime.ICEM_BRIDGE_SCRIPT.exists(),
            "icem_mcp_home": str(runtime.ICEM_HOME),
        }
    )


def start_icem_bridge(
    project_file: str = "",
    workdir: str = "",
    batch: bool = False,
    wait_seconds: int = 30,
    extra_args: str = "",
) -> str:
    """Launch ICEM CFD with a persistent MCP Tcl bridge.

    By default ICEM starts with its GUI. Set batch=True for a headless,
    persistent ICEM session. project_file is passed to ICEM at startup.
    """
    import mcp_server as runtime
    if not runtime.ICEM_CFD.exists():
        return runtime._json({"ok": False, "error": f"ICEM CFD launcher not found: {runtime.ICEM_CFD}"})
    if not runtime.ICEM_BRIDGE_SCRIPT.exists():
        return runtime._json({"ok": False, "error": f"ICEM CFD bridge script not found: {runtime.ICEM_BRIDGE_SCRIPT}"})

    status = runtime._read_icem_status()
    if status.get("status") == "running":
        ping_result = runtime._send_icem_command("ping", timeout=5.0)
        if ping_result.get("success"):
            return runtime._json(
                {
                    "ok": True,
                    "already_running": True,
                    "status": status,
                    "ping": ping_result,
                }
            )

    startup_project = ""
    if project_file:
        project = runtime._as_path(project_file)
        if not project.exists():
            return runtime._json({"ok": False, "error": f"ICEM project/input file not found: {project}"})
        startup_project = str(project)

    cwd = runtime._as_path(workdir) if workdir else runtime.RUNS_DIR / "icem_bridge"
    cwd.mkdir(parents=True, exist_ok=True)
    runtime._ensure_dirs()
    runtime._clear_stale_icem_commands()
    try:
        if runtime.ICEM_STATUS_FILE.exists():
            runtime.ICEM_STATUS_FILE.unlink()
    except OSError:
        pass

    arguments: list[str] = []
    if batch:
        arguments.append("-batch")
    arguments.extend(["-script", str(runtime.ICEM_BRIDGE_SCRIPT)])
    arguments.extend(runtime._split_extra_args(extra_args))
    if startup_project:
        arguments.append(startup_project)

    env = runtime._icem_environment(batch)
    try:
        command = runtime._icem_command(arguments)
    except ValueError as exc:
        return runtime._json({"ok": False, "error": str(exc)})
    log_handle = runtime.ICEM_LOG_FILE.open("a", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        log_handle.close()

    deadline = time.time() + max(1, int(wait_seconds))
    ping_result: dict[str, Any] = {}
    while time.time() < deadline:
        status = runtime._read_icem_status()
        if status.get("status") == "running":
            ping_result = runtime._send_icem_command("ping", timeout=5.0)
            if ping_result.get("success"):
                return runtime._json(
                    {
                        "ok": True,
                        "pid": proc.pid,
                        "batch": batch,
                        "workdir": str(cwd),
                        "command": command,
                        "status": status,
                        "ping": ping_result,
                    }
                )
        if proc.poll() is not None:
            break
        time.sleep(0.5)

    return runtime._json(
        {
            "ok": False,
            "pid": proc.pid,
            "returncode": proc.poll(),
            "batch": batch,
            "status": runtime._read_icem_status(),
            "detail": "ICEM CFD bridge did not answer before timeout",
            "log_file": str(runtime.ICEM_LOG_FILE),
            "log_tail": runtime._read_tail(runtime.ICEM_LOG_FILE),
        }
    )


def stop_icem_bridge(timeout_seconds: int = 15) -> str:
    """Stop the persistent ICEM CFD bridge and close its ICEM process."""
    import mcp_server as runtime
    result = runtime._send_icem_command("stop", timeout=min(float(timeout_seconds), 5.0))
    if not result.get("success"):
        return runtime._json({"ok": False, "command_result": result, "status": runtime._read_icem_status()})

    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        status = runtime._read_icem_status()
        if status.get("status") == "stopped":
            return runtime._json({"ok": True, "status": status, "command_result": result})
        time.sleep(0.25)
    return runtime._json({"ok": False, "status": runtime._read_icem_status(), "command_result": result})


def check_icem_connection() -> str:
    """Check whether the persistent ICEM CFD Tcl bridge is responding."""
    import mcp_server as runtime
    status = runtime._read_icem_status()
    if not status:
        return runtime._json(
            {
                "ok": False,
                "error": "ICEM CFD bridge status not found. Run start_icem_bridge().",
            }
        )
    if status.get("status") != "running":
        return runtime._json({"ok": False, "error": "ICEM CFD bridge is not running", "status": status})
    result = runtime._send_icem_command("ping", timeout=10.0)
    return runtime._json({"ok": bool(result.get("success")), "status": status, "ping": result})


def execute_icem_script(script: str, timeout_seconds: int = 120) -> str:
    """Execute Tcl/Replay commands inside the live ICEM CFD bridge session.

    The returned result is the value produced by the final Tcl command. This
    provides direct access to ICEM commands such as ic_load_tetin and blocking,
    meshing, quality, and output-interface commands recorded by Replay Control.
    """
    import mcp_server as runtime
    if not script.strip():
        return runtime._json({"ok": False, "error": "script must not be empty"})
    result = runtime._send_icem_command("execute", timeout=float(timeout_seconds), script=script)
    return runtime._format_icem_result(result)


def get_icem_session_info(timeout_seconds: int = 30) -> str:
    """Get basic information from the live ICEM CFD Tcl interpreter."""
    import mcp_server as runtime
    script = r"""
set __icem_mcp_info ""
append __icem_mcp_info "pid=[pid]\n"
append __icem_mcp_info "cwd=[pwd]\n"
append __icem_mcp_info "tcl_patchlevel=[info patchlevel]\n"
append __icem_mcp_info "ic_commands=[llength [info commands ic_*]]\n"
append __icem_mcp_info "blocking_commands=[llength [info commands ic_hex_*]]\n"
set __icem_mcp_info
"""
    result = runtime._send_icem_command("execute", timeout=float(timeout_seconds), script=script)
    return runtime._format_icem_result(result)


def list_icem_commands(pattern: str = "ic_*", limit: int = 300, timeout_seconds: int = 30) -> str:
    """List commands available in the live ICEM Tcl interpreter.

    pattern is a Tcl info-commands glob, for example ic_hex_* or ic_geo_*.
    """
    import mcp_server as runtime
    safe_limit = max(1, min(int(limit), 2000))
    script = "\n".join(
        [
            f"set __icem_mcp_commands [lsort [info commands {runtime._tcl_quote(pattern)}]]",
            f"set __icem_mcp_commands [lrange $__icem_mcp_commands 0 {safe_limit - 1}]",
            'join $__icem_mcp_commands "\\n"',
            "",
        ]
    )
    result = runtime._send_icem_command("execute", timeout=float(timeout_seconds), script=script)
    return runtime._format_icem_result(result)


def run_icem_replay(
    replay_file: str,
    workdir: str = "",
    project_file: str = "",
    extra_args: str = "",
    timeout_seconds: int = 3600,
) -> str:
    """Run an ICEM CFD Tcl/Replay script as a one-shot batch job.

    A generated wrapper sources the replay and exits ICEM when it finishes, so
    the original replay file does not need an explicit exit command.
    """
    import mcp_server as runtime
    if not runtime.ICEM_CFD.exists():
        return runtime._json({"ok": False, "error": f"ICEM CFD launcher not found: {runtime.ICEM_CFD}"})

    replay = runtime._as_path(replay_file)
    if not replay.exists():
        return runtime._json({"ok": False, "error": f"ICEM replay file not found: {replay}"})

    startup_project = ""
    if project_file:
        project = runtime._as_path(project_file)
        if not project.exists():
            return runtime._json({"ok": False, "error": f"ICEM project/input file not found: {project}"})
        startup_project = str(project)

    cwd = runtime._as_path(workdir) if workdir else replay.parent
    cwd.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:8]
    wrapper = cwd / f"icem_mcp_wrapper_{run_id}.tcl"
    result_file = cwd / f"icem_mcp_result_{run_id}.txt"
    wrapper_script = f"""set __icem_mcp_code [catch {{source {runtime._tcl_quote(replay)}}} __icem_mcp_result]
set __icem_mcp_channel [open {runtime._tcl_quote(result_file)} w]
fconfigure $__icem_mcp_channel -encoding utf-8 -translation lf
puts $__icem_mcp_channel "code=$__icem_mcp_code"
puts $__icem_mcp_channel "result=$__icem_mcp_result"
if {{$__icem_mcp_code != 0 && [info exists errorInfo]}} {{
    puts $__icem_mcp_channel "errorInfo=$errorInfo"
}}
close $__icem_mcp_channel
if {{$__icem_mcp_code == 0 || $__icem_mcp_code == 2}} {{
    exit 0
}}
exit 1
"""
    wrapper.write_text(wrapper_script, encoding="utf-8")

    arguments = ["-batch", "-script", str(wrapper)]
    arguments.extend(runtime._split_extra_args(extra_args))
    if startup_project:
        arguments.append(startup_project)
    try:
        command = runtime._icem_command(arguments)
    except ValueError as exc:
        return runtime._json({"ok": False, "error": str(exc)})

    try:
        process_result = runtime._run_process(command, cwd, timeout_seconds, env=runtime._icem_environment(batch=True))
    except subprocess.TimeoutExpired:
        return runtime._json(
            {
                "ok": False,
                "error": f"Timed out after {timeout_seconds}s",
                "replay_file": str(replay),
                "wrapper_file": str(wrapper),
            }
        )

    result_text = runtime._read_tail(result_file)
    successful_code = result_text.startswith("code=0") or result_text.startswith("code=2")
    ok = process_result["returncode"] == 0 and result_file.exists() and successful_code
    return runtime._json(
        {
            "ok": ok,
            "replay_file": str(replay),
            "project_file": startup_project,
            "workdir": str(cwd),
            "wrapper_file": str(wrapper),
            "result_file": str(result_file),
            "command": command,
            "process": process_result,
            "result_tail": result_text,
        }
    )


TOOLS = (
    check_icem_installation,
    start_icem_bridge,
    stop_icem_bridge,
    check_icem_connection,
    execute_icem_script,
    get_icem_session_info,
    list_icem_commands,
    run_icem_replay,
)

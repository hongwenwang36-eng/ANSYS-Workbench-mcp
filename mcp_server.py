#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP bridge for Ansys Workbench automation.

The server supports two modes:

1. File-IPC bridge mode, similar to Abaqus MCP:
   mcp_server.py writes command JSON files and ansys_workbench_bridge.wbjn
   runs inside Workbench to execute them.
2. Direct batch mode:
   mcp_server.py invokes RunWB2/MAPDL directly for one-shot jobs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


__version__ = "0.5.0"

SERVER_ROOT = Path(__file__).resolve().parent
DEFAULT_MCP_HOME = SERVER_ROOT
MCP_HOME = Path(os.environ.get("ANSYS_WORKBENCH_MCP_HOME", DEFAULT_MCP_HOME)).expanduser().resolve()

COMMANDS_DIR = MCP_HOME / "commands"
RESULTS_DIR = MCP_HOME / "results"
SCRIPTS_DIR = MCP_HOME / "scripts"
RUNS_DIR = MCP_HOME / "runs"
STATUS_FILE = MCP_HOME / "status.json"
STOP_FILE = MCP_HOME / "stop.flag"
LOG_FILE = MCP_HOME / "mcp.log"
BRIDGE_JOURNAL = SERVER_ROOT / "ansys_workbench_bridge.wbjn"
ICEM_HOME = MCP_HOME / "icem"
ICEM_COMMANDS_DIR = ICEM_HOME / "commands"
ICEM_RESULTS_DIR = ICEM_HOME / "results"
ICEM_SCRIPTS_DIR = ICEM_HOME / "scripts"
ICEM_STATUS_FILE = ICEM_HOME / "status.json"
ICEM_LOG_FILE = ICEM_HOME / "icem_bridge.log"
ICEM_BRIDGE_SCRIPT = SERVER_ROOT / "icem_cfd_bridge.tcl"

DEFAULT_RUNWB2 = r"D:\Program Files\ANSYS Inc\v251\Framework\bin\Win64\RunWB2.exe"
DEFAULT_MECHANICAL = r"D:\Program Files\ANSYS Inc\v251\aisol\bin\winx64\AnsysWBU.exe"
DEFAULT_MAPDL = r"D:\Program Files\ANSYS Inc\v251\ansys\bin\winx64\ANSYS251.exe"
DEFAULT_FLUENT = r"D:\Program Files\ANSYS Inc\v251\fluent\ntbin\win64\fluent.exe"
DEFAULT_SPACECLAIM = r"D:\Program Files\ANSYS Inc\v251\scdm\SpaceClaim.exe"
DEFAULT_CFX_SOLVE = r"D:\Program Files\ANSYS Inc\v251\CFX\bin\cfx5solve.exe"
DEFAULT_CFX_PRE = r"D:\Program Files\ANSYS Inc\v251\CFX\bin\cfx5pre.exe"
DEFAULT_CFX_POST = r"D:\Program Files\ANSYS Inc\v251\CFX\bin\cfx5post.exe"
DEFAULT_ICEM_CFD = r"D:\Program Files\ANSYS Inc\v251\icemcfd\win64_amd\bin\icemcfd.bat"

RUNWB2 = Path(os.environ.get("ANSYS_RUNWB2", DEFAULT_RUNWB2))
MECHANICAL = Path(os.environ.get("ANSYS_MECHANICAL", DEFAULT_MECHANICAL))
MAPDL = Path(os.environ.get("ANSYS_MAPDL", DEFAULT_MAPDL))
FLUENT = Path(os.environ.get("ANSYS_FLUENT", DEFAULT_FLUENT))
SPACECLAIM = Path(os.environ.get("ANSYS_SPACECLAIM", DEFAULT_SPACECLAIM))
CFX_SOLVE = Path(os.environ.get("ANSYS_CFX_SOLVE", DEFAULT_CFX_SOLVE))
CFX_PRE = Path(os.environ.get("ANSYS_CFX_PRE", DEFAULT_CFX_PRE))
CFX_POST = Path(os.environ.get("ANSYS_CFX_POST", DEFAULT_CFX_POST))
ICEM_CFD = Path(os.environ.get("ANSYS_ICEM_CFD", DEFAULT_ICEM_CFD))

DEFAULT_TIMEOUT = 30.0

ANSYS_SCRIPT_SUFFIXES = {
    ".ccl",
    ".cse",
    ".jou",
    ".pre",
    ".py",
    ".rpl",
    ".tcl",
    ".wbjn",
}

WORKBENCH_ANALYSIS_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "steady_state_thermal": [{"template_name": "Steady-State Thermal", "solver": "ANSYS"}],
    "transient_thermal": [{"template_name": "Transient Thermal", "solver": "ANSYS"}],
    "static_structural": [{"template_name": "Static Structural", "solver": "ANSYS"}],
    "transient_structural": [{"template_name": "Transient Structural", "solver": "ANSYS"}],
    "modal": [{"template_name": "Modal", "solver": "ANSYS"}],
    "harmonic_response": [{"template_name": "Harmonic Response", "solver": "ANSYS"}],
    "response_spectrum": [{"template_name": "Response Spectrum", "solver": "ANSYS"}],
    "random_vibration": [{"template_name": "Random Vibration", "solver": "ANSYS"}],
    "cfx": [{"template_name": "Fluid Flow (CFX)", "solver": ""}, {"template_name": "CFX", "solver": ""}],
    "fluent": [{"template_name": "Fluid Flow (Fluent)", "solver": ""}, {"template_name": "Fluent", "solver": ""}],
    "system_coupling": [{"template_name": "System Coupling", "solver": ""}],
}

WORKBENCH_DEFAULT_PROJECT_NAMES: dict[str, str] = {
    "steady_state_thermal": "steady_state_thermal",
    "transient_thermal": "transient_thermal",
    "static_structural": "static_structural",
    "transient_structural": "transient_structural",
    "modal": "modal_analysis",
    "harmonic_response": "harmonic_response",
    "response_spectrum": "response_spectrum",
    "random_vibration": "random_vibration",
    "cfx": "cfx_flow",
    "fluent": "fluent_flow",
    "system_coupling": "system_coupling",
}

mcp = FastMCP("ansys-workbench-mcp")


def _ensure_dirs() -> None:
    for path in [
        COMMANDS_DIR,
        RESULTS_DIR,
        SCRIPTS_DIR,
        RUNS_DIR,
        ICEM_COMMANDS_DIR,
        ICEM_RESULTS_DIR,
        ICEM_SCRIPTS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def _as_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _split_extra_args(extra_args: str) -> list[str]:
    if not extra_args.strip():
        return []
    return shlex.split(extra_args, posix=False)


def _tcl_quote(value: str | Path) -> str:
    """Return a Tcl double-quoted literal without allowing substitutions."""
    text = str(value).replace("\\", "/")
    replacements = {
        "\\": "\\\\",
        '"': '\\"',
        "$": "\\$",
        "[": "\\[",
        "]": "\\]",
        "\r": "\\r",
        "\n": "\\n",
        "\t": "\\t",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return f'"{text}"'


def _icem_command(arguments: list[str]) -> str:
    """Build a Windows command line for the ICEM CFD batch launcher."""
    comspec = os.environ.get("COMSPEC", "cmd.exe")

    def quote_for_cmd(value: str | Path) -> str:
        text = str(value)
        if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        if '"' in text or "\r" in text or "\n" in text:
            raise ValueError("ICEM command arguments cannot contain quotes or newlines")
        # CALL performs another percent-expansion pass; double percent signs so
        # paths and arguments are passed literally. Quoting protects cmd.exe
        # metacharacters such as &, |, <, >, and ^.
        return f'"{text.replace("%", "%%")}"'

    launcher = " ".join(quote_for_cmd(value) for value in [ICEM_CFD, *arguments])
    return f"{quote_for_cmd(comspec)} /d /v:off /c call {launcher}"


def _icem_environment(batch: bool) -> dict[str, str]:
    """Build an ICEM environment that prioritizes Ansys runtime DLLs."""
    env = os.environ.copy()
    preferred_paths: list[str] = []
    try:
        ansys_root = ICEM_CFD.parents[3]
    except IndexError:
        ansys_root = None

    if ansys_root is not None:
        for relative_path in [
            Path("aisol") / "bin" / "winx64",
            Path("Framework") / "bin" / "Win64",
        ]:
            candidate = ansys_root / relative_path
            if candidate.is_dir():
                preferred_paths.append(str(candidate))

    inherited_paths = env.get("PATH", "").split(os.pathsep)
    ordered_paths: list[str] = []
    seen_paths: set[str] = set()
    for path in [*preferred_paths, *inherited_paths]:
        if not path:
            continue
        path_key = os.path.normcase(os.path.normpath(path))
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)
        ordered_paths.append(path)
    env["PATH"] = os.pathsep.join(ordered_paths)
    env["ANSYS_ICEM_MCP_HOME"] = str(ICEM_HOME)
    env["ICEM_MCP_BATCH"] = "1" if batch else "0"
    return env


def _analysis_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _analysis_candidates(analysis_type: str, template_name: str = "", solver: str = "") -> list[dict[str, str]]:
    if template_name:
        return [{"template_name": template_name, "solver": solver}]
    key = _analysis_key(analysis_type)
    candidates = WORKBENCH_ANALYSIS_TEMPLATES.get(key)
    if not candidates:
        supported = ", ".join(sorted(WORKBENCH_ANALYSIS_TEMPLATES))
        raise ValueError(f"Unsupported analysis_type {analysis_type!r}. Supported values: {supported}")
    return candidates


def _default_project_name(analysis_type: str, fallback: str = "workbench_analysis") -> str:
    return WORKBENCH_DEFAULT_PROJECT_NAMES.get(_analysis_key(analysis_type), fallback)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _run_process(
    args: list[str] | str,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        env=env,
    )
    return {
        "returncode": proc.returncode,
        "elapsed_seconds": round(time.time() - started, 3),
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
    }


def _workbench_command(journal_path: Path, batch: bool) -> list[str]:
    args = [str(RUNWB2)]
    if batch:
        args.append("-B")
    args.extend(["-R", str(journal_path)])
    return args


def _read_status() -> dict[str, Any]:
    return _read_json(STATUS_FILE)


def _send_command(cmd_type: str, timeout: float = DEFAULT_TIMEOUT, **kwargs: Any) -> dict[str, Any]:
    _ensure_dirs()
    cmd_id = uuid.uuid4().hex[:8]
    command = {"id": cmd_id, "type": cmd_type, "timestamp": time.time(), **kwargs}
    cmd_path = COMMANDS_DIR / f"cmd_{cmd_id}.json"
    result_path = RESULTS_DIR / f"{cmd_id}.json"

    _write_json(cmd_path, command)
    deadline = time.time() + float(timeout)
    while time.time() < deadline:
        if result_path.exists():
            result = _read_json(result_path)
            try:
                result_path.unlink()
            except Exception:
                pass
            return result
        time.sleep(0.05)

    try:
        cmd_path.unlink()
    except Exception:
        pass
    return {"success": False, "error": f"Timeout: no response from Workbench bridge in {timeout}s"}


def _read_icem_status() -> dict[str, Any]:
    return _read_json(ICEM_STATUS_FILE)


def _send_icem_command(
    command_type: str,
    timeout: float = DEFAULT_TIMEOUT,
    script: str = "",
) -> dict[str, Any]:
    """Send a Tcl command to the persistent ICEM CFD bridge."""
    _ensure_dirs()
    command_id = uuid.uuid4().hex[:8]
    command_path = ICEM_COMMANDS_DIR / f"cmd_{command_id}.tcl"
    result_path = ICEM_RESULTS_DIR / f"{command_id}.json"
    script_path = ICEM_SCRIPTS_DIR / f"script_{command_id}.tcl"

    if command_type == "execute":
        script_path.write_text(script, encoding="utf-8")

    descriptor = "\n".join(
        [
            f"set command_id {_tcl_quote(command_id)}",
            f"set command_type {_tcl_quote(command_type)}",
            f"set script_file {_tcl_quote(script_path if command_type == 'execute' else '')}",
            f"set result_file {_tcl_quote(result_path)}",
            "",
        ]
    )
    command_path.write_text(descriptor, encoding="utf-8")

    deadline = time.time() + float(timeout)
    while time.time() < deadline:
        if result_path.exists():
            result = _read_json(result_path)
            for path in [result_path, script_path]:
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
            if result:
                return result
            return {
                "success": False,
                "error": f"ICEM bridge returned an invalid result file: {result_path}",
            }
        time.sleep(0.05)

    for path in [command_path, script_path]:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    return {"success": False, "error": f"Timeout: no response from ICEM CFD bridge in {timeout}s"}


def _format_icem_result(result: dict[str, Any]) -> str:
    if result.get("success"):
        return _json(
            {
                "ok": True,
                "command_id": result.get("id", ""),
                "elapsed_seconds": result.get("elapsed_seconds", 0),
                "result": result.get("result", ""),
            }
        )
    return _json(
        {
            "ok": False,
            "command_id": result.get("id", ""),
            "error": result.get("error", "Unknown ICEM CFD bridge error"),
            "traceback": result.get("traceback", ""),
        }
    )


def _read_tail(path: Path, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def _path_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "size_bytes": None, "modified_time_ns": None}
    stat = path.stat()
    return {
        "exists": True,
        "size_bytes": stat.st_size if path.is_file() else None,
        "modified_time_ns": stat.st_mtime_ns,
    }


def _state_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if not after["exists"]:
        return False
    if not before["exists"]:
        return True
    return (
        before["size_bytes"] != after["size_bytes"]
        or before["modified_time_ns"] != after["modified_time_ns"]
    )


def _expected_output_status(
    value: str,
    before: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return existence and freshness metadata for an optional expected artifact."""
    if not value.strip():
        return {
            "required": False,
            "path": "",
            "exists": None,
            "size_bytes": None,
            "modified_time_ns": None,
            "updated": None,
        }
    path = _as_path(value)
    current = _path_state(path)
    return {
        "required": True,
        "path": str(path),
        **current,
        "updated": _state_changed(before, current) if before is not None else None,
    }


def _clear_stale_icem_commands() -> None:
    """Remove only MCP-generated command descriptors from an earlier bridge."""
    for path in ICEM_COMMANDS_DIR.glob("cmd_*.tcl"):
        try:
            path.unlink()
        except OSError:
            pass


def _format_bridge_result(result: dict[str, Any]) -> str:
    if result.get("success"):
        data = result.get("data")
        output = result.get("output", "")
        if data is not None:
            return _json(data if isinstance(data, dict) else {"data": data, "output": output})
        return output if output else "(Command executed successfully, no output)"
    error = result.get("error", "Unknown error")
    tb = result.get("traceback", "")
    if error == "Unknown error" and not tb:
        return f"Error: {error}\nRaw result: {_json(result)}"
    return f"Error: {error}\n{tb}".strip()


def _wait_for_log_marker(log_path: Path, marker: str, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if log_path.exists():
            try:
                if marker in log_path.read_text(encoding="utf-8", errors="replace"):
                    return True
            except OSError:
                pass
        time.sleep(0.5)
    return False


@mcp.resource("ansys-workbench://status")
def workbench_status_resource() -> str:
    """Current Ansys Workbench bridge status."""
    status = _read_status()
    if not status:
        return _json({"connected": False, "detail": "status.json not found", "mcp_home": str(MCP_HOME)})
    return _json(status)


@mcp.resource("ansys-workbench://installation")
def installation_resource() -> str:
    """Configured Ansys executable paths for this MCP server."""
    return check_ansys_installation()


@mcp.resource("ansys-workbench://icem/status")
def icem_status_resource() -> str:
    """Current persistent ICEM CFD bridge status."""
    status = _read_icem_status()
    if not status:
        return _json(
            {
                "connected": False,
                "detail": "ICEM CFD status.json not found",
                "icem_mcp_home": str(ICEM_HOME),
            }
        )
    return _json(status)


@mcp.tool()
def check_ansys_installation() -> str:
    """Check configured Workbench, Mechanical, MAPDL, CFD, and bridge paths."""
    data = {
        "version": __version__,
        "runwb2": str(RUNWB2),
        "runwb2_exists": RUNWB2.exists(),
        "mechanical": str(MECHANICAL),
        "mechanical_exists": MECHANICAL.exists(),
        "mapdl": str(MAPDL),
        "mapdl_exists": MAPDL.exists(),
        "fluent": str(FLUENT),
        "fluent_exists": FLUENT.exists(),
        "spaceclaim": str(SPACECLAIM),
        "spaceclaim_exists": SPACECLAIM.exists(),
        "cfx_solve": str(CFX_SOLVE),
        "cfx_solve_exists": CFX_SOLVE.exists(),
        "cfx_pre": str(CFX_PRE),
        "cfx_pre_exists": CFX_PRE.exists(),
        "cfx_post": str(CFX_POST),
        "cfx_post_exists": CFX_POST.exists(),
        "icem_cfd": str(ICEM_CFD),
        "icem_cfd_exists": ICEM_CFD.exists(),
        "icem_bridge_script": str(ICEM_BRIDGE_SCRIPT),
        "icem_bridge_script_exists": ICEM_BRIDGE_SCRIPT.exists(),
        "icem_mcp_home": str(ICEM_HOME),
        "bridge_journal": str(BRIDGE_JOURNAL),
        "bridge_journal_exists": BRIDGE_JOURNAL.exists(),
        "mcp_home": str(MCP_HOME),
        "server_root": str(SERVER_ROOT),
    }
    return _json(data)


@mcp.tool()
def write_ansys_script(output_path: str, content: str, overwrite: bool = False) -> str:
    """Write an Ansys automation script with guarded extension and overwrite checks.

    Supported extensions are .wbjn, .py, .tcl, .rpl, .jou, .ccl, .pre, and
    .cse. Existing files are preserved unless overwrite=True.
    """
    path = _as_path(output_path)
    suffix = path.suffix.lower()
    if suffix not in ANSYS_SCRIPT_SUFFIXES:
        return _json(
            {
                "ok": False,
                "error": f"Unsupported script extension: {suffix or '(none)'}",
                "supported_extensions": sorted(ANSYS_SCRIPT_SUFFIXES),
            }
        )
    if "\x00" in content:
        return _json({"ok": False, "error": "Script content cannot contain NUL bytes"})
    if path.exists() and not overwrite:
        return _json(
            {
                "ok": False,
                "error": f"Refusing to overwrite existing file without overwrite=True: {path}",
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    payload = path.read_bytes()
    return _json(
        {
            "ok": True,
            "path": str(path),
            "extension": suffix,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    )


@mcp.tool()
def check_icem_installation() -> str:
    """Check the configured ICEM CFD launcher and persistent bridge script."""
    return _json(
        {
            "version": __version__,
            "icem_cfd": str(ICEM_CFD),
            "icem_cfd_exists": ICEM_CFD.exists(),
            "bridge_script": str(ICEM_BRIDGE_SCRIPT),
            "bridge_script_exists": ICEM_BRIDGE_SCRIPT.exists(),
            "icem_mcp_home": str(ICEM_HOME),
        }
    )


@mcp.tool()
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
    if not ICEM_CFD.exists():
        return _json({"ok": False, "error": f"ICEM CFD launcher not found: {ICEM_CFD}"})
    if not ICEM_BRIDGE_SCRIPT.exists():
        return _json({"ok": False, "error": f"ICEM CFD bridge script not found: {ICEM_BRIDGE_SCRIPT}"})

    status = _read_icem_status()
    if status.get("status") == "running":
        ping_result = _send_icem_command("ping", timeout=5.0)
        if ping_result.get("success"):
            return _json(
                {
                    "ok": True,
                    "already_running": True,
                    "status": status,
                    "ping": ping_result,
                }
            )

    startup_project = ""
    if project_file:
        project = _as_path(project_file)
        if not project.exists():
            return _json({"ok": False, "error": f"ICEM project/input file not found: {project}"})
        startup_project = str(project)

    cwd = _as_path(workdir) if workdir else RUNS_DIR / "icem_bridge"
    cwd.mkdir(parents=True, exist_ok=True)
    _ensure_dirs()
    _clear_stale_icem_commands()
    try:
        if ICEM_STATUS_FILE.exists():
            ICEM_STATUS_FILE.unlink()
    except OSError:
        pass

    arguments: list[str] = []
    if batch:
        arguments.append("-batch")
    arguments.extend(["-script", str(ICEM_BRIDGE_SCRIPT)])
    arguments.extend(_split_extra_args(extra_args))
    if startup_project:
        arguments.append(startup_project)

    env = _icem_environment(batch)
    try:
        command = _icem_command(arguments)
    except ValueError as exc:
        return _json({"ok": False, "error": str(exc)})
    log_handle = ICEM_LOG_FILE.open("a", encoding="utf-8", errors="replace")
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
        status = _read_icem_status()
        if status.get("status") == "running":
            ping_result = _send_icem_command("ping", timeout=5.0)
            if ping_result.get("success"):
                return _json(
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

    return _json(
        {
            "ok": False,
            "pid": proc.pid,
            "returncode": proc.poll(),
            "batch": batch,
            "status": _read_icem_status(),
            "detail": "ICEM CFD bridge did not answer before timeout",
            "log_file": str(ICEM_LOG_FILE),
            "log_tail": _read_tail(ICEM_LOG_FILE),
        }
    )


@mcp.tool()
def stop_icem_bridge(timeout_seconds: int = 15) -> str:
    """Stop the persistent ICEM CFD bridge and close its ICEM process."""
    result = _send_icem_command("stop", timeout=min(float(timeout_seconds), 5.0))
    if not result.get("success"):
        return _json({"ok": False, "command_result": result, "status": _read_icem_status()})

    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        status = _read_icem_status()
        if status.get("status") == "stopped":
            return _json({"ok": True, "status": status, "command_result": result})
        time.sleep(0.25)
    return _json({"ok": False, "status": _read_icem_status(), "command_result": result})


@mcp.tool()
def check_icem_connection() -> str:
    """Check whether the persistent ICEM CFD Tcl bridge is responding."""
    status = _read_icem_status()
    if not status:
        return _json(
            {
                "ok": False,
                "error": "ICEM CFD bridge status not found. Run start_icem_bridge().",
            }
        )
    if status.get("status") != "running":
        return _json({"ok": False, "error": "ICEM CFD bridge is not running", "status": status})
    result = _send_icem_command("ping", timeout=10.0)
    return _json({"ok": bool(result.get("success")), "status": status, "ping": result})


@mcp.tool()
def execute_icem_script(script: str, timeout_seconds: int = 120) -> str:
    """Execute Tcl/Replay commands inside the live ICEM CFD bridge session.

    The returned result is the value produced by the final Tcl command. This
    provides direct access to ICEM commands such as ic_load_tetin and blocking,
    meshing, quality, and output-interface commands recorded by Replay Control.
    """
    if not script.strip():
        return _json({"ok": False, "error": "script must not be empty"})
    result = _send_icem_command("execute", timeout=float(timeout_seconds), script=script)
    return _format_icem_result(result)


@mcp.tool()
def get_icem_session_info(timeout_seconds: int = 30) -> str:
    """Get basic information from the live ICEM CFD Tcl interpreter."""
    script = r"""
set __icem_mcp_info ""
append __icem_mcp_info "pid=[pid]\n"
append __icem_mcp_info "cwd=[pwd]\n"
append __icem_mcp_info "tcl_patchlevel=[info patchlevel]\n"
append __icem_mcp_info "ic_commands=[llength [info commands ic_*]]\n"
append __icem_mcp_info "blocking_commands=[llength [info commands ic_hex_*]]\n"
set __icem_mcp_info
"""
    result = _send_icem_command("execute", timeout=float(timeout_seconds), script=script)
    return _format_icem_result(result)


@mcp.tool()
def list_icem_commands(pattern: str = "ic_*", limit: int = 300, timeout_seconds: int = 30) -> str:
    """List commands available in the live ICEM Tcl interpreter.

    pattern is a Tcl info-commands glob, for example ic_hex_* or ic_geo_*.
    """
    safe_limit = max(1, min(int(limit), 2000))
    script = "\n".join(
        [
            f"set __icem_mcp_commands [lsort [info commands {_tcl_quote(pattern)}]]",
            f"set __icem_mcp_commands [lrange $__icem_mcp_commands 0 {safe_limit - 1}]",
            'join $__icem_mcp_commands "\\n"',
            "",
        ]
    )
    result = _send_icem_command("execute", timeout=float(timeout_seconds), script=script)
    return _format_icem_result(result)


@mcp.tool()
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
    if not ICEM_CFD.exists():
        return _json({"ok": False, "error": f"ICEM CFD launcher not found: {ICEM_CFD}"})

    replay = _as_path(replay_file)
    if not replay.exists():
        return _json({"ok": False, "error": f"ICEM replay file not found: {replay}"})

    startup_project = ""
    if project_file:
        project = _as_path(project_file)
        if not project.exists():
            return _json({"ok": False, "error": f"ICEM project/input file not found: {project}"})
        startup_project = str(project)

    cwd = _as_path(workdir) if workdir else replay.parent
    cwd.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:8]
    wrapper = cwd / f"icem_mcp_wrapper_{run_id}.tcl"
    result_file = cwd / f"icem_mcp_result_{run_id}.txt"
    wrapper_script = f"""set __icem_mcp_code [catch {{source {_tcl_quote(replay)}}} __icem_mcp_result]
set __icem_mcp_channel [open {_tcl_quote(result_file)} w]
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
    arguments.extend(_split_extra_args(extra_args))
    if startup_project:
        arguments.append(startup_project)
    try:
        command = _icem_command(arguments)
    except ValueError as exc:
        return _json({"ok": False, "error": str(exc)})

    try:
        process_result = _run_process(command, cwd, timeout_seconds, env=_icem_environment(batch=True))
    except subprocess.TimeoutExpired:
        return _json(
            {
                "ok": False,
                "error": f"Timed out after {timeout_seconds}s",
                "replay_file": str(replay),
                "wrapper_file": str(wrapper),
            }
        )

    result_text = _read_tail(result_file)
    successful_code = result_text.startswith("code=0") or result_text.startswith("code=2")
    ok = process_result["returncode"] == 0 and result_file.exists() and successful_code
    return _json(
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


@mcp.tool()
def start_workbench_bridge(batch: bool = True, wait_seconds: int = 20) -> str:
    """Launch Workbench with the file-IPC bridge journal loaded.

    The bridge journal keeps Workbench alive and polls commands/*.json.
    Use stop_workbench_bridge to stop it.
    """
    if not RUNWB2.exists():
        return _json({"ok": False, "error": f"RunWB2 not found: {RUNWB2}"})
    if not BRIDGE_JOURNAL.exists():
        return _json({"ok": False, "error": f"Bridge journal not found: {BRIDGE_JOURNAL}"})

    status = _read_status()
    if status.get("status") == "running":
        ping_result = _send_command("ping", timeout=5.0)
        if ping_result.get("success"):
            return _json({"ok": True, "already_running": True, "status": status, "ping": ping_result})

    _ensure_dirs()
    try:
        if STOP_FILE.exists():
            STOP_FILE.unlink()
    except Exception:
        pass

    env = os.environ.copy()
    env["ANSYS_WORKBENCH_MCP_HOME"] = str(MCP_HOME)
    proc = subprocess.Popen(
        _workbench_command(BRIDGE_JOURNAL, batch=batch),
        cwd=str(SERVER_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + max(1, int(wait_seconds))
    ping_result: dict[str, Any] = {}
    while time.time() < deadline:
        status = _read_status()
        if status.get("status") == "running":
            ping_result = _send_command("ping", timeout=5.0)
            if ping_result.get("success"):
                return _json({"ok": True, "pid": proc.pid, "status": status, "ping": ping_result})
        time.sleep(0.5)

    return _json({"ok": False, "pid": proc.pid, "status": _read_status(), "detail": "Bridge did not answer before timeout"})


@mcp.tool()
def stop_workbench_bridge(timeout_seconds: int = 10) -> str:
    """Signal the Workbench bridge loop to stop."""
    result = _send_command("stop", timeout=min(float(timeout_seconds), 5.0))
    if not result.get("success"):
        try:
            STOP_FILE.write_text("stop", encoding="utf-8")
        except Exception:
            pass

    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        status = _read_status()
        if status.get("status") in {"stopped", "ready"}:
            return _json({"ok": True, "status": status, "command_result": result})
        time.sleep(0.25)

    return _json({"ok": False, "status": _read_status(), "command_result": result})


@mcp.tool()
def check_workbench_connection() -> str:
    """Check whether the Workbench bridge journal is running and responding."""
    status = _read_status()
    if not status:
        return "Workbench bridge status not found. Run start_workbench_bridge() or load ansys_workbench_bridge.wbjn in Workbench."

    if status.get("status") != "running":
        return f"Workbench bridge is not running: {_json(status)}"

    result = _send_command("ping", timeout=10.0)
    if result.get("success"):
        data = result.get("data", {})
        version = data.get("version", "?") if isinstance(data, dict) else "?"
        return f"Connected to Ansys Workbench bridge v{version}.\nStatus: {_json(status)}"
    return f"Workbench bridge status exists but ping failed: {_json(result)}"


@mcp.tool()
def execute_workbench_script(script: str, timeout_seconds: int = 60) -> str:
    """Execute Python/Workbench journal code inside the running Workbench bridge."""
    result = _send_command("execute_script", timeout=float(timeout_seconds), script=script)
    return _format_bridge_result(result)


@mcp.tool()
def get_project_info(timeout_seconds: int = 30) -> str:
    """Get project/system/component information from the running Workbench bridge."""
    result = _send_command("get_project_info", timeout=float(timeout_seconds))
    return _format_bridge_result(result)


@mcp.tool()
def open_project(project_file: str, timeout_seconds: int = 120) -> str:
    """Open a Workbench project in the running Workbench bridge."""
    result = _send_command("open_project", timeout=float(timeout_seconds), project_file=project_file)
    return _format_bridge_result(result)


@mcp.tool()
def save_project(project_file: str = "", overwrite: bool = True, timeout_seconds: int = 120) -> str:
    """Save the current Workbench project through the running bridge."""
    result = _send_command(
        "save_project",
        timeout=float(timeout_seconds),
        project_file=project_file,
        overwrite=overwrite,
    )
    return _format_bridge_result(result)


@mcp.tool()
def update_project(timeout_seconds: int = 600) -> str:
    """Run Workbench Update() in the running bridge."""
    result = _send_command("update_project", timeout=float(timeout_seconds))
    return _format_bridge_result(result)


@mcp.tool()
def probe_workbench_analysis_templates_live(timeout_seconds: int = 60) -> str:
    """Check Workbench template availability for the supported analysis wrappers."""
    result = _send_command(
        "probe_analysis_templates",
        timeout=float(timeout_seconds),
        analysis_templates=WORKBENCH_ANALYSIS_TEMPLATES,
    )
    return _format_bridge_result(result)


@mcp.tool()
def probe_system_coupling_live(timeout_seconds: int = 60) -> str:
    """Verify the System Coupling template and its live Workbench scripting API."""
    result = _send_command("probe_system_coupling", timeout=float(timeout_seconds))
    return _format_bridge_result(result)


@mcp.tool()
def create_cfx_mechanical_fsi_project_live(
    project_dir: str,
    project_name: str = "cfx_mechanical_fsi",
    cfx_geometry_file: str = "",
    mechanical_geometry_file: str = "",
    overwrite: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create and connect CFX, Transient Structural, and System Coupling systems.

    This creates the two-way FSI project topology. Participant meshes, physics,
    coupling regions, variables, and data transfers must still be completed
    before solving. Separate fluid and structural geometry files are optional.
    """
    result = _send_command(
        "create_cfx_mechanical_fsi_project",
        timeout=float(timeout_seconds),
        project_dir=project_dir,
        project_name=project_name,
        cfx_geometry_file=cfx_geometry_file,
        mechanical_geometry_file=mechanical_geometry_file,
        overwrite=overwrite,
    )
    return _format_bridge_result(result)


@mcp.tool()
def connect_system_coupling_participants_live(
    system_indices: list[int],
    timeout_seconds: int = 120,
) -> str:
    """Connect existing Workbench systems to the current System Coupling Setup.

    Use get_project_info to obtain zero-based system indices. Do not include the
    System Coupling system itself.
    """
    result = _send_command(
        "connect_system_coupling_participants",
        timeout=float(timeout_seconds),
        system_indices=system_indices,
    )
    return _format_bridge_result(result)


@mcp.tool()
def get_system_coupling_status_live(timeout_seconds: int = 60) -> str:
    """List System Coupling participants, regions, variables, transfers, and settings."""
    result = _send_command("get_system_coupling_status", timeout=float(timeout_seconds))
    return _format_bridge_result(result)


@mcp.tool()
def configure_system_coupling_settings_live(
    step_size: str = "",
    end_time: str = "",
    number_of_steps: int = 0,
    minimum_iterations: int = 0,
    maximum_iterations: int = 0,
    timeout_seconds: int = 60,
) -> str:
    """Set System Coupling transient duration and coupling-iteration controls.

    Quantity values include units, for example step_size="0.001 [s]" and
    end_time="0.1 [s]". Zero/empty inputs leave a setting unchanged.
    """
    result = _send_command(
        "configure_system_coupling_settings",
        timeout=float(timeout_seconds),
        step_size=step_size,
        end_time=end_time,
        number_of_steps=number_of_steps,
        minimum_iterations=minimum_iterations,
        maximum_iterations=maximum_iterations,
    )
    return _format_bridge_result(result)


@mcp.tool()
def create_system_coupling_data_transfer_live(
    name: str,
    source_participant: str,
    source_region: str,
    source_variable: str,
    target_participant: str,
    target_region: str,
    target_variable: str,
    timeout_seconds: int = 60,
) -> str:
    """Create one data transfer using published participant/region/variable names.

    Call get_system_coupling_status_live after participant Setup cells have been
    refreshed to discover the exact names exposed by CFX and Mechanical.
    """
    result = _send_command(
        "create_system_coupling_data_transfer",
        timeout=float(timeout_seconds),
        name=name,
        source_participant=source_participant,
        source_region=source_region,
        source_variable=source_variable,
        target_participant=target_participant,
        target_region=target_region,
        target_variable=target_variable,
    )
    return _format_bridge_result(result)


@mcp.tool()
def configure_cfx_mechanical_two_way_fsi_live(
    cfx_participant: str,
    cfx_region: str,
    cfx_displacement_variable: str,
    cfx_force_variable: str,
    mechanical_participant: str,
    mechanical_region: str,
    mechanical_displacement_variable: str,
    mechanical_force_variable: str,
    timeout_seconds: int = 120,
) -> str:
    """Create the two transfers required for two-way CFX-Mechanical FSI.

    Creates Mechanical displacement -> CFX displacement and CFX force ->
    Mechanical force. Names must match get_system_coupling_status_live output.
    """
    result = _send_command(
        "configure_cfx_mechanical_two_way_fsi",
        timeout=float(timeout_seconds),
        cfx_participant=cfx_participant,
        cfx_region=cfx_region,
        cfx_displacement_variable=cfx_displacement_variable,
        cfx_force_variable=cfx_force_variable,
        mechanical_participant=mechanical_participant,
        mechanical_region=mechanical_region,
        mechanical_displacement_variable=mechanical_displacement_variable,
        mechanical_force_variable=mechanical_force_variable,
    )
    return _format_bridge_result(result)


@mcp.tool()
def export_system_coupling_setup_live(output_path: str, timeout_seconds: int = 180) -> str:
    """Export the current System Coupling setup to an `.sci` file."""
    result = _send_command(
        "export_system_coupling_setup",
        timeout=float(timeout_seconds),
        output_path=output_path,
    )
    return _format_bridge_result(result)


@mcp.tool()
def run_system_coupling_solution_live(timeout_seconds: int = 3600) -> str:
    """Update the System Coupling Solution cell and wait for the coupled run.

    The participant setups and all required transfers must already validate.
    """
    result = _send_command("run_system_coupling_solution", timeout=float(timeout_seconds))
    return _format_bridge_result(result)


@mcp.tool()
def create_workbench_analysis_system_live(
    analysis_type: str,
    project_dir: str,
    project_name: str = "",
    geometry_file: str = "",
    refresh_model: bool = False,
    reset_project: bool = True,
    template_name: str = "",
    solver: str = "",
    timeout_seconds: int = 180,
) -> str:
    """Create a Workbench analysis system in the running bridge.

    Supported analysis_type values include steady_state_thermal,
    transient_thermal, static_structural, transient_structural, modal,
    harmonic_response, response_spectrum, random_vibration, cfx, and fluent.
    template_name/solver can override the built-in mapping.
    """
    try:
        candidates = _analysis_candidates(analysis_type, template_name, solver)
    except ValueError as exc:
        return _json({"ok": False, "error": str(exc)})
    result = _send_command(
        "create_analysis_system",
        timeout=float(timeout_seconds),
        analysis_type=_analysis_key(analysis_type),
        project_dir=project_dir,
        project_name=project_name or _default_project_name(analysis_type),
        geometry_file=geometry_file,
        refresh_model=refresh_model,
        reset_project=reset_project,
        template_candidates=candidates,
    )
    return _format_bridge_result(result)


@mcp.tool()
def create_steady_state_thermal_system_live(
    project_dir: str,
    project_name: str = "steady_state_thermal",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Steady-State Thermal system in the running Workbench bridge."""
    result = _send_command(
        "create_steady_state_thermal_system",
        timeout=float(timeout_seconds),
        project_dir=project_dir,
        project_name=project_name,
        geometry_file=geometry_file,
        refresh_model=refresh_model,
    )
    return _format_bridge_result(result)


@mcp.tool()
def create_transient_thermal_system_live(
    project_dir: str,
    project_name: str = "transient_thermal",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Transient Thermal system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "transient_thermal",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_static_structural_system_live(
    project_dir: str,
    project_name: str = "static_structural",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Static Structural system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "static_structural",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_transient_structural_system_live(
    project_dir: str,
    project_name: str = "transient_structural",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Transient Structural dynamics system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "transient_structural",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_modal_analysis_system_live(
    project_dir: str,
    project_name: str = "modal_analysis",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Modal dynamics system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "modal",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_harmonic_response_system_live(
    project_dir: str,
    project_name: str = "harmonic_response",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Harmonic Response dynamics system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "harmonic_response",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_response_spectrum_system_live(
    project_dir: str,
    project_name: str = "response_spectrum",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Response Spectrum dynamics system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "response_spectrum",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_random_vibration_system_live(
    project_dir: str,
    project_name: str = "random_vibration",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Random Vibration dynamics system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "random_vibration",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_cfx_flow_system_live(
    project_dir: str,
    project_name: str = "cfx_flow",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Fluid Flow (CFX) system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "cfx",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_fluent_flow_system_live(
    project_dir: str,
    project_name: str = "fluent_flow",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Try to create a Fluid Flow (Fluent) system in the running Workbench bridge."""
    return create_workbench_analysis_system_live(
        "fluent",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def create_thermal_bar_demo_live(
    project_dir: str = r"D:\ansys-workbench-mcp\runs\thermal_bar_demo_live",
    timeout_seconds: int = 600,
) -> str:
    """Create and solve a simple thermal bar demo through the running Workbench bridge."""
    result = _send_command("create_thermal_bar_demo", timeout=float(timeout_seconds), project_dir=project_dir)
    return _format_bridge_result(result)


@mcp.tool()
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
    if not SPACECLAIM.exists():
        return _json({"ok": False, "error": f"SpaceClaim not found: {SPACECLAIM}"})

    script = _as_path(script_path)
    if not script.exists():
        return _json({"ok": False, "error": f"SpaceClaim script not found: {script}"})
    if script.suffix.lower() != ".py":
        return _json({"ok": False, "error": "SpaceClaim script must use the .py extension"})

    cwd = _as_path(workdir) if workdir else script.parent
    cwd.mkdir(parents=True, exist_ok=True)
    log_file = cwd / f"{script.stem}.spaceclaim.log"
    args = [
        str(SPACECLAIM),
        f"/Headless={'True' if headless else 'False'}",
        "/Splash=False",
        f"/RunScript={script}",
        f"/ScriptAPI={script_api}",
        f"/ScriptOutput={log_file}",
        "/ExitAfterScript=True",
    ]
    args.extend(_split_extra_args(extra_args))
    artifact_before = _expected_output_status(expected_output)

    try:
        result = _run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "script": str(script)})

    artifact = _expected_output_status(expected_output, before=artifact_before)
    ok = result["returncode"] == 0 and (
        not artifact["required"] or (artifact["exists"] is True and artifact["updated"] is True)
    )
    return _json(
        {
            "ok": ok,
            "script": str(script),
            "workdir": str(cwd),
            "command": args,
            "log_file": str(log_file),
            "log_tail": _read_tail(log_file),
            "expected_output": artifact,
            "process": result,
        }
    )


@mcp.tool()
def run_cfx_pre_session(
    session_file: str,
    workdir: str = "",
    expected_output: str = "",
    extra_args: str = "",
    timeout_seconds: int = 900,
) -> str:
    """Run a CFX-Pre session in batch mode and optionally verify a .cfx or .def output."""
    if not CFX_PRE.exists():
        return _json({"ok": False, "error": f"CFX-Pre not found: {CFX_PRE}"})

    session = _as_path(session_file)
    if not session.exists():
        return _json({"ok": False, "error": f"CFX-Pre session not found: {session}"})
    cwd = _as_path(workdir) if workdir else session.parent
    cwd.mkdir(parents=True, exist_ok=True)
    args = [str(CFX_PRE), "-batch", str(session)]
    args.extend(_split_extra_args(extra_args))
    artifact_before = _expected_output_status(expected_output)

    try:
        result = _run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "session_file": str(session)})

    artifact = _expected_output_status(expected_output, before=artifact_before)
    ok = result["returncode"] == 0 and (
        not artifact["required"] or (artifact["exists"] is True and artifact["updated"] is True)
    )
    return _json(
        {
            "ok": ok,
            "session_file": str(session),
            "workdir": str(cwd),
            "command": args,
            "expected_output": artifact,
            "process": result,
        }
    )


@mcp.tool()
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
    if not CFX_POST.exists():
        return _json({"ok": False, "error": f"CFD-Post not found: {CFX_POST}"})

    session = _as_path(session_file)
    if not session.exists():
        return _json({"ok": False, "error": f"CFD-Post session not found: {session}"})

    mode = rendering.strip().lower()
    render_flags = {
        "software": "-batch-software-rendering",
        "gpu": "-batch-gpu-rendering",
    }
    if mode not in render_flags:
        return _json({"ok": False, "error": "rendering must be software or gpu"})

    cwd = _as_path(workdir) if workdir else session.parent
    cwd.mkdir(parents=True, exist_ok=True)
    args = [str(CFX_POST)]
    loaded_result = ""
    loaded_state = ""
    if result_file:
        result_path = _as_path(result_file)
        if not result_path.exists():
            return _json({"ok": False, "error": f"CFX result file not found: {result_path}"})
        loaded_result = str(result_path)
        args.extend(["-results", loaded_result])
    if state_file:
        state_path = _as_path(state_file)
        if not state_path.exists():
            return _json({"ok": False, "error": f"CFD-Post state file not found: {state_path}"})
        loaded_state = str(state_path)
        args.extend(["-state", loaded_state])
    args.extend([render_flags[mode], str(session)])
    args.extend(_split_extra_args(extra_args))
    artifact_before = _expected_output_status(expected_output)

    try:
        result = _run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "session_file": str(session)})

    artifact = _expected_output_status(expected_output, before=artifact_before)
    ok = result["returncode"] == 0 and (
        not artifact["required"] or (artifact["exists"] is True and artifact["updated"] is True)
    )
    return _json(
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


@mcp.tool()
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
    if not RUNWB2.exists():
        return _json({"ok": False, "error": f"RunWB2 not found: {RUNWB2}"})

    journal = _as_path(journal_path)
    if not journal.exists():
        return _json({"ok": False, "error": f"Journal not found: {journal}"})

    cwd = _as_path(workdir) if workdir else journal.parent
    cwd.mkdir(parents=True, exist_ok=True)
    if completion_marker and not log_file:
        return _json({"ok": False, "error": "completion_marker requires log_file"})
    log_path = _as_path(log_file) if log_file else None
    log_before = _path_state(log_path) if log_path else None
    artifact_before = _expected_output_status(expected_output)

    try:
        result = _run_process(_workbench_command(journal, batch=batch), cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(journal)})

    log_text = _read_tail(log_path) if log_path else ""
    log_after = _path_state(log_path) if log_path else None
    log_updated = _state_changed(log_before, log_after) if log_before and log_after else None
    marker_seen = completion_marker in log_text if completion_marker else None
    artifact = _expected_output_status(expected_output, before=artifact_before)
    ok = (
        result["returncode"] == 0
        and (marker_seen is not False)
        and (log_updated is not False if completion_marker else True)
        and (
            not artifact["required"]
            or (artifact["exists"] is True and artifact["updated"] is True)
        )
    )
    return _json(
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


@mcp.tool()
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
    if not RUNWB2.exists():
        return _json({"ok": False, "error": f"RunWB2 not found: {RUNWB2}"})

    try:
        candidates = _analysis_candidates(analysis_type, template_name, solver)
    except ValueError as exc:
        return _json({"ok": False, "error": str(exc)})

    if geometry_file:
        geom = _as_path(geometry_file)
        if not geom.exists():
            return _json({"ok": False, "error": f"Geometry file not found: {geom}"})
        geometry_file = str(geom)

    analysis_key = _analysis_key(analysis_type)
    final_project_name = project_name or _default_project_name(analysis_key)
    out_dir = _as_path(project_dir)
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
        process_result = _run_process(_workbench_command(journal_file, batch=True), out_dir, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(journal_file)})

    marker_seen = _wait_for_log_marker(log_file, marker, min(timeout_seconds, 120))
    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    ok = project_file.exists() and marker_seen and "ERROR" not in log_text
    return _json(
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


@mcp.tool()
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
    if not RUNWB2.exists():
        return _json({"ok": False, "error": f"RunWB2 not found: {RUNWB2}"})

    out_dir = _as_path(project_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    project_file = out_dir / f"{project_name}.wbpj"
    journal_file = out_dir / f"{project_name}_create_steady_thermal.wbjn"
    log_file = out_dir / f"{project_name}_create_steady_thermal.log"

    geom_line = ""
    if geometry_file:
        geom = _as_path(geometry_file)
        if not geom.exists():
            return _json({"ok": False, "error": f"Geometry file not found: {geom}"})
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
        process_result = _run_process(_workbench_command(journal_file, batch=True), out_dir, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(journal_file)})

    marker_seen = _wait_for_log_marker(log_file, marker, min(timeout_seconds, 120))
    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
    ok = project_file.exists() and marker_seen and "ERROR" not in log_text
    return _json(
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


@mcp.tool()
def run_mapdl_input(
    input_file: str,
    workdir: str = "",
    job_name: str = "ansys_mcp_job",
    timeout_seconds: int = 600,
) -> str:
    """Run a Mechanical APDL input file with MAPDL."""
    if not MAPDL.exists():
        return _json({"ok": False, "error": f"MAPDL not found: {MAPDL}"})

    inp = _as_path(input_file)
    if not inp.exists():
        return _json({"ok": False, "error": f"Input file not found: {inp}"})

    cwd = _as_path(workdir) if workdir else inp.parent
    cwd.mkdir(parents=True, exist_ok=True)
    out_file = cwd / f"{job_name}.out"
    args = [str(MAPDL), "-b", "-i", str(inp), "-o", str(out_file), "-j", job_name]

    try:
        result = _run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "input_file": str(inp)})

    out_tail = out_file.read_text(encoding="utf-8", errors="replace")[-12000:] if out_file.exists() else ""
    return _json(
        {
            "ok": result["returncode"] == 0,
            "input_file": str(inp),
            "out_file": str(out_file),
            "process": result,
            "out_tail": out_tail,
        }
    )


@mcp.tool()
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
    if not FLUENT.exists():
        return _json({"ok": False, "error": f"Fluent not found: {FLUENT}"})

    journal = _as_path(journal_path)
    if not journal.exists():
        return _json({"ok": False, "error": f"Journal not found: {journal}"})

    cwd = _as_path(workdir) if workdir else journal.parent
    cwd.mkdir(parents=True, exist_ok=True)

    dim = dimension.strip().lower()
    if dim not in {"2d", "3d"}:
        return _json({"ok": False, "error": "dimension must be 2d or 3d"})
    prec = precision.strip().lower()
    if prec in {"double", "dp"}:
        fluent_mode = dim + "dp"
    elif prec in {"single", "sp"}:
        fluent_mode = dim
    else:
        return _json({"ok": False, "error": "precision must be single or double"})

    args = [str(FLUENT), fluent_mode]
    if int(processors) > 1:
        args.append(f"-t{int(processors)}")
    if not gui:
        args.append("-g")
    args.extend(["-i", str(journal)])
    args.extend(_split_extra_args(extra_args))

    try:
        result = _run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(journal)})

    return _json(
        {
            "ok": result["returncode"] == 0,
            "journal": str(journal),
            "workdir": str(cwd),
            "command": args,
            "process": result,
        }
    )


@mcp.tool()
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
    if not CFX_SOLVE.exists():
        return _json({"ok": False, "error": f"CFX solver not found: {CFX_SOLVE}"})

    definition = _as_path(definition_file)
    if not definition.exists():
        return _json({"ok": False, "error": f"Definition file not found: {definition}"})

    cwd = _as_path(workdir) if workdir else definition.parent
    cwd.mkdir(parents=True, exist_ok=True)

    args = [str(CFX_SOLVE), "-batch", "-def", str(definition), "-chdir", str(cwd)]
    if run_name:
        args.extend(["-name", run_name])
    if double_precision:
        args.append("-double")
    if int(processors) > 1:
        args.extend(["-par-local", "-partition", str(int(processors))])
    args.extend(_split_extra_args(extra_args))

    try:
        result = _run_process(args, cwd, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "definition_file": str(definition)})

    return _json(
        {
            "ok": result["returncode"] == 0,
            "definition_file": str(definition),
            "workdir": str(cwd),
            "command": args,
            "process": result,
        }
    )


@mcp.tool()
def create_and_run_thermal_bar_demo(
    project_dir: str = r"D:\ansys-workbench-mcp\runs\thermal_bar_demo",
    timeout_seconds: int = 600,
) -> str:
    """Create and solve a small steady thermal bar demo through direct Workbench batch."""
    out_dir = _as_path(project_dir)
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
        process_result = _run_process(_workbench_command(wbjn, batch=True), out_dir, timeout_seconds)
    except subprocess.TimeoutExpired:
        return _json({"ok": False, "error": f"Timed out after {timeout_seconds}s", "journal": str(wbjn)})

    marker_seen = _wait_for_log_marker(log_file, marker, min(timeout_seconds, 180))
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
    return _json(
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


if __name__ == "__main__":
    _ensure_dirs()
    mcp.run()

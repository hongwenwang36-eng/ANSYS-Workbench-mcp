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

import simulation_checks
import simulation_jobs

import hashlib
import json
import math
import os
import shlex
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


__version__ = "0.6.0"

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
    ".inp",
    ".dat",
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
    console_path = os.environ.get("ANSYS_MCP_JOB_CONSOLE")
    if console_path:
        import job_process
        result = job_process.run(args, cwd, timeout_seconds, env, console_path,
                                 os.environ["ANSYS_MCP_JOB_DIRECTORY"])
        return {**result, "stdout": _read_tail(Path(console_path)), "stderr": ""}
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        errors="replace",
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
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - limit * 4))
            return stream.read().decode("utf-8", errors="replace")[-limit:]
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

    Supported extensions are .inp, .dat, .wbjn, .py, .tcl, .rpl, .jou, .ccl, .pre, and
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
def start_ansys_job(tool: str, arguments: dict[str, Any], request_id: str = "") -> str:
    """Start a batch run and return a persistent job_id. Reuse a UUID request_id for retry safety."""
    return _json(simulation_jobs.submit(RUNS_DIR / "jobs", tool, arguments, request_id))


@mcp.tool()
def get_ansys_job(job_id: str) -> str:
    """Inspect a background job after reconnecting, including its latest console output."""
    path = simulation_jobs.job_path(RUNS_DIR / "jobs", job_id)
    return _json({**simulation_jobs.status(path), "console_tail": _read_tail(path / "console.log")})


@mcp.tool()
def stop_ansys_job(job_id: str) -> str:
    """Stop this background job and the local processes launched within its Windows job."""
    return _json(simulation_jobs.stop(simulation_jobs.job_path(RUNS_DIR / "jobs", job_id)))


@mcp.tool()
def diagnose_ansys_log(log_file: str) -> str:
    """Find recognized error messages, their lines and troubleshooting hints in a solver log."""
    return _json(simulation_checks.diagnose(_as_path(log_file)))


@mcp.tool()
def verify_simulation(csv_file: str, criteria: list[simulation_checks.MetricLimit]) -> str:
    """Check metric,unit,value CSV rows against inclusive limits in matching units."""
    return _json(simulation_checks.verify(_as_path(csv_file), criteria))


# A directly launched stdio server and imported solver workers share one runtime.
import sys
sys.modules.setdefault("mcp_server", sys.modules[__name__])
from ansys_mcp import api, batch_tools, icem_tools, workbench_tools

for module in (icem_tools, workbench_tools, batch_tools, api):
    for tool in module.TOOLS:
        globals()[tool.__name__] = mcp.tool()(tool)


if __name__ == "__main__":
    _ensure_dirs()
    mcp.run()

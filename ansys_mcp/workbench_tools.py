from __future__ import annotations
import os
import subprocess
import time
from typing import Any


def start_workbench_bridge(batch: bool = True, wait_seconds: int = 20) -> str:
    """Launch Workbench with the file-IPC bridge journal loaded.

    The bridge journal keeps Workbench alive and polls commands/*.json.
    Use stop_workbench_bridge to stop it.
    """
    import mcp_server as runtime
    if not runtime.RUNWB2.exists():
        return runtime._json({"ok": False, "error": f"RunWB2 not found: {runtime.RUNWB2}"})
    if not runtime.BRIDGE_JOURNAL.exists():
        return runtime._json({"ok": False, "error": f"Bridge journal not found: {runtime.BRIDGE_JOURNAL}"})

    status = runtime._read_status()
    if status.get("status") == "running":
        ping_result = runtime._send_command("ping", timeout=5.0)
        if ping_result.get("success"):
            return runtime._json({"ok": True, "already_running": True, "status": status, "ping": ping_result})

    runtime._ensure_dirs()
    try:
        if runtime.STOP_FILE.exists():
            runtime.STOP_FILE.unlink()
    except Exception:
        pass

    env = os.environ.copy()
    env["ANSYS_WORKBENCH_MCP_HOME"] = str(runtime.MCP_HOME)
    proc = subprocess.Popen(
        runtime._workbench_command(runtime.BRIDGE_JOURNAL, batch=batch),
        cwd=str(runtime.SERVER_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + max(1, int(wait_seconds))
    ping_result: dict[str, Any] = {}
    while time.time() < deadline:
        status = runtime._read_status()
        if status.get("status") == "running":
            ping_result = runtime._send_command("ping", timeout=5.0)
            if ping_result.get("success"):
                return runtime._json({"ok": True, "pid": proc.pid, "status": status, "ping": ping_result})
        time.sleep(0.5)

    return runtime._json({"ok": False, "pid": proc.pid, "status": runtime._read_status(), "detail": "Bridge did not answer before timeout"})


def stop_workbench_bridge(timeout_seconds: int = 10) -> str:
    """Signal the Workbench bridge loop to stop."""
    import mcp_server as runtime
    result = runtime._send_command("stop", timeout=min(float(timeout_seconds), 5.0))
    if not result.get("success"):
        try:
            runtime.STOP_FILE.write_text("stop", encoding="utf-8")
        except Exception:
            pass

    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        status = runtime._read_status()
        if status.get("status") in {"stopped", "ready"}:
            return runtime._json({"ok": True, "status": status, "command_result": result})
        time.sleep(0.25)

    return runtime._json({"ok": False, "status": runtime._read_status(), "command_result": result})


def check_workbench_connection() -> str:
    """Check whether the Workbench bridge journal is running and responding."""
    import mcp_server as runtime
    status = runtime._read_status()
    if not status:
        return "Workbench bridge status not found. Run start_workbench_bridge() or load ansys_workbench_bridge.wbjn in Workbench."

    if status.get("status") != "running":
        return f"Workbench bridge is not running: {runtime._json(status)}"

    result = runtime._send_command("ping", timeout=10.0)
    if result.get("success"):
        data = result.get("data", {})
        version = data.get("version", "?") if isinstance(data, dict) else "?"
        return f"Connected to Ansys Workbench bridge v{version}.\nStatus: {runtime._json(status)}"
    return f"Workbench bridge status exists but ping failed: {runtime._json(result)}"


def execute_workbench_script(script: str, timeout_seconds: int = 60) -> str:
    """Execute Python/Workbench journal code inside the running Workbench bridge."""
    import mcp_server as runtime
    result = runtime._send_command("execute_script", timeout=float(timeout_seconds), script=script)
    return runtime._format_bridge_result(result)


def get_project_info(timeout_seconds: int = 30) -> str:
    """Get project/system/component information from the running Workbench bridge."""
    import mcp_server as runtime
    result = runtime._send_command("get_project_info", timeout=float(timeout_seconds))
    return runtime._format_bridge_result(result)


def open_project(project_file: str, timeout_seconds: int = 120) -> str:
    """Open a Workbench project in the running Workbench bridge."""
    import mcp_server as runtime
    result = runtime._send_command("open_project", timeout=float(timeout_seconds), project_file=project_file)
    return runtime._format_bridge_result(result)


def save_project(project_file: str = "", overwrite: bool = True, timeout_seconds: int = 120) -> str:
    """Save the current Workbench project through the running bridge."""
    import mcp_server as runtime
    result = runtime._send_command(
        "save_project",
        timeout=float(timeout_seconds),
        project_file=project_file,
        overwrite=overwrite,
    )
    return runtime._format_bridge_result(result)


def update_project(timeout_seconds: int = 600) -> str:
    """Run Workbench Update() in the running bridge."""
    import mcp_server as runtime
    result = runtime._send_command("update_project", timeout=float(timeout_seconds))
    return runtime._format_bridge_result(result)


def probe_workbench_analysis_templates_live(timeout_seconds: int = 60) -> str:
    """Check Workbench template availability for the supported analysis wrappers."""
    import mcp_server as runtime
    result = runtime._send_command(
        "probe_analysis_templates",
        timeout=float(timeout_seconds),
        analysis_templates=runtime.WORKBENCH_ANALYSIS_TEMPLATES,
    )
    return runtime._format_bridge_result(result)


def probe_system_coupling_live(timeout_seconds: int = 60) -> str:
    """Verify the System Coupling template and its live Workbench scripting API."""
    import mcp_server as runtime
    result = runtime._send_command("probe_system_coupling", timeout=float(timeout_seconds))
    return runtime._format_bridge_result(result)


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
    import mcp_server as runtime
    result = runtime._send_command(
        "create_cfx_mechanical_fsi_project",
        timeout=float(timeout_seconds),
        project_dir=project_dir,
        project_name=project_name,
        cfx_geometry_file=cfx_geometry_file,
        mechanical_geometry_file=mechanical_geometry_file,
        overwrite=overwrite,
    )
    return runtime._format_bridge_result(result)


def connect_system_coupling_participants_live(
    system_indices: list[int],
    timeout_seconds: int = 120,
) -> str:
    """Connect existing Workbench systems to the current System Coupling Setup.

    Use get_project_info to obtain zero-based system indices. Do not include the
    System Coupling system itself.
    """
    import mcp_server as runtime
    result = runtime._send_command(
        "connect_system_coupling_participants",
        timeout=float(timeout_seconds),
        system_indices=system_indices,
    )
    return runtime._format_bridge_result(result)


def get_system_coupling_status_live(timeout_seconds: int = 60) -> str:
    """List System Coupling participants, regions, variables, transfers, and settings."""
    import mcp_server as runtime
    result = runtime._send_command("get_system_coupling_status", timeout=float(timeout_seconds))
    return runtime._format_bridge_result(result)


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
    import mcp_server as runtime
    result = runtime._send_command(
        "configure_system_coupling_settings",
        timeout=float(timeout_seconds),
        step_size=step_size,
        end_time=end_time,
        number_of_steps=number_of_steps,
        minimum_iterations=minimum_iterations,
        maximum_iterations=maximum_iterations,
    )
    return runtime._format_bridge_result(result)


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
    import mcp_server as runtime
    result = runtime._send_command(
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
    return runtime._format_bridge_result(result)


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
    import mcp_server as runtime
    result = runtime._send_command(
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
    return runtime._format_bridge_result(result)


def export_system_coupling_setup_live(output_path: str, timeout_seconds: int = 180) -> str:
    """Export the current System Coupling setup to an `.sci` file."""
    import mcp_server as runtime
    result = runtime._send_command(
        "export_system_coupling_setup",
        timeout=float(timeout_seconds),
        output_path=output_path,
    )
    return runtime._format_bridge_result(result)


def run_system_coupling_solution_live(timeout_seconds: int = 3600) -> str:
    """Update the System Coupling Solution cell and wait for the coupled run.

    The participant setups and all required transfers must already validate.
    """
    import mcp_server as runtime
    result = runtime._send_command("run_system_coupling_solution", timeout=float(timeout_seconds))
    return runtime._format_bridge_result(result)


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
    import mcp_server as runtime
    try:
        candidates = runtime._analysis_candidates(analysis_type, template_name, solver)
    except ValueError as exc:
        return runtime._json({"ok": False, "error": str(exc)})
    result = runtime._send_command(
        "create_analysis_system",
        timeout=float(timeout_seconds),
        analysis_type=runtime._analysis_key(analysis_type),
        project_dir=project_dir,
        project_name=project_name or runtime._default_project_name(analysis_type),
        geometry_file=geometry_file,
        refresh_model=refresh_model,
        reset_project=reset_project,
        template_candidates=candidates,
    )
    return runtime._format_bridge_result(result)


def create_steady_state_thermal_system_live(
    project_dir: str,
    project_name: str = "steady_state_thermal",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Steady-State Thermal system in the running Workbench bridge."""
    import mcp_server as runtime
    result = runtime._send_command(
        "create_steady_state_thermal_system",
        timeout=float(timeout_seconds),
        project_dir=project_dir,
        project_name=project_name,
        geometry_file=geometry_file,
        refresh_model=refresh_model,
    )
    return runtime._format_bridge_result(result)


def create_transient_thermal_system_live(
    project_dir: str,
    project_name: str = "transient_thermal",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Transient Thermal system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "transient_thermal",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_static_structural_system_live(
    project_dir: str,
    project_name: str = "static_structural",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Static Structural system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "static_structural",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_transient_structural_system_live(
    project_dir: str,
    project_name: str = "transient_structural",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Transient Structural dynamics system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "transient_structural",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_modal_analysis_system_live(
    project_dir: str,
    project_name: str = "modal_analysis",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Modal dynamics system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "modal",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_harmonic_response_system_live(
    project_dir: str,
    project_name: str = "harmonic_response",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Harmonic Response dynamics system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "harmonic_response",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_response_spectrum_system_live(
    project_dir: str,
    project_name: str = "response_spectrum",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Response Spectrum dynamics system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "response_spectrum",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_random_vibration_system_live(
    project_dir: str,
    project_name: str = "random_vibration",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Random Vibration dynamics system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "random_vibration",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_cfx_flow_system_live(
    project_dir: str,
    project_name: str = "cfx_flow",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Create a Fluid Flow (CFX) system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "cfx",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_fluent_flow_system_live(
    project_dir: str,
    project_name: str = "fluent_flow",
    geometry_file: str = "",
    refresh_model: bool = False,
    timeout_seconds: int = 180,
) -> str:
    """Try to create a Fluid Flow (Fluent) system in the running Workbench bridge."""
    import mcp_server as runtime
    return runtime.create_workbench_analysis_system_live(
        "fluent",
        project_dir,
        project_name,
        geometry_file,
        refresh_model,
        True,
        timeout_seconds=timeout_seconds,
    )


def create_thermal_bar_demo_live(
    project_dir: str = r"D:\ansys-workbench-mcp\runs\thermal_bar_demo_live",
    timeout_seconds: int = 600,
) -> str:
    """Create and solve a simple thermal bar demo through the running Workbench bridge."""
    import mcp_server as runtime
    result = runtime._send_command("create_thermal_bar_demo", timeout=float(timeout_seconds), project_dir=project_dir)
    return runtime._format_bridge_result(result)


TOOLS = (
    start_workbench_bridge,
    stop_workbench_bridge,
    check_workbench_connection,
    execute_workbench_script,
    get_project_info,
    open_project,
    save_project,
    update_project,
    probe_workbench_analysis_templates_live,
    probe_system_coupling_live,
    create_cfx_mechanical_fsi_project_live,
    connect_system_coupling_participants_live,
    get_system_coupling_status_live,
    configure_system_coupling_settings_live,
    create_system_coupling_data_transfer_live,
    configure_cfx_mechanical_two_way_fsi_live,
    export_system_coupling_setup_live,
    run_system_coupling_solution_live,
    create_workbench_analysis_system_live,
    create_steady_state_thermal_system_live,
    create_transient_thermal_system_live,
    create_static_structural_system_live,
    create_transient_structural_system_live,
    create_modal_analysis_system_live,
    create_harmonic_response_system_live,
    create_response_spectrum_system_live,
    create_random_vibration_system_live,
    create_cfx_flow_system_live,
    create_fluent_flow_system_live,
    create_thermal_bar_demo_live,
)

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import mcp_server  # noqa: E402


class IcemSupportTests(unittest.TestCase):
    def test_tcl_quote_blocks_substitution_and_normalizes_paths(self) -> None:
        quoted = mcp_server._tcl_quote(r"D:\work\$case\[mesh].tin")
        self.assertEqual(quoted, '"D:/work/\\$case/\\[mesh\\].tin"')

    def test_icem_command_uses_cmd_call_for_batch_launcher(self) -> None:
        command = mcp_server._icem_command(["-batch", "-script", "D:\\work\\bridge.tcl"])
        self.assertIsInstance(command, str)
        self.assertIn(" /d /v:off /c call ", command)
        self.assertIn("icemcfd.bat", command)
        self.assertIn('"-batch"', command)
        self.assertIn('"-script"', command)

    def test_icem_command_quotes_cmd_metacharacters(self) -> None:
        command = mcp_server._icem_command(["D:\\cases\\mesh&quality.rpl"])
        self.assertIn('"D:\\cases\\mesh&quality.rpl"', command)

    def test_icem_environment_prioritizes_ansys_runtime_dlls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ansys_root = Path(temp_dir) / "v251"
            launcher = ansys_root / "icemcfd" / "win64_amd" / "bin" / "icemcfd.bat"
            aisol_bin = ansys_root / "aisol" / "bin" / "winx64"
            framework_bin = ansys_root / "Framework" / "bin" / "Win64"
            launcher.parent.mkdir(parents=True)
            aisol_bin.mkdir(parents=True)
            framework_bin.mkdir(parents=True)
            launcher.touch()

            with mock.patch.multiple(
                mcp_server,
                ICEM_CFD=launcher,
                ICEM_HOME=ansys_root / "icem-mcp",
            ):
                with mock.patch.dict(os.environ, {"PATH": r"C:\polluted\runtime"}):
                    env = mcp_server._icem_environment(batch=True)

            path_entries = env["PATH"].split(os.pathsep)
            self.assertEqual(path_entries[:2], [str(aisol_bin), str(framework_bin)])
            self.assertEqual(env["ANSYS_ICEM_MCP_HOME"], str(ansys_root / "icem-mcp"))
            self.assertEqual(env["ICEM_MCP_BATCH"], "1")

    def test_send_icem_command_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            icem_home = Path(temp_dir)
            commands = icem_home / "commands"
            results = icem_home / "results"
            scripts = icem_home / "scripts"
            status = icem_home / "status.json"
            log = icem_home / "icem_bridge.log"

            with mock.patch.multiple(
                mcp_server,
                ICEM_HOME=icem_home,
                ICEM_COMMANDS_DIR=commands,
                ICEM_RESULTS_DIR=results,
                ICEM_SCRIPTS_DIR=scripts,
                ICEM_STATUS_FILE=status,
                ICEM_LOG_FILE=log,
            ):
                mcp_server._ensure_dirs()

                def fake_bridge() -> None:
                    deadline = time.time() + 2
                    descriptor = None
                    while time.time() < deadline:
                        matches = list(commands.glob("cmd_*.tcl"))
                        if matches:
                            descriptor = matches[0]
                            break
                        time.sleep(0.01)
                    if descriptor is None:
                        return
                    command_id = descriptor.stem.removeprefix("cmd_")
                    result_path = results / f"{command_id}.json"
                    result_path.write_text(
                        json.dumps(
                            {
                                "success": True,
                                "id": command_id,
                                "elapsed_seconds": 0,
                                "result": "pong",
                                "error": "",
                                "traceback": "",
                            }
                        ),
                        encoding="utf-8",
                    )

                bridge_thread = threading.Thread(target=fake_bridge)
                bridge_thread.start()
                result = mcp_server._send_icem_command("ping", timeout=2)
                bridge_thread.join(timeout=2)

                self.assertTrue(result["success"])
                self.assertEqual(result["result"], "pong")

    def test_installation_report_includes_icem(self) -> None:
        report = json.loads(mcp_server.check_ansys_installation())
        self.assertIn("icem_cfd", report)
        self.assertIn("icem_bridge_script", report)
        self.assertEqual(report["version"], "0.5.0")

    def test_documented_bridge_tools_are_defined(self) -> None:
        expected_tools = {
            "check_ansys_installation",
            "write_ansys_script",
            "check_icem_installation",
            "start_icem_bridge",
            "stop_icem_bridge",
            "check_icem_connection",
            "execute_icem_script",
            "get_icem_session_info",
            "list_icem_commands",
            "run_icem_replay",
            "start_workbench_bridge",
            "stop_workbench_bridge",
            "check_workbench_connection",
            "execute_workbench_script",
            "get_project_info",
            "open_project",
            "save_project",
            "update_project",
            "probe_workbench_analysis_templates_live",
            "probe_system_coupling_live",
            "create_cfx_mechanical_fsi_project_live",
            "connect_system_coupling_participants_live",
            "get_system_coupling_status_live",
            "configure_system_coupling_settings_live",
            "create_system_coupling_data_transfer_live",
            "configure_cfx_mechanical_two_way_fsi_live",
            "export_system_coupling_setup_live",
            "run_system_coupling_solution_live",
            "create_workbench_analysis_system_live",
            "create_steady_state_thermal_system_live",
            "create_transient_thermal_system_live",
            "create_static_structural_system_live",
            "create_transient_structural_system_live",
            "create_modal_analysis_system_live",
            "create_harmonic_response_system_live",
            "create_response_spectrum_system_live",
            "create_random_vibration_system_live",
            "create_cfx_flow_system_live",
            "create_fluent_flow_system_live",
            "create_thermal_bar_demo_live",
            "run_spaceclaim_script",
            "run_cfx_pre_session",
            "run_cfx_post_session",
            "run_workbench_journal",
            "create_workbench_analysis_system",
            "create_steady_state_thermal_system",
            "run_mapdl_input",
            "run_fluent_journal",
            "run_cfx_solver",
            "create_and_run_thermal_bar_demo",
        }
        registered_tools = set(mcp_server.mcp._tool_manager._tools)
        self.assertEqual(registered_tools, expected_tools)
        for tool_name in expected_tools:
            with self.subTest(tool_name=tool_name):
                self.assertTrue(callable(getattr(mcp_server, tool_name, None)))

    def test_documented_resources_are_registered(self) -> None:
        self.assertEqual(
            set(mcp_server.mcp._resource_manager._resources),
            {
                "ansys-workbench://status",
                "ansys-workbench://installation",
                "ansys-workbench://icem/status",
            },
        )

    def test_readme_tool_table_matches_registered_tools(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        tool_section = readme.split("## MCP 工具", 1)[1].split("## MCP 资源", 1)[0]
        documented_tools = set(re.findall(r"^\| `([^`]+)` \|", tool_section, re.MULTILINE))
        self.assertEqual(documented_tools, set(mcp_server.mcp._tool_manager._tools))

    def test_bridge_and_server_versions_match(self) -> None:
        bridge = (REPO_ROOT / "ansys_workbench_bridge.wbjn").read_text(encoding="utf-8")
        version_match = re.search(r'^__version__ = "([^"]+)"$', bridge, re.MULTILINE)
        self.assertIsNotNone(version_match)
        self.assertEqual(version_match.group(1), mcp_server.__version__)

    def test_system_coupling_template_and_bridge_commands_are_present(self) -> None:
        self.assertEqual(
            mcp_server.WORKBENCH_ANALYSIS_TEMPLATES["system_coupling"],
            [{"template_name": "System Coupling", "solver": ""}],
        )
        bridge = (REPO_ROOT / "ansys_workbench_bridge.wbjn").read_text(encoding="utf-8")
        for command in [
            "probe_system_coupling",
            "create_cfx_mechanical_fsi_project",
            "connect_system_coupling_participants",
            "get_system_coupling_status",
            "configure_system_coupling_settings",
            "create_system_coupling_data_transfer",
            "configure_cfx_mechanical_two_way_fsi",
            "export_system_coupling_setup",
            "run_system_coupling_solution",
        ]:
            with self.subTest(command=command):
                self.assertIn('cmd_type == "' + command + '"', bridge)


if __name__ == "__main__":
    unittest.main()

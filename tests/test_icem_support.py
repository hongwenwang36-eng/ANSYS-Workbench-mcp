from __future__ import annotations

import json
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
        self.assertEqual(report["version"], "0.3.0")


if __name__ == "__main__":
    unittest.main()

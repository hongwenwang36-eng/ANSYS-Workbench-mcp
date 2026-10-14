from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import mcp_server  # noqa: E402


SUCCESS_PROCESS = {
    "returncode": 0,
    "elapsed_seconds": 0.1,
    "stdout": "",
    "stderr": "",
}


class CfxPipelineSupportTests(unittest.TestCase):
    def test_installation_report_includes_geometry_and_post_tools(self) -> None:
        report = json.loads(mcp_server.check_ansys_installation())
        self.assertIn("spaceclaim", report)
        self.assertIn("spaceclaim_exists", report)
        self.assertIn("cfx_post", report)
        self.assertIn("cfx_post_exists", report)

    def test_write_ansys_script_is_atomic_and_refuses_implicit_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "iterate.wbjn"
            first = json.loads(mcp_server.write_ansys_script(str(path), "print('first')\n"))
            self.assertTrue(first["ok"])
            self.assertEqual(path.read_text(encoding="utf-8"), "print('first')\n")
            self.assertEqual(len(first["sha256"]), 64)

            refused = json.loads(mcp_server.write_ansys_script(str(path), "print('second')\n"))
            self.assertFalse(refused["ok"])
            self.assertIn("overwrite=True", refused["error"])
            self.assertEqual(path.read_text(encoding="utf-8"), "print('first')\n")

            replaced = json.loads(
                mcp_server.write_ansys_script(str(path), "print('second')\n", overwrite=True)
            )
            self.assertTrue(replaced["ok"])
            self.assertEqual(path.read_text(encoding="utf-8"), "print('second')\n")

            unsupported = json.loads(
                mcp_server.write_ansys_script(str(Path(temp_dir) / "unsafe.exe"), "payload")
            )
            self.assertFalse(unsupported["ok"])

    def test_run_spaceclaim_script_builds_headless_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "SpaceClaim.exe"
            script = root / "geometry.py"
            executable.touch()
            script.write_text("print('geometry')\n", encoding="utf-8")

            with mock.patch.multiple(mcp_server, SPACECLAIM=executable):
                with mock.patch.object(mcp_server, "_run_process", return_value=SUCCESS_PROCESS) as run:
                    payload = json.loads(mcp_server.run_spaceclaim_script(str(script)))

            self.assertTrue(payload["ok"])
            command = run.call_args.args[0]
            self.assertEqual(command[0], str(executable))
            self.assertIn("/Headless=True", command)
            self.assertIn(f"/RunScript={script}", command)
            self.assertIn("/ExitAfterScript=True", command)

    def test_run_cfx_pre_session_uses_batch_and_expected_output_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "cfx5pre.exe"
            session = root / "setup.pre"
            expected = root / "case.def"
            executable.touch()
            session.write_text("COMMAND FILE:\nEND\n", encoding="utf-8")

            with mock.patch.multiple(mcp_server, CFX_PRE=executable):
                with mock.patch.object(mcp_server, "_run_process", return_value=SUCCESS_PROCESS):
                    missing = json.loads(
                        mcp_server.run_cfx_pre_session(
                            str(session), expected_output=str(expected)
                        )
                    )
                expected.write_text("old", encoding="utf-8")

                def update_expected(*args, **kwargs):
                    expected.write_text("new definition", encoding="utf-8")
                    return SUCCESS_PROCESS

                with mock.patch.object(mcp_server, "_run_process", side_effect=update_expected) as run:
                    present = json.loads(
                        mcp_server.run_cfx_pre_session(
                            str(session), expected_output=str(expected)
                        )
                    )

            self.assertFalse(missing["ok"])
            self.assertTrue(present["ok"])
            command = run.call_args.args[0]
            self.assertEqual(command[:3], [str(executable), "-batch", str(session)])

    def test_run_cfx_post_session_supports_software_and_gpu_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "cfx5post.exe"
            session = root / "export.cse"
            result = root / "case.res"
            executable.touch()
            session.write_text("COMMAND FILE:\nEND\n", encoding="utf-8")
            result.touch()

            with mock.patch.multiple(mcp_server, CFX_POST=executable):
                with mock.patch.object(mcp_server, "_run_process", return_value=SUCCESS_PROCESS) as run:
                    software = json.loads(
                        mcp_server.run_cfx_post_session(
                            str(session), result_file=str(result), rendering="software"
                        )
                    )
                    software_command = run.call_args.args[0]
                    gpu = json.loads(
                        mcp_server.run_cfx_post_session(str(session), rendering="gpu")
                    )
                    gpu_command = run.call_args.args[0]

            self.assertTrue(software["ok"])
            self.assertIn("-results", software_command)
            self.assertIn("-batch-software-rendering", software_command)
            self.assertTrue(gpu["ok"])
            self.assertIn("-batch-gpu-rendering", gpu_command)

    def test_run_workbench_journal_can_require_marker_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "RunWB2.exe"
            journal = root / "iterate.wbjn"
            log = root / "iterate.log"
            artifact = root / "converged.wbpj"
            executable.touch()
            journal.write_text("# workbench journal\n", encoding="utf-8")
            log.write_text("old log\n", encoding="utf-8")
            artifact.write_text("old project", encoding="utf-8")

            def update_iteration_outputs(*args, **kwargs):
                log.write_text("ITERATION_CONVERGED\n", encoding="utf-8")
                artifact.write_text("new converged project", encoding="utf-8")
                return SUCCESS_PROCESS

            with mock.patch.multiple(mcp_server, RUNWB2=executable):
                with mock.patch.object(
                    mcp_server, "_run_process", side_effect=update_iteration_outputs
                ):
                    payload = json.loads(
                        mcp_server.run_workbench_journal(
                            str(journal),
                            log_file=str(log),
                            completion_marker="ITERATION_CONVERGED",
                            expected_output=str(artifact),
                        )
                    )

            self.assertTrue(payload["ok"])
            self.assertTrue(payload["marker_seen"])
            self.assertTrue(payload["log_updated"])
            self.assertTrue(payload["expected_output"]["exists"])
            self.assertTrue(payload["expected_output"]["updated"])
            self.assertEqual(payload["returncode"], 0)


if __name__ == "__main__":
    unittest.main()

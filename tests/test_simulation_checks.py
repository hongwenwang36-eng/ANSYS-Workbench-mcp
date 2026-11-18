import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mcp_server
from simulation_checks import MetricLimit, diagnose, verify


class EvidenceTests(unittest.TestCase):
    def test_missing_nonfinite_duplicate_and_wrong_units_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "values.csv"
            rule = [MetricLimit(metric="force", unit="N", minimum=99, maximum=101)]
            for body in ["other,N,100", "force,N,nan", "force,kN,100", "force,N,102"]:
                path.write_text("metric,unit,value\n" + body)
                self.assertFalse(verify(path, rule)["ok"])
            path.write_text("metric,unit,value\nforce,N,100\nforce,N,100\n")
            with self.assertRaises(ValueError):
                verify(path, rule)
            path.write_text("metric,unit,value\nforce,N,100\n")
            self.assertTrue(verify(path, rule)["ok"])
            with self.assertRaises(ValueError):
                verify(path, [])

    def test_diagnostic_points_to_error_not_success_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "solver.out"
            path.write_text("NUMBER OF ERROR MESSAGES ENCOUNTERED= 0\n"
                            "*** ERROR ***\nnegative cell volume\n")
            result = diagnose(path)
            self.assertEqual([x["line"] for x in result["findings"]], [2, 3])

    def test_zero_byte_output_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            executable = path / "pre.exe"
            session = path / "case.pre"
            output = path / "case.def"
            executable.touch()
            session.write_text("session")
            def run(*args):
                output.touch()
                return {"returncode": 0, "stdout": "", "stderr": ""}
            with patch.object(mcp_server, "CFX_PRE", executable), patch.object(mcp_server, "_run_process", run):
                result = json.loads(mcp_server.run_cfx_pre_session(
                    str(session), expected_output=str(output)))
            self.assertFalse(result["ok"])

    def test_mapdl_input_extension(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.inp"
            result = json.loads(mcp_server.write_ansys_script(str(path), "/exit,nosave\n"))
            self.assertTrue(result["ok"])
            self.assertEqual(path.read_text(), "/exit,nosave\n")


if __name__ == "__main__":
    unittest.main()

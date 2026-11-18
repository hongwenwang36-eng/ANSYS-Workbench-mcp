import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mcp_server


class AnsysMeshingTests(unittest.TestCase):
    def test_invalid_size_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            geometry = Path(folder) / "bar.scdocx"
            geometry.touch()
            with patch.object(mcp_server, "run_workbench_journal") as launch:
                for invalid in (0, -1, float("nan"), float("inf")):
                    result = json.loads(mcp_server.generate_ansys_mesh(
                        str(geometry), folder, element_size_mm=invalid))
                    self.assertFalse(result["ok"])
                launch.assert_not_called()

    def test_missing_mesh_export_prevents_success(self):
        with tempfile.TemporaryDirectory() as folder:
            geometry = Path(folder) / "bar.scdocx"
            geometry.touch()

            def journal_runner(journal, workdir, **kwargs):
                directory = Path(workdir)
                (directory / "meshing_files").mkdir()
                return '{"ok": true}'

            with patch.object(mcp_server, "run_workbench_journal", journal_runner):
                result = json.loads(mcp_server.generate_ansys_mesh(str(geometry), folder))
            self.assertFalse(result["ok"])
            self.assertFalse(result["reopened"])
            self.assertTrue(Path(result["journal"]).is_file())

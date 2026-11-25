from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ansys_mcp import models, verification, workflows
from ansys_mcp.rag import store
from ansys_mcp.rag.documents import Source

ROOT = Path(__file__).resolve().parents[1]


class EngineeringTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)

    def test_import_search_replace_and_failed_rebuild(self):
        source = self.root / "两相.html"
        source.write_text("<p>cavitation 饱和蒸气压 VAPOR_TEST</p>", encoding="utf-8")
        cfg = Source(
            path=str(source),
            module="fluids",
            version="251",
            software="Fluent",
            kind="command",
        )
        db = self.root / "index.sqlite"
        with patch.object(store, "default_sources", return_value=[]):
            gen = store.update(db, ROOT, [cfg])["generation"]
            hits = store.search(
                db, ROOT, "饱和蒸气压", "command", "fluids", "251", software="fluent"
            )["hits"]
            self.assertEqual(len(hits), 1)
            doc = store.get_document(db, ROOT, hits[0]["document_id"])["chunks"][0]
            self.assertIn("VAPOR_TEST", doc["text"])
            self.assertEqual(doc["lines"], [1, 1])
            self.assertFalse(
                store.search(db, ROOT, "VAPOR_TEST", version="252")["hits"]
            )
            source.unlink()
            with self.assertRaises(FileNotFoundError):
                store.update(db, ROOT)
            self.assertEqual(store.search(db, ROOT, "cavitation")["generation"], gen)
            cfg2 = self.root / "second.txt"
            cfg2.write_text("mode frequency vibration")
            store.update(db, ROOT, [Source(path=str(cfg2))], replace_sources=True)
            with self.assertRaises(ValueError):
                store.get_document(db, ROOT, hits[0]["document_id"])

    def test_native_snapshot_integrity(self):
        p = self.root / "beam.wbpj"
        p.write_text("project")
        parts = self.root / "beam_files"
        parts.mkdir()
        (parts / "data").write_text("payload")
        snap = self.root / "snapshot"
        models.snapshot(p, snap)
        restored = Path(models.restore(snap, self.root / "restored")["project"])
        self.assertEqual(restored.read_text(), "project")
        (snap / "beam_files" / "data").write_text("changed")
        with self.assertRaises(ValueError):
            models.restore(snap, self.root / "bad")
        self.assertFalse((self.root / "bad").exists())

    def test_audit_thermal_global_initial_condition_and_conflict(self):
        a = {
            "name": "Temp",
            "type": "Temperature",
            "scope_ids": [7],
            "magnitude": ["20 [C]"],
        }
        objs = [a, {"name": "initial", "type": "InitialCondition", "scope_ids": []}]
        s = {
            "kind": "workbench",
            "systems": ["SYS"],
            "mechanical": {
                "elements": 1,
                "analyses": [{"objects": objs}],
                "bodies": [
                    {"id": 1, "suppressed": False, "material": "Steel", "face_ids": [7]}
                ],
            },
        }
        self.assertTrue(models.audit(s)["passed"])
        objs.append({**a, "magnitude": ["100 [C]"]})
        self.assertFalse(models.audit(s)["passed"])

    def test_failed_physical_check_and_refinement(self):
        p = self.root / "audit.csv"
        p.write_text("metric,unit,value\nhot,W,4\ncold,W,-3\n")
        rule = verification.Equation(
            name="heat", unit="W", terms={"hot": 1, "cold": 1}, atol=0.1
        )
        self.assertFalse(verification.equations(p, [rule])["ok"])
        p.write_text(
            "metric,unit,value,spacing\nmode,Hz,10,1\nmode,Hz,11,0.5\nmode,Hz,11.01,0.25\n"
        )
        self.assertTrue(verification.refinement(p, "mode", "Hz", 0.001)["ok"])
        self.assertFalse(verification.refinement(p, "mode", "Hz", 0.0001)["ok"])

    def test_workflow_retry_and_dependency_gating(self):
        stages = [
            workflows.Step(
                name="mesh",
                tool="run_workbench_journal",
                arguments={"journal_path": "x.wbjn"},
                repairs=[{"category": "artifact", "arguments": {}}],
                outputs=["mesh.dat"],
            ),
            workflows.Step(
                name="analysis",
                tool="run_mapdl_input",
                arguments={"input_file": "mesh.dat"},
                depends_on=["mesh"],
                inputs={"mesh.dat": "@mesh/mesh.dat"},
                outputs=["out.csv"],
            ),
        ]

        def submit(root, tool, args, jid):
            wd = Path(args["workdir"])
            if wd.name == "2":
                (wd / "mesh.dat").write_text("accepted mesh")
            if tool == "run_mapdl_input":
                self.assertEqual((wd / "mesh.dat").read_text(), "accepted mesh")
                (wd / "out.csv").write_text("result")
            return {
                "state": "finished",
                "result": {"ok": True},
                "directory": str(root / jid),
            }

        state = workflows.create(self.root, stages, launch=False)
        folder = self.root / state["id"]
        with patch.object(workflows.jobs, "submit", side_effect=submit):
            first = workflows.advance(folder)
            self.assertEqual(
                first["steps"][0]["attempts"][0]["diagnostics"], ["artifact"]
            )
            self.assertFalse(first["steps"][1]["attempts"])
            self.assertEqual(workflows.advance(folder)["state"], "finished")
            self.assertEqual(workflows.advance(folder)["state"], "finished")
        self.assertNotEqual(stages[0].name, stages[1].name)

    def test_attempt_artifact_cannot_target_drive_root(self):
        for name in ("/mesh.dat", "../mesh.dat", "C:/mesh.dat", "mesh.dat:stream"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                workflows.relative(name)

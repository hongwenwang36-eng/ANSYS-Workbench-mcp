"""Exercise worker restart, idempotency and cancellation without an ANSYS license."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

import simulation_jobs as jobs


@unittest.skipUnless(os.name == "nt", "Windows process-tree jobs")
class BackgroundTests(unittest.TestCase):
    def wait_terminal(self, path):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = jobs.status(path)
            if state["state"] not in {"starting", "running", "stopping"}:
                return state
            time.sleep(0.1)
        self.fail("worker did not finish")

    def test_restart_and_duplicate_submission(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            request_id = str(uuid.uuid4())
            args = {"input_file": str(root / "missing.inp")}
            first = jobs.submit(root, "run_mapdl_input", args, request_id)
            second = jobs.submit(root, "run_mapdl_input", args, request_id)
            self.assertEqual(first["job_id"], second["job_id"])
            with self.assertRaises(ValueError):
                jobs.submit(root, "run_mapdl_input", {"input_file": "different.inp"}, request_id)
            path = jobs.job_path(root, first["job_id"])
            result = self.wait_terminal(path)
            self.assertEqual(result["state"], "failed")
            code = "import json,simulation_jobs as j;from pathlib import Path;print(json.dumps(j.status(Path(%r))))" % str(path)
            readback = subprocess.check_output([sys.executable, "-c", code], text=True)
            self.assertEqual(json.loads(readback)["state"], "failed")

    def test_cancel_process_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            import ctypes
            executable = ctypes.create_unicode_buffer(32768)
            ctypes.windll.kernel32.GetModuleFileNameW(None, executable, len(executable))
            native_python = executable.value
            marker = root / "child-survived"
            script = root / "fake.py"
            script.write_text("import subprocess,sys,time\nfrom pathlib import Path\n"
                              f"child=subprocess.Popen([{native_python!r},'-c',"
                              + repr("import time;from pathlib import Path;time.sleep(30);Path(%r).touch()" % str(marker))
                              + "])\n" + f"Path({str(root / 'ready')!r}).write_text(str(child.pid))\n" + "time.sleep(30)\n")
            path = root / uuid.uuid4().hex
            path.mkdir()
            helper = root / "worker.py"
            helper.write_text("import win32job,win32api,subprocess,sys,time\n"
                "import simulation_jobs as j,job_process\nfrom pathlib import Path\n"
                f"p=Path({str(path)!r})\n"
                "h=win32job.CreateJobObject(None,j.object_name(p))\n"
                "win32job.AssignProcessToJobObject(h,win32api.GetCurrentProcess())\n"
                "(p/'started').touch()\n"
                f"job_process.run([{native_python!r},{str(script)!r}],p,30,None,str(p/'console.log'),str(p))\n")
            env = dict(os.environ, PYTHONPATH=str(Path(jobs.__file__).parent))
            proc = subprocess.Popen([sys.executable, str(helper)], env=env,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 10
                while not (root / "ready").exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertTrue((root / "ready").exists())
                import win32api
                import win32event
                child_handle = win32api.OpenProcess(0x00100000, False, int((root / "ready").read_text()))
                jobs.stop(path)
                proc.wait(timeout=10)
                self.assertEqual(win32event.WaitForSingleObject(child_handle, 10000), 0)
                child_handle.Close()
                self.assertEqual(jobs.status(path)["state"], "stopped")
                self.assertFalse(marker.exists())
            finally:
                if proc.poll() is None:
                    jobs.stop(path)
                    proc.wait(timeout=10)

"""Run a Windows process attached to the worker's job before its first instruction."""
import msvcrt
import os
from pathlib import Path
import subprocess
import time

import win32api
import win32con
import win32event
import win32job
import win32process

import simulation_jobs


def run(args, cwd, timeout, env, console_path, directory):
    started = time.time()
    job = simulation_jobs.open_job(Path(directory), win32job.JOB_OBJECT_ASSIGN_PROCESS)
    if job is None:
        raise RuntimeError("Background process job has disappeared")
    with open(console_path, "ab", buffering=0) as output, open(os.devnull, "rb") as input_stream:
        out_handle = msvcrt.get_osfhandle(output.fileno())
        in_handle = msvcrt.get_osfhandle(input_stream.fileno())
        os.set_handle_inheritable(out_handle, True)
        os.set_handle_inheritable(in_handle, True)
        startup = win32process.STARTUPINFO()
        startup.dwFlags = win32con.STARTF_USESTDHANDLES
        startup.hStdOutput = out_handle
        startup.hStdError = out_handle
        startup.hStdInput = in_handle
        command = args if isinstance(args, str) else subprocess.list2cmdline(args)
        process, thread, pid, tid = win32process.CreateProcess(
            None, command, None, None, True,
            win32con.CREATE_SUSPENDED | win32con.CREATE_NO_WINDOW,
            env, str(cwd), startup)
        try:
            win32job.AssignProcessToJobObject(job, process)
            win32process.ResumeThread(thread)
            if win32event.WaitForSingleObject(process, int(timeout * 1000)) == win32con.WAIT_TIMEOUT:
                raise subprocess.TimeoutExpired(args, timeout)
            return {"returncode": win32process.GetExitCodeProcess(process),
                    "elapsed_seconds": round(time.time() - started, 3)}
        except Exception:
            win32api.TerminateProcess(process, 1)
            raise
        finally:
            thread.Close()
            process.Close()

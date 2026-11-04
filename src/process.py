"""Cooperative job cancellation with bounded child-process cleanup."""
import os
import subprocess
import sys
import time
from pathlib import Path
from process_group import popen


def stop_tree(child):
    if child.poll() is not None:return
    try:
        subprocess.run(["taskkill","/PID",str(child.pid),"/T","/F"],capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW,timeout=5)
    except subprocess.TimeoutExpired:child.kill()
    child.wait(timeout=5)


def run(command, **kwargs):
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    marker = os.environ.get("ARRANGER_CANCEL_FILE")
    if not marker and os.name!="nt":
        return subprocess.run(command, **kwargs)
    check = kwargs.pop("check", False)
    timeout = kwargs.pop("timeout", None)
    if kwargs.pop("capture_output",False):
        if "stdout" in kwargs or "stderr" in kwargs:
            raise ValueError("capture_output cannot be combined with stdout/stderr")
        kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if marker and Path(marker).exists():
        raise ValueError("Render canceled")
    with popen(command, **kwargs) as child:
        if marker:print(f"child_started {child.pid}", file=sys.stderr, flush=True)
        started = time.monotonic()
        try:
            while True:
                if marker and Path(marker).exists():raise ValueError("Render canceled")
                try:
                    stdout, stderr = child.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    if timeout is not None and time.monotonic() - started >= timeout:
                        raise subprocess.TimeoutExpired(command, timeout)
        except BaseException:
            stop_tree(child)
            raise
        result = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result

"""Exercise cancellation after a resolved source launches a real encoder."""
import ctypes
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import wave
import json
import time

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt" and shutil.which("ffmpeg"), "Windows/FFmpeg required")
class CancellationTests(unittest.TestCase):
    def test_owned_child_kill_releases_native_helpers_while_owner_lives(self):
        sys.path.insert(0,str(ROOT/"src"))
        from process_group import popen
        fixture=Path(os.environ["LOCALAPPDATA"],"SampleArranger/tools/arranger-native/arranger-lifecycle-fixture.exe")
        if not fixture.is_file():self.skipTest("build lifecycle fixture")
        with tempfile.TemporaryDirectory() as directory:
            pids=Path(directory)/"pids.json"
            with popen([str(fixture),str(pids)]) as child:
                deadline=time.monotonic()+5
                while not pids.exists() and time.monotonic()<deadline:time.sleep(0.02)
                kernel=ctypes.WinDLL("kernel32",use_last_error=True)
                kernel.OpenProcess.restype=ctypes.c_void_p;kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
                grandchild=kernel.OpenProcess(0x100000,False,json.loads(pids.read_text())[1])
                self.assertTrue(grandchild)
                try:
                    self.assertEqual(kernel.WaitForSingleObject(grandchild,0),258)
                    child.kill();child.wait(timeout=5)
                    self.assertEqual(kernel.WaitForSingleObject(grandchild,5000),0)
                finally:kernel.CloseHandle(grandchild)
    def test_native_descendants_on_abrupt_owner_exit(self):
        fixture=Path(os.environ["LOCALAPPDATA"],"SampleArranger/tools/arranger-native/arranger-lifecycle-fixture.exe")
        if not fixture.is_file():self.skipTest("build lifecycle fixture")
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pids=root/"pids.json";crash=root/"crash"
            owner="import sys,os,time,subprocess,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from process_group import own_process_tree,diagnostic,popen; own_process_tree(); child=popen([sys.argv[2],sys.argv[3]]); flag=Path(sys.argv[4]); exec('while not flag.exists(): time.sleep(0.02)'); Path(sys.argv[3]+'.debug').write_text(json.dumps(diagnostic(json.loads(Path(sys.argv[3]).read_text())))); os._exit(17)"
            with subprocess.Popen([sys.executable,"-c",owner,str(ROOT/"src"),str(fixture),str(pids),str(crash)]) as process:
                handles=[];kernel=ctypes.WinDLL("kernel32",use_last_error=True)
                kernel.OpenProcess.restype=ctypes.c_void_p;kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
                try:
                    deadline=time.monotonic()+5
                    while not pids.exists() and time.monotonic()<deadline:time.sleep(0.02)
                    for pid in json.loads(pids.read_text()):
                        handle=kernel.OpenProcess(0x100000,False,pid);self.assertTrue(handle);handles.append(handle)
                        self.assertEqual(kernel.WaitForSingleObject(handle,0),258)
                    crash.touch();self.assertEqual(process.wait(timeout=5),17)
                    for handle in handles:self.assertEqual(kernel.WaitForSingleObject(handle,5000),0,Path(str(pids)+".debug").read_text())
                finally:
                    crash.touch()
                    if process.poll() is None:process.wait(timeout=5)
                    for handle in handles:kernel.CloseHandle(handle)
    def test_abrupt_owner_exit_kills_descendants_without_cancel_handler(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pids=root/"pids.json";crash=root/"crash"
            grandchild=f"import sys,time,os; from pathlib import Path; sys.path.insert(0,{str(ROOT/'src')!r}); from process_group import own_process_tree; own_process_tree(); Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)"
            nested=f"import subprocess,sys,time,json,os; from pathlib import Path; sys.path.insert(0,{str(ROOT/'src')!r}); from process_group import own_process_tree,popen; own_process_tree(); grand=Path(sys.argv[1]+'.grand'); child=popen([sys.executable,'-c',{grandchild!r},str(grand)]); exec('while not grand.exists(): time.sleep(0.02)'); Path(sys.argv[1]).write_text(json.dumps([os.getpid(),int(grand.read_text())])); time.sleep(60)"
            owner="import sys,os,time,subprocess; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from process_group import own_process_tree,popen; own_process_tree(); child=popen([sys.executable,'-c',sys.argv[2],sys.argv[3]]); flag=Path(sys.argv[4]); exec('while not flag.exists(): time.sleep(0.02)'); os._exit(17)"
            with subprocess.Popen([sys.executable,"-c",owner,str(ROOT/"src"),nested,str(pids),str(crash)]) as process:
                handles=[];kernel=ctypes.WinDLL("kernel32",use_last_error=True)
                kernel.OpenProcess.restype=ctypes.c_void_p;kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
                try:
                    deadline=time.monotonic()+5
                    while not pids.exists() and time.monotonic()<deadline:time.sleep(0.02)
                    for pid in json.loads(pids.read_text()):
                        handle=kernel.OpenProcess(0x100000,False,pid);self.assertTrue(handle);handles.append(handle)
                        self.assertEqual(kernel.WaitForSingleObject(handle,0),258)
                    crash.touch();self.assertEqual(process.wait(timeout=5),17)
                    for handle in handles:self.assertEqual(kernel.WaitForSingleObject(handle,5000),0)
                finally:
                    crash.touch()
                    if process.poll() is None:process.wait(timeout=5)
                    for handle in handles:kernel.CloseHandle(handle)
    def test_nested_child_tree_exits(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            marker=root/"cancel"
            identities=root/"pids.json"
            nested="import subprocess,sys,time,json,os; from pathlib import Path; child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid])); time.sleep(60)"
            outer="import sys; sys.path.insert(0,sys.argv[1]); from process import run; run([sys.executable,'-c',sys.argv[2],sys.argv[3]],check=True)"
            with subprocess.Popen([sys.executable,"-c",outer,str(ROOT/"src"),nested,str(identities)],
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                                  env=dict(os.environ,ARRANGER_CANCEL_FILE=str(marker))) as process:
                handles=[]
                kernel=ctypes.WinDLL("kernel32",use_last_error=True)
                kernel.OpenProcess.restype=ctypes.c_void_p
                kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
                kernel.CloseHandle.argtypes=[ctypes.c_void_p]
                try:
                    deadline=time.monotonic()+5
                    while not identities.exists() and time.monotonic()<deadline:time.sleep(0.02)
                    pids=json.loads(identities.read_text())
                    for pid in pids:
                        handle=kernel.OpenProcess(0x100000,False,pid)
                        self.assertTrue(handle)
                        handles.append(handle)
                        self.assertEqual(kernel.WaitForSingleObject(handle,0),258)
                    marker.touch()
                    process.communicate(timeout=10)
                    self.assertNotEqual(process.returncode,0)
                    for handle in handles:self.assertEqual(kernel.WaitForSingleObject(handle,5000),0)
                finally:
                    marker.touch()
                    if process.poll() is None:process.communicate(timeout=10)
                    for handle in handles:kernel.CloseHandle(handle)

    def test_captured_child_with_marker_transport(self):
        from unittest.mock import patch
        sys.path.insert(0,str(ROOT/"src"))
        from process import run
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{"ARRANGER_CANCEL_FILE":str(Path(folder)/"cancel")}):
                result=run([sys.executable,"-c","print('captured')"],capture_output=True,text=True,check=True,timeout=5)
                self.assertEqual(result.stdout,"captured\n")
    def test_running_encoder_exit_and_no_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample, database = root / "known.wav", root / "catalog.sqlite"
            with wave.open(str(sample), "wb") as audio:
                audio.setparams((2, 2, 44100, 0, "NONE", "not compressed"))
                audio.writeframes(b"\x00\x10\x00\x10" * 44100)
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE sample(path TEXT, name TEXT)")
                connection.execute("INSERT INTO sample VALUES (?, ?)", (str(sample), sample.name))
            connection.close()
            jobs = root / "jobs"
            jobs.mkdir()
            marker = root / "cancel"
            command = [sys.executable, "-B", str(ROOT / "src/render.py"), "--catalog", str(database),
                       "--sample", sample.name, "--seconds", "30", "--jobs", str(jobs)]
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  env=dict(os.environ, ARRANGER_REALTIME="1",
                                           ARRANGER_CANCEL_FILE=str(marker))) as process:
                try:
                    line = process.stderr.readline()
                    self.assertTrue(line.startswith("child_started "), line)
                    child_pid = int(line.split()[1])
                    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                    kernel.OpenProcess.restype = ctypes.c_void_p
                    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                    handle = kernel.OpenProcess(0x100000, False, child_pid)
                    self.assertTrue(handle, "encoder must actually be running")
                    try:
                        self.assertEqual(kernel.WaitForSingleObject(handle, 0), 258)
                        marker.touch()
                        stdout, stderr = process.communicate(timeout=10)
                        self.assertNotEqual(process.returncode, 0)
                        self.assertIn("canceled", stderr)
                        self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
                        self.assertEqual(stdout, "")
                        self.assertEqual(list(jobs.iterdir()), [])
                    finally:
                        kernel.CloseHandle(handle)
                finally:
                    if process.poll() is None:
                        marker.touch()
                        process.communicate(timeout=10)

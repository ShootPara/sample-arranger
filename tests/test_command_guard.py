import os
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


@unittest.skipUnless(os.name=='nt','Windows process-object lifetime test')
class CommandGuardTests(unittest.TestCase):
    def test_creation_identity_mismatch_does_not_terminate_other_process(self):
        from command_guard import current_identity,ProcessGuard
        code="import sys,time;sys.path.insert(0,sys.argv[1]);from command_guard import current_identity;print(*current_identity(),flush=True);time.sleep(20)"
        with subprocess.Popen([sys.executable,'-B','-c',code,str(Path(__file__).resolve().parents[1]/'src')],stdout=subprocess.PIPE,text=True) as child:
            pid,creation=map(int,child.stdout.readline().split())
            try:
                with self.assertRaisesRegex(ValueError,'identity changed'):ProcessGuard(pid,creation+1)
                self.assertIsNone(child.poll())
                guard=ProcessGuard(pid,creation)
                try:self.assertTrue(guard.running());guard.terminate();child.wait(timeout=5);self.assertFalse(guard.running())
                finally:guard.close()
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)

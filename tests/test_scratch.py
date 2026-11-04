import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from scratch import scratch,cleanup,OWNER


class ScratchTests(unittest.TestCase):
    def test_cooperative_exception_and_publication_leave_no_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaisesRegex(ValueError,'fixture'):
                with scratch(root) as stage:
                    (stage/'partial.mp3').write_bytes(b'partial')
                    raise ValueError('fixture')
            self.assertEqual(list(root.iterdir()),[])
            with scratch(root) as stage:
                (stage/'result.mp3').write_bytes(b'complete')
                stage.rename(root/'job-fixture')
            self.assertEqual([path.name for path in root.iterdir()],['job-fixture'])

    def test_actual_owner_crash_cleanup_and_active_session_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);ready=root/'ready'
            code='''import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from scratch import scratch
with scratch(Path(sys.argv[2])) as stage:
    (stage/'unfinished.f32').write_bytes(b'owned partial')
    Path(sys.argv[3]).write_text(str(stage))
    time.sleep(30)
'''
            child=subprocess.Popen([sys.executable,'-B','-c',code,str(Path(__file__).resolve().parents[1]/'src'),str(root),str(ready)])
            try:
                deadline=time.monotonic()+5
                while not ready.exists() and time.monotonic()<deadline:time.sleep(0.02)
                self.assertTrue(ready.exists());stage=Path(ready.read_text())
                self.assertEqual(cleanup(root),0);self.assertTrue((stage/'unfinished.f32').exists())
                child.kill();child.wait(timeout=5)
                published=root/('job-'+str(uuid.uuid4()));published.mkdir();(published/'result.mp3').write_bytes(b'retained')
                foreign=root/'.scratch'/('work-'+str(uuid.uuid4()));foreign.mkdir();(foreign/'owner.json').write_text('{}')
                self.assertEqual(cleanup(root),1);self.assertFalse(stage.exists())
                self.assertTrue((published/'result.mp3').exists());self.assertTrue(foreign.exists())
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)

    def test_unknown_wrapper_content_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owned=root/'.scratch'/('work-'+str(uuid.uuid4()));owned.mkdir(parents=True)
            (owned/'owner.json').write_text(json.dumps(OWNER));(owned/'lock').write_bytes(b'0')
            (owned/'unrecognized.txt').write_text('do not infer ownership')
            self.assertEqual(cleanup(root),0);self.assertTrue((owned/'unrecognized.txt').exists())

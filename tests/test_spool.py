import json
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spool import cleanup, session_spool
from brief import interpret


class OwnershipTests(unittest.TestCase):
    def test_shared_orphan_cleanup_reports_bounds_and_protects_active_session(self):
        import os
        from unittest.mock import patch
        from commands import execute
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}):
            root=Path(directory)/'SampleArranger/continuous'
            with session_spool(root) as active:
                (active/'chunk-0.wav').write_bytes(b'active')
                orphan=root/'session-fixture';orphan.mkdir();(orphan/'owner.json').write_text(json.dumps({'owner':'sample-arranger-continuous','schema':1}));(orphan/'lock').write_bytes(b'0');(orphan/'chunk-0.wav').write_bytes(b'orphan')
                result=execute({'contract':1,'operation':'continuous.cleanup','arguments':{}})['result']
                self.assertEqual(result['removed_chunks'],1);self.assertEqual(result['active_sessions'],1);self.assertEqual(result['inactive_audio_bytes'],0)
                self.assertTrue((active/'chunk-0.wav').exists());self.assertFalse(orphan.exists())
    def test_typed_brief_constraints_and_single_consolidated_clarification(self):
        from music import compile_intent
        intent=interpret("one minute sparse music in Eb minor at137.25 BPM without bass")
        self.assertEqual(intent["state"],"ready")
        self.assertEqual(intent["musical"]["root"],3)
        self.assertEqual(intent["recommended_bpm"],137.25)
        self.assertEqual(intent["excluded_roles"],["bass"])
        score=compile_intent({"seconds":intent["seconds"],"bpm":intent["recommended_bpm"],**intent["musical"]})
        self.assertFalse(any(note["part"]=="bass" for note in score["notes"]))
        missing=interpret("music at20 BPM in C major and D minor")
        self.assertEqual(missing["state"],"needs_input")
        self.assertIn("duration",missing["message"]);self.assertIn("tempo",missing["message"]);self.assertIn("key",missing["message"])
        refined=interpret("1 minute at120 BPM in C major without bass","10 seconds at95 BPM in F# minor")
        self.assertEqual(refined["musical"]["root"],6)
        self.assertNotIn("parts",refined["musical"])
        self.assertEqual(refined["recommended_bpm"],95)
        self.assertEqual(interpret("music","still music at20 BPM")["state"],"invalid")

    def test_abrupt_process_exit_releases_lock_for_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = """import os,sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from spool import session_spool
with session_spool(Path(sys.argv[1])) as folder:
    (folder/'chunk-0.wav').write_bytes(b'audio')
    os._exit(17)
"""
            child = subprocess.run([sys.executable, "-B", "-c", code, str(root),
                                    str(Path(__file__).resolve().parents[1] / "src")], timeout=10)
            self.assertEqual(child.returncode, 17)
            self.assertEqual(cleanup(root), 1)
            self.assertEqual(list(root.glob("session-*/chunk-*.wav")), [])
            self.assertEqual(list(root.glob("session-*")), [],"orphan metadata must not grow indefinitely")
    def test_active_session_is_preserved_and_orphan_audio_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unrelated = root / "session-unrelated"
            unrelated.mkdir()
            (unrelated / "chunk-1.wav").write_bytes(b"private")
            with session_spool(root) as active:
                (active / "chunk-0.wav").write_bytes(b"audio")
                self.assertEqual(cleanup(root), 0)
                self.assertTrue((active / "chunk-0.wav").exists())
            orphan = root / "session-orphan"
            orphan.mkdir()
            (orphan / "owner.json").write_text(json.dumps(
                {"owner": "sample-arranger-continuous", "schema": 1}))
            (orphan / "lock").write_bytes(b"0")
            (orphan / "chunk-2.wav").write_bytes(b"audio")
            self.assertEqual(cleanup(root), 1)
            self.assertTrue((unrelated / "chunk-1.wav").exists())

    def test_refinement_replaces_initial_duration_and_energy(self):
        result = interpret("upbeat music for 1 minute", "calm piano for 20 seconds")
        self.assertEqual(result["seconds"], 20)
        self.assertEqual(result["role"], "piano")
        self.assertIsNone(result["recommended_bpm"])
        self.assertEqual(interpret("music")["state"], "needs_input")
        self.assertEqual(interpret("music", "music")["state"], "invalid")

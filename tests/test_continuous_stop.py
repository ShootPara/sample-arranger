import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from continuous import play


class ContinuousStopTests(unittest.TestCase):
    def test_external_stop_discards_all_chunks_without_an_export(self):
        requested=threading.Event()
        def consume(path,stop):
            self.assertTrue(path.is_file());requested.set();stop.wait(timeout=1)
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,{"LOCALAPPDATA":directory}):
                result=play(None,builtin=True,bpm=137,chunks=10,chunk_seconds=1,consume=consume,cancel_event=requested)
            self.assertEqual(result["state"],"stopped")
            self.assertEqual(result["audio_retention"],"disposable")
            self.assertNotIn("audio",result)
            self.assertEqual(list(Path(directory).rglob("*.wav")),[])

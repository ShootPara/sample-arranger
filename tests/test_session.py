import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from session import ContinuousSession


class SessionTests(unittest.TestCase):
    def test_continuous_generation_preserves_key_part_constraints_and_compact_evolution(self):
        import os
        from unittest.mock import patch
        import palette
        from continuous import play
        original=palette.render_score;observed=[];consumed=[]
        def record(score,path,**kwargs):
            observed.append(score)
            return original(score,path,**kwargs)
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,{'LOCALAPPDATA':directory}),patch.object(palette,'render_score',side_effect=record):
                result=play(None,builtin=True,bpm=240,chunks=4,chunk_seconds=1,
                            intent={'root':6,'mode':'minor','parts':['chords','melody'],'density':'sparse','seed':7},
                            consume=lambda path,stop:consumed.append(path))
            self.assertEqual(result['state'],'completed');self.assertEqual(len(consumed),4)
            self.assertEqual([score['ending_state']['next_bar'] for score in observed],[1,2,3,4])
            self.assertTrue(all(score['root']==6 and score['mode']=='minor' and score['seed']==7 for score in observed))
            self.assertTrue(all(note['part']!='bass' for score in observed for note in score['notes']))
            self.assertGreater(len({tuple(tuple(chord['pitches']) for chord in score['harmony']) for score in observed}),1)
            self.assertFalse(any(path.exists() for path in consumed))
            self.assertNotIn('audio',result)

    def test_oversized_chunk_is_rejected_and_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def generate(index, path, stop):
                path.write_bytes(bytes(129))
            session = ContinuousSession(root, generate, lambda *_: None, max_chunk_bytes=128)
            with self.assertRaisesRegex(ValueError, "byte cap"):
                session.run(1)
            self.assertEqual(list(root.iterdir()), [])
    def test_consumption_deletes_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = []
            def generate(index, path, stop):
                path.write_bytes(bytes(32))
            def consume(path, stop):
                self.assertTrue(path.exists())
                if previous:
                    self.assertFalse(previous[-1].exists())
                previous.append(path)
            ContinuousSession(root, generate, consume).run(40)
            self.assertEqual(len(previous), 40)
            self.assertEqual(list(root.iterdir()), [])

    def test_disconnect_cleans_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def generate(index, path, stop):
                path.write_bytes(bytes(32))
            def consume(path, stop):
                raise ConnectionError("playback device disconnected")
            with self.assertRaises(ConnectionError):
                ContinuousSession(root, generate, consume).run(40)
            self.assertEqual(list(root.iterdir()), [])

    def test_underrun_cancels_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def generate(index, path, stop):
                stop.wait(1)
            session = ContinuousSession(root, generate, lambda *_: None, wait_seconds=0.05)
            with self.assertRaises(TimeoutError):
                session.run(2)
            self.assertTrue(session.stop.is_set())
            self.assertEqual(list(root.iterdir()), [])

    def test_cancel_removes_ahead_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def generate(index, path, stop):
                path.write_bytes(bytes(32))
            session = ContinuousSession(root, generate, lambda path, stop: stop.set())
            session.run(40)
            self.assertEqual(list(root.iterdir()), [])

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vst3_render import render_plugin


class WorkerFailureTests(unittest.TestCase):
    def test_failed_worker_leaves_no_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.f32"
            source.write_bytes(bytes(8))
            with patch("vst3_render.run", return_value=subprocess.CompletedProcess(
                [], 3221225477, "", ""
            )):
                with self.assertRaisesRegex(ValueError, "worker failed"):
                    render_plugin(source, source, source, root)
            self.assertEqual(list(root.iterdir()), [source])

    def test_timeout_leaves_no_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.f32"
            source.write_bytes(bytes(8))
            with patch("vst3_render.run", side_effect=subprocess.TimeoutExpired([], 1)):
                with self.assertRaisesRegex(ValueError, "timed out"):
                    render_plugin(source, source, source, root, timeout=1)
            self.assertEqual(list(root.iterdir()), [source])

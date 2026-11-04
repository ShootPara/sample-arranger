import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from render import load_arrangement


class ArrangementTempoTests(unittest.TestCase):
    def test_explicit_double_time_and_rejected_stretch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "catalog.sqlite"
            plan = root / "plan.json"
            with sqlite3.connect(database) as db:
                db.execute("CREATE TABLE sample(path TEXT, name TEXT)")
                db.execute("INSERT INTO sample VALUES (?, ?)", (str(root / "loop.wav"), "loop.wav"))
            db.close()
            section = {"sample": "loop.wav", "seconds": 4, "source_bpm": 65,
                       "target_bpm": 128, "beat_scale": 2}
            plan.write_text(json.dumps([section]), encoding="utf-8")
            self.assertAlmostEqual(load_arrangement(plan, database)[0][2], 128 / 130)
            section["beat_scale"] = 0.5
            plan.write_text(json.dumps([section]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "tempo stretch"):
                load_arrangement(plan, database)

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute


class CatalogCorrectionTests(unittest.TestCase):
    def test_manual_history_and_rescan_preserve_observations_but_invalidate_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sample=root/'drum_130BPM.wav';sample.write_bytes(b'fixture')
            database=root/'catalog.sqlite'
            def command(operation,**args):return execute({'contract':1,'operation':operation,'arguments':{'catalog':str(database),**args}})['result']
            command('catalog.scan',root=str(sample),metadata_only=True)
            corrected=command('catalog.correct',path=str(sample),bpm=65)
            self.assertEqual(corrected['bpm_hint'],130)
            self.assertEqual(corrected['tempo_correction'],65)
            self.assertTrue(corrected['tempo_correction_record']['valid'])
            self.assertTrue(corrected['tempo_correction_record']['corrected_utc'])
            command('catalog.correct',path=str(sample),bpm=130)
            with sqlite3.connect(database) as db:self.assertEqual(db.execute('SELECT count(*) FROM tempo_correction_history').fetchone()[0],2)
            db.close()
            sample.write_bytes(b'different fixture')
            command('catalog.scan',root=str(sample),metadata_only=True)
            result=command('catalog.search',term='drum')[0]
            self.assertEqual(result['bpm_hint'],130)
            self.assertIsNone(result['tempo_correction'])
            self.assertEqual(result['tempo_correction_record']['bpm'],130)
            self.assertFalse(result['tempo_correction_record']['valid'])


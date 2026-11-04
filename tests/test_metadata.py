import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from riff_metadata import observe


class MetadataTests(unittest.TestCase):
    def wav(self,path,bpm=120,flags=2):
        fmt=struct.pack('<HHIIHH',1,1,8000,16000,2,16)
        acid=struct.pack('<IHHfIHHf',flags,60,0x8000,0,2,4,4,bpm)
        content=b'WAVE'+b'fmt '+struct.pack('<I',len(fmt))+fmt+b'acid'+struct.pack('<I',len(acid))+acid+b'data'+struct.pack('<I',16000)+bytes(16000)
        path.write_bytes(b'RIFF'+struct.pack('<I',len(content))+content)

    def test_declared_tempo_consistency_one_shot_and_malformed_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.wav';self.wav(path)
            result=observe(path);self.assertEqual(result['duration_seconds'],1)
            self.assertEqual(result['acid'][0]['recommendation'],'duration_consistent_candidate')
            self.assertEqual(result['acid'][0]['root_midi'],60)
            self.wav(path,bpm=90)
            self.assertEqual(observe(path)['acid'][0]['recommendation'],'review_conflict_or_unknown')
            self.wav(path,flags=3)
            self.assertEqual(observe(path)['acid'][0]['recommendation'],'review_one_shot')
            value=bytearray(path.read_bytes());struct.pack_into('<I',value,16,2**32-1);path.write_bytes(value)
            with self.assertRaisesRegex(ValueError,'extends past'):observe(path)

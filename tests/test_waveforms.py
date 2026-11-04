import os
from pathlib import Path
import sys
import tempfile
import unittest
import wave
from array import array
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute


class WaveformTests(unittest.TestCase):
    def test_stereo_opposite_polarity_remains_visible_without_audio_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'known.wav'
            values=array('h',[16384,-16384])*4410
            with wave.open(str(source),'wb') as output:
                output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(values.tobytes())
            result=execute({'contract':1,'operation':'assets.waveform','arguments':{'path':str(source)}})['result']
            self.assertEqual(result['cache'],'memory only')
            self.assertLessEqual(len(result['peaks']),256)
            self.assertAlmostEqual(result['source_seconds'],0.1)
            self.assertGreater(max(high for _,high in result['peaks']),0.49)
            self.assertLess(min(low for low,_ in result['peaks']),-0.49)
            self.assertEqual(list(root.iterdir()),[source])

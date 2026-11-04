import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from audio_measurements import measure
from commands import execute
from render import render
from process import run


class MeasurementTests(unittest.TestCase):
    def tone(self,path,seconds=1):
        frames=round(seconds*44100);signal=0.5*np.sin(2*np.pi*997*np.arange(frames)/44100)
        with wave.open(str(path),'wb') as output:
            output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(np.repeat((signal*32767).astype('<i2'),2).tobytes())
    def test_independent_known_signal_peak_rms_duration_and_source_preservation(self):
        from assets import digest
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'tone.wav';self.tone(source);before=digest(source)
            result=execute({'contract':1,'operation':'audio.inspect','arguments':{'path':str(source)}})['result']
            self.assertEqual(result['decoded_frames'],44100);self.assertFalse(result['silent'])
            self.assertAlmostEqual(result['sample_peak_dbfs'],20*math.log10(0.5),delta=0.01)
            self.assertAlmostEqual(result['rms_dbfs'],20*math.log10(0.5/math.sqrt(2)),delta=0.01)
            self.assertAlmostEqual(result['true_peak_dbtp'],20*math.log10(0.5),delta=0.15)
            self.assertIsNotNone(result['integrated_lufs']);self.assertEqual(digest(source),before)
            with self.assertRaisesRegex(ValueError,'length differs'):measure(source,40000)
    def test_fractional_clip_boundaries_do_not_accumulate_rounding_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'tone.wav';self.tone(source)
            sections=[(source,0.10001,1)]*16
            result=render(source,None,sum(length for _,length,_ in sections),root/'jobs',sections=sections)
            self.assertEqual(result['measurements']['decoded_frames'],round(16*0.10001*44100))
            self.assertFalse(result['measurements']['silent'])
    def test_silence_is_reported_without_invented_loudness_and_url_protocol_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'silence.wav'
            with wave.open(str(source),'wb') as output:output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(bytes(4410*4))
            result=measure(source);self.assertTrue(result['silent']);self.assertIsNone(result['integrated_lufs']);self.assertIsNone(result['rms_dbfs'])
        blocked=run(['ffmpeg','-nostdin','-v','error','-i','tcp://127.0.0.1:9','-f','null','-'],capture_output=True,text=True,timeout=5)
        self.assertNotEqual(blocked.returncode,0);self.assertIn('not on whitelist',blocked.stderr)
        self.assertNotIn('Connection refused',blocked.stderr,'protocol must be rejected before opening a connection')

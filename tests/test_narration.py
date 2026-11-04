from array import array
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from render import render
from narration import inspect_fit,settings
from assets import digest


def tone(path,frequency,seconds,amplitude):
    samples=amplitude*np.sin(2*np.pi*frequency*np.arange(round(seconds*44100))/44100)
    with wave.open(str(path),'wb') as output:
        output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(np.repeat((samples*32767).astype('<i2'),2).tobytes())


def decode(path):
    completed=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','f32le','-'],capture_output=True,check=True,timeout=10)
    return np.frombuffer(completed.stdout,dtype='<f4').reshape(-1,2)[:,0]


class NarrationTests(unittest.TestCase):
    def test_shared_placement_inspection_reports_decoded_clip_length_and_bounds(self):
        from commands import execute
        with tempfile.TemporaryDirectory() as directory:
            voice=Path(directory)/'voice.wav';tone(voice,880,0.5,0.1)
            args={'voice':str(voice),'seconds':2,'voice_settings':{'offset_seconds':1}}
            report=execute({'contract':1,'operation':'narration.inspect','arguments':args})['result']
            self.assertEqual(report['decoded_frames'],22050);self.assertEqual(report['offset_samples'],44100)
            self.assertEqual(report['bytes'],voice.stat().st_size)
            with self.assertRaisesRegex(ValueError,'four minutes'):
                execute({'contract':1,'operation':'narration.inspect','arguments':{**args,'seconds':float('inf')}})
            with self.assertRaisesRegex(ValueError,'four minutes'):inspect_fit(voice,44100*241)

    def test_offset_ducking_and_unmodified_source_with_independent_frequency_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jobs=root/'jobs';jobs.mkdir();bed=root/'bed.wav';voice=root/'voice.wav'
            tone(bed,220,3,0.15);tone(voice,880,0.5,0.2);original=digest(voice)
            result=render(bed,voice,3,jobs,voice_settings={'offset_seconds':1})
            audio=decode(result['audio'])
            self.assertEqual(len(audio),3*44100)
            def amplitude(frequency,start,end):
                first,last=round(start*44100),round(end*44100);time=np.arange(first,last)/44100
                return abs(2*np.sum(audio[first:last]*np.exp(-2j*np.pi*frequency*time))/(last-first))
            self.assertLess(amplitude(880,0.2,0.7),0.002)
            self.assertGreater(amplitude(880,1.1,1.4),0.15)
            self.assertLess(amplitude(880,1.9,2.4),0.002)
            self.assertLess(amplitude(220,1.1,1.4),amplitude(220,0.2,0.7)*0.65)
            self.assertGreater(amplitude(220,2.3,2.8),amplitude(220,1.1,1.4)*1.4)
            self.assertEqual(digest(voice),original)
            self.assertEqual(result['narration']['decoded_frames'],22050)
            self.assertEqual(result['narration']['offset_samples'],44100)
            self.assertTrue(result['music_edge_fades']['before_narration'])
            self.assertEqual(sorted(path.name for path in Path(result['audio']).parent.iterdir()),['manifest.json','result.mp3'])
            un_ducked=render(bed,voice,3,jobs,voice_settings={'offset_seconds':1,'ducking':False})
            audio=decode(un_ducked['audio'])
            self.assertGreater(amplitude(220,1.1,1.4),amplitude(220,0.2,0.7)*0.9)

    def test_saved_voice_reference_and_settings_reopen_and_changed_source_blocks(self):
        from commands import execute
        from project import save,inspect
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);voice=root/'voice.wav';tone(voice,880,0.3,0.2)
            path=root/'project.json';jobs=root/'jobs';jobs.mkdir()
            project=save(path,[],score=compile_intent({'seconds':1}),voice=voice,voice_settings={'offset_seconds':0.2,'ducking':False})
            self.assertEqual(project['schema'],6)
            result=execute({'contract':1,'operation':'project.render','arguments':{'project':str(path),'jobs':str(jobs)}})['result']
            self.assertEqual(result['narration']['offset_samples'],8820)
            self.assertFalse(result['narration']['settings']['ducking'])
            self.assertEqual(len(decode(result['audio'])),44100)
            identity={key:project['narration'][key] for key in ('path','bytes','sha256')}
            tone(voice,990,0.3,0.2)
            self.assertFalse(inspect(path)['ready'])
            with self.assertRaisesRegex(ValueError,'missing or changed'):
                execute({'contract':1,'operation':'project.render','arguments':{'project':str(path),'jobs':str(jobs)}})
            with self.assertRaisesRegex(ValueError,'pinned narration changed'):
                save(root/'snapshot.json',[],score=project['score'],voice=voice,voice_asset=identity)
    def test_mp3_padding_is_not_voice_content_and_overlong_audio_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'voice.wav';mp3=root/'voice.mp3';tone(source,880,0.5,0.2)
            subprocess.run(['ffmpeg','-v','error','-i',str(source),'-c:a','libmp3lame','-b:a','192k',str(mp3)],check=True,timeout=10)
            result=inspect_fit(mp3,22050)
            self.assertEqual(result['decoded_frames'],22050)
            with self.assertRaisesRegex(ValueError,'no speech was truncated'):inspect_fit(source,20000)
            with self.assertRaises(ValueError):settings({'ducking':'yes'})

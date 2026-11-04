from fractions import Fraction
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from continuous import chunk_frames,play
from music import compile_intent


class RollingMusicTests(unittest.TestCase):
    def test_relative_melody_intention_survives_rolling_boundary_and_deletion(self):
        from palette import render_score as render_palette
        pattern=[{'tone':0,'ticks':960,'velocity':80},{'tone':-1,'ticks':960,'velocity':0},{'tone':2,'ticks':1920,'velocity':70}]
        scores=[];consumed=[]
        def render(score,*args,**kwargs):scores.append(score);return render_palette(score,*args,**kwargs)
        def consume(path,stop):
            with wave.open(str(path)) as audio:consumed.append(audio.getnframes())
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}),patch('palette.render_score',side_effect=render):
            result=play(None,bpm=137,chunks=3,chunk_seconds=1,builtin=True,consume=consume,intent={'root':9,'mode':'minor','melody_pattern':pattern})
            self.assertEqual(result['chunks_submitted'],3);self.assertEqual([s['ending_state']['next_bar'] for s in scores],[1,2,3])
            self.assertEqual([s['melody_pattern'] for s in scores],[pattern]*3)
            self.assertEqual(consumed,[chunk_frames(i,1,137) for i in range(3)])
            self.assertFalse(list(Path(directory).rglob('*.wav')))

    def test_global_sample_clock_does_not_accumulate_block_rounding(self):
        counts=[chunk_frames(index,34,137) for index in range(10000)]
        self.assertEqual(sum(counts),round(Fraction(10000*34*240*44100,137)))
        self.assertLessEqual(max(counts)-min(counts),1)

    def test_compact_harmonic_boundary_state_and_disposable_audio(self):
        first=compile_intent({"bars":3,"bpm":137,"resolve":False})
        state=first["ending_state"]
        second=compile_intent({"bars":3,"bpm":137,"resolve":False,"bar_offset":state["next_bar"],
                               "previous_chord":state["previous_chord"],"seed":state["seed"]})
        self.assertEqual(second["harmony"][0]["degree"],5)
        observed=[]
        def consume(path,stop):
            with wave.open(str(path)) as audio:
                observed.append((audio.getnframes(),hashlib.sha256(audio.readframes(audio.getnframes())).hexdigest()))
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,{"LOCALAPPDATA":directory}):
                play(None,bpm=137,chunks=3,chunk_seconds=1,builtin=True,consume=consume)
            self.assertEqual([frames for frames,_ in observed],[chunk_frames(i,1,137) for i in range(3)])
            self.assertEqual(len({checksum for _,checksum in observed}),3)
            self.assertEqual(list(Path(directory).rglob("*.wav")),[])

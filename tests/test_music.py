from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from music import compile_intent,native_notes,validate


class MusicTests(unittest.TestCase):
    def test_bed_form_varies_density_and_parts_without_breaking_harmony_or_duration(self):
        score=compile_intent({'seconds':60,'bpm':128,'form':'bed','parts':['chords','melody']})
        self.assertEqual([section['role'] for section in score['form']],['intro','main','lift','outro'])
        self.assertEqual(score['duration_frames'],60*44100)
        self.assertNotIn('bass',{note['part'] for note in score['notes']})
        intro=score['form'][0]['bars']*4*960
        self.assertFalse(any(note['part']=='melody' and note['tick']<intro for note in score['notes']))
        self.assertTrue(any(note['part']=='melody' and note['tick']>=intro for note in score['notes']))
        self.assertEqual(score['harmony'][-1]['degree'],1)
        self.assertLess(max(note['velocity'] for note in score['notes'] if note['tick']<intro),
                        max(note['velocity'] for note in score['notes'] if note['tick']>=intro))
        with self.assertRaisesRegex(ValueError,'form bars'):
            compile_intent({'bars':8,'form':[{'bars':2,'role':'intro'}]})
        with self.assertRaisesRegex(ValueError,'contradicts'):
            compile_intent({'bars':8,'parts':['melody'],'form':[{'bars':8,'role':'main','parts':['bass']}]})
        validate(compile_intent({'bars':1,'parts':['melody'],'form':'bed'}))
    def test_four_minute_fast_score_and_exact_requested_seconds(self):
        score=compile_intent({"bpm":240,"seconds":240,"density":"busy"})
        self.assertEqual(score["duration_frames"],240*44100)
        self.assertEqual(score["bars"],240)
        for part in ("bass","chords","melody"):
            self.assertLessEqual(len(native_notes(score,part).splitlines()),2048)
        short=compile_intent({"bpm":137,"seconds":7.123})
        self.assertEqual(short["duration_frames"],round(7.123*44100))
        fractional=compile_intent({"bpm":137.25,"seconds":7.123})
        self.assertEqual(fractional["duration_frames"],round(7.123*44100))
        self.assertTrue(native_notes(fractional,"bass"))
        self.assertEqual(compile_intent({"bpm":137.24,"seconds":240})["duration_frames"],240*44100)
    def test_form_harmony_register_note_lifecycle_and_exact_clock(self):
        score=compile_intent({"bpm":137,"bars":8,"mode":"minor","root":9,"density":"busy"})
        self.assertEqual(score["harmony"][-1]["degree"],1)
        self.assertEqual(score,compile_intent({"bpm":137,"bars":8,"mode":"minor","root":9,"density":"busy"}))
        for chord in score["harmony"]:
            self.assertLessEqual(max(chord["pitches"])-min(chord["pitches"]),16)
        rows=[list(map(int,line.split())) for line in native_notes(score,"bass").splitlines()]
        self.assertEqual(rows[2][0],round(4*60*44100/137))
        self.assertTrue(all(start<end for start,end,_,_ in rows))
        broken=deepcopy(score)
        broken["notes"].append(deepcopy(broken["notes"][0]))
        with self.assertRaisesRegex(ValueError,"overlapping"):
            validate(broken)
        with self.assertRaisesRegex(ValueError,"four minutes"):
            compile_intent({"bpm":40,"bars":64})

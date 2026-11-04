from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from music import compile_intent,edit_harmony,set_note_locks,validate,SCALES,chord_label
from project import save,read
from commands import execute


class HarmonyTests(unittest.TestCase):
    def test_revoice_one_bar_preserves_rhythm_other_events_and_compatible_locks(self):
        score=compile_intent({'bars':4});original=deepcopy(score)
        # C is shared between old A-minor and new F-major triads in bar2.
        index=next(i for i,n in enumerate(score['notes']) if n['part']=='chords' and n['tick']==3840 and n['pitch']%12==0)
        score=set_note_locks(score,[index]);locked=deepcopy(score['notes'][index])
        result=edit_harmony(score,[{'bar':1,'degree':4}]);validate(result)
        self.assertEqual(result['harmony'][1]['degree'],4);self.assertEqual(chord_label(result,result['harmony'][1]),'F')
        self.assertEqual(result['notes'][index],locked);self.assertEqual(result['note_locks'],[locked])
        for before,after in zip(score['notes'],result['notes']):
            if not 3840<=before['tick']<7680:self.assertEqual(before,after)
            self.assertEqual({k:v for k,v in before.items() if k!='pitch'},{k:v for k,v in after.items() if k!='pitch'})
            if 3840<=before['tick']<7680:self.assertIn(after['pitch']%12,{5,9,0})
        self.assertEqual(score['notes'],original['notes']);self.assertEqual(result['duration_frames'],score['duration_frames'])
    def test_lock_conflict_crossing_notes_and_duplicate_edits_fail_atomically(self):
        score=compile_intent({'bars':4})
        index=next(i for i,n in enumerate(score['notes']) if n['part']=='bass' and n['tick']==3840)
        score=set_note_locks(score,[index]);before=deepcopy(score)
        with self.assertRaisesRegex(ValueError,'locked note'):edit_harmony(score,[{'bar':1,'degree':7}])
        self.assertEqual(score,before)
        with self.assertRaisesRegex(ValueError,'duplicate'):edit_harmony(score,[{'bar':1,'degree':4}]*2)
        crossing=compile_intent({'bars':4});note=next(n for n in crossing['notes'] if n['part']=='melody' and n['tick']==2880);note['length']=1010;validate(crossing)
        with self.assertRaisesRegex(ValueError,'crosses'):edit_harmony(crossing,[{'bar':1,'degree':4}])
    def test_shared_project_revision_harmonic_key_checks_and_minor_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'project.json';score=compile_intent({'bars':4,'root':9,'mode':'minor'});save(path,[],score=score)
            result=execute({'contract':1,'operation':'project.harmony.edit','arguments':{'project':str(path),'changes':[{'bar':1,'degree':2}],'expected_revision':1}})['result']
            self.assertTrue(result['ready']);self.assertEqual(read(path)['revision'],2)
            chord=read(path)['score']['harmony'][1];self.assertEqual(chord_label(score,chord),'Bdim')
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'revision conflict'):
                execute({'contract':1,'operation':'project.harmony.edit','arguments':{'project':str(path),'changes':[{'bar':1,'degree':4}],'expected_revision':1}})
            self.assertEqual(path.read_bytes(),before)
            malformed=deepcopy(score);malformed['harmony'][0]['pitches']=[60,64,67]
            with self.assertRaisesRegex(ValueError,'contradicts'):validate(malformed)


if __name__=='__main__':unittest.main()

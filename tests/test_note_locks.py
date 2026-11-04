from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute
from music import compile_intent,edit_score,set_note_locks
from project import save,read


class NoteLockTests(unittest.TestCase):
    def test_unrelated_index_changes_preserve_exact_locks_and_locked_changes_fail_atomically(self):
        score=compile_intent({'bars':4});locked=set_note_locks(score,[5]);original=deepcopy(locked)
        for changes in ([{'action':'set','index':5,'field':'velocity','value':1}], [{'action':'remove','index':5}]):
            with self.assertRaisesRegex(ValueError,'locked note'):edit_score(locked,changes)
            self.assertEqual(locked,original)
        shifted=edit_score(locked,[{'action':'remove','index':0}])
        self.assertEqual(shifted['notes'][4],score['notes'][5]);self.assertEqual(shifted['note_locks'],locked['note_locks'])
        unblocked=set_note_locks(shifted,[])
        changed=edit_score(unblocked,[{'action':'set','index':4,'field':'velocity','value':1}])
        self.assertEqual(changed['notes'][4]['velocity'],1)
    def test_saved_project_lock_and_revision_are_shared_between_cli_edits_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'project.json';save(path,[],score=compile_intent({'seconds':2}))
            def call(operation,**args):return execute({'contract':1,'operation':operation,'arguments':{'project':str(path),**args}})['result']
            result=call('project.notes.lock',indices=[0],expected_revision=1)
            self.assertEqual(result['project']['revision'],2);self.assertEqual(read(path)['score']['note_locks'],[read(path)['score']['notes'][0]])
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'locked note'):
                call('project.notes.edit',changes=[{'action':'set','index':0,'field':'velocity','value':1}],expected_revision=2)
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'saved note locks'):
                save(path,[],score=compile_intent({'seconds':2}),expected_revision=2)
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'revision conflict'):call('project.notes.lock',indices=[],expected_revision=1)
            call('project.notes.lock',indices=[],expected_revision=2)
            self.assertEqual(read(path)['revision'],3)
    def test_four_minute_score_lock_validation_is_bounded_and_identity_types_are_strict(self):
        start=time.monotonic();score=compile_intent({'seconds':240,'bpm':240,'density':'busy'})
        locked=set_note_locks(score,list(range(len(score['notes']))))
        self.assertGreater(len(locked['note_locks']),2000)
        self.assertLess(time.monotonic()-start,5)
        with self.assertRaises(ValueError):set_note_locks(score,[True])


if __name__=='__main__':unittest.main()

from copy import deepcopy
import json
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from music import compile_intent,edit_harmony,edit_score,apply_melody_pattern,validate,render_without_parts
from musical_locks import set_locks,preserve
from commands import execute


class MusicalLocksTests(unittest.TestCase):
    def test_distinct_harmony_rhythm_and_section_projections(self):
        score=compile_intent({'bars':3,'resolve':False})
        harmony=set_locks(score,[{'bar':1,'kind':'harmony','part':'all'}])
        with self.assertRaisesRegex(ValueError,'protected harmony'):edit_harmony(harmony,[{'bar':1,'degree':2}])
        # A rhythmic edit is allowed under a harmony intention lock.
        pattern=[{'tone':0,'ticks':1920,'velocity':72},{'tone':2,'ticks':1920,'velocity':74}]
        validate(apply_melody_pattern(harmony,[1],pattern))
        rhythm=set_locks(score,[{'bar':1,'kind':'rhythm','part':'melody'}])
        index=next(i for i,n in enumerate(score['notes']) if n['part']=='melody' and n['tick']//3840==1)
        validate(edit_score(rhythm,[{'action':'set','index':index,'field':'velocity','value':1}]))
        # Chord/degree changes preserve accepted melody timing under a rhythm lock.
        validate(edit_harmony(rhythm,[{'bar':1,'degree':2}]))
        with self.assertRaisesRegex(ValueError,'protected rhythm'):apply_melody_pattern(rhythm,[1],pattern)
        section=set_locks(score,[{'bar':1,'kind':'section','part':'all'}])
        with self.assertRaisesRegex(ValueError,'protected section'):edit_score(section,[{'action':'set','index':index,'field':'velocity','value':1}])
        validate(edit_harmony(section,[{'bar':0,'degree':2}]))
        altered=deepcopy(section);altered['bpm']=121;altered['duration_frames']=round(altered['duration_ticks']*60*44100/(960*121))
        with self.assertRaisesRegex(ValueError,'protected'):validate(altered)
        internal=render_without_parts(section,['melody']);self.assertNotIn('musical_locks',internal);self.assertIn('musical_locks',section)

    def test_saved_locks_require_explicit_release_even_if_rehashed_or_removed(self):
        spec={'bar':1,'kind':'harmony','part':'all'};score=set_locks(compile_intent({'bars':3}),[spec])
        def call(op,**args):return execute({'contract':1,'operation':op,'arguments':args})['result']
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'score.json')
            call('project.save',project=path,sections=[],score=score)
            replacement=set_locks(score,[])
            for candidate in (replacement,edit_harmony(replacement,[{'bar':1,'degree':2}])):
                with self.assertRaisesRegex(ValueError,'saved musical'):call('project.save',project=path,sections=[],score=candidate,expected_revision=1)
            repinned=set_locks(edit_harmony(replacement,[{'bar':1,'degree':2}]),[spec])
            with self.assertRaisesRegex(ValueError,'saved musical'):call('project.save',project=path,sections=[],score=repinned,expected_revision=1)
            saved=call('project.save',project=path,sections=[],score=repinned,expected_revision=1,released_musical_locks=[spec])
            self.assertEqual(saved['revision'],2)
            self.assertEqual(json.loads(Path(path).read_text(encoding='utf-8'))['score']['harmony'][1]['degree'],2)
        with self.assertRaisesRegex(ValueError,'saved musical'):preserve(score,replacement,[{'bar':0,'kind':'harmony','part':'all'}])

    def test_lock_structure_tamper_and_cli_schema_are_bounded(self):
        score=compile_intent({'bars':2});spec={'bar':0,'kind':'section','part':'all'}
        for specs in ([spec,spec],[{**spec,'bar':True}],[{**spec,'part':'melody'}],[{**spec,'bar':2}]):
            with self.assertRaises(ValueError):set_locks(score,specs)
        locked=set_locks(score,[spec]);locked['musical_locks'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'protected'):validate(locked)
        from contract_schema import request_schema
        self.assertTrue(request_schema('score.musical.locks.set'))

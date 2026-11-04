from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute
from midi_planning import prepare,validate_proposal,current,propose_with_port
from music import compile_intent,native_notes,validate

PATTERN=[{'tone':0,'ticks':960,'velocity':80},{'tone':-1,'ticks':480,'velocity':0},
         {'tone':2,'ticks':480,'velocity':90},{'tone':1,'ticks':1920,'velocity':70}]
STATE={'revision':3,'brief':'A gentle rising phrase; rests leave narration space.',
       'intent':{'bpm':120,'root':9,'mode':'minor','bars':2,'resolve':False,'parts':['melody','bass']}}
PROPOSAL={'revision':3,'progression':[1,4],'density':'sparse','melody_pattern':PATTERN}


class MidiPlanningTests(unittest.TestCase):
    def test_model_grid_uses_host_timing_and_velocity_without_bar_arithmetic(self):
        state={**deepcopy(STATE),'grid_steps':8}
        proposal={'revision':3,'progression':[1,4],'density':'sparse','melody_grid':[0,-1,2,-1,1,-1,2,-1]}
        request=prepare(state);self.assertEqual(request['output_schema']['properties']['melody_grid']['minItems'],8)
        result=validate_proposal(state,{'structured':proposal});pattern=result['intent']['melody_pattern']
        self.assertEqual(sum(cell['ticks'] for cell in pattern),3840)
        self.assertEqual({cell['ticks'] for cell in pattern},{480})
        self.assertEqual([cell['velocity'] for cell in pattern],[76,0,76,0,76,0,76,0])
        self.assertEqual(result['score']['duration_frames'],176400)
        with self.assertRaises(ValueError):validate_proposal(state,{'structured':{**proposal,'melody_grid':[0]*7}})
        with self.assertRaises(ValueError):validate_proposal(state,{'structured':{**proposal,'melody_grid':[-1]*8}})

    def test_relative_phrase_rest_harmony_exact_noteoffs_and_partial_end(self):
        result=validate_proposal(STATE,{'structured':PROPOSAL});score=result['score'];validate(score)
        self.assertEqual(score['generator'],'intent-compiler-3')
        notes=[n for n in score['notes'] if n['part']=='melody']
        self.assertEqual([n['tick'] for n in notes],[0,1440,1920,3840,5280,5760])
        for note in notes:
            chord=score['harmony'][note['tick']//3840]
            self.assertIn(note['pitch']%12,{p%12 for p in chord['pitches']})
            self.assertEqual(note['length'],next(c['ticks'] for c in PATTERN if c['tone']==[0,2,1][notes.index(note)%3]))
        rows=[list(map(int,line.split())) for line in native_notes(score,'melody').splitlines()]
        self.assertEqual(rows[0][:2],[0,22050]);self.assertEqual(rows[1][0],33075)
        short=compile_intent({'bpm':120,'seconds':1.8,'parts':['melody'],'melody_pattern':PATTERN})
        self.assertEqual(short['notes'][-1]['tick']+short['notes'][-1]['length'],short['duration_ticks'])
        self.assertEqual(short['duration_frames'],79380)
        fast=compile_intent({'bpm':240,'seconds':240,'melody_pattern':PATTERN})
        self.assertLessEqual(len(native_notes(fast,'melody').splitlines()),2048)
        self.assertNotIn('melody_pattern',compile_intent({'bars':1}))

    def test_semantic_rejection_hard_context_locks_and_stale_response(self):
        result=validate_proposal(STATE,{'structured':PROPOSAL});self.assertTrue(current(STATE,result)['current'])
        for key,value in (('revision',4),('brief','Refined request')):
            changed={**STATE,key:value}
            with self.assertRaisesRegex(ValueError,'stale'):current(changed,result)
        state=deepcopy(STATE);state['protected_notes']=[result['score']['notes'][0]]
        locked=validate_proposal(state,{'structured':PROPOSAL});self.assertEqual(locked['score']['note_locks'],state['protected_notes'])
        changed=deepcopy(PROPOSAL);changed['progression']=[2,4]
        with self.assertRaisesRegex(ValueError,'protected'):validate_proposal(state,{'structured':changed})
        state=deepcopy(STATE);state['intent']['density']='busy'
        with self.assertRaisesRegex(ValueError,'hard intention'):validate_proposal(state,{'structured':PROPOSAL})
        for cell in ({'tone':0,'ticks':3840,'velocity':122},{'tone':-1,'ticks':3840,'velocity':0},
                     {'tone':True,'ticks':3840,'velocity':80},{'tone':0,'ticks':3839,'velocity':80}):
            with self.assertRaises(ValueError):validate_proposal(STATE,{'structured':{**PROPOSAL,'melody_pattern':[cell]}})
        with self.assertRaises(ValueError):prepare({**STATE,'intent':{**STATE['intent'],'bars':5}})
        with self.assertRaises(ValueError):prepare({**STATE,'brief':'é'*10000})
        with self.assertRaises(ValueError):prepare(STATE,context=512,output_limit=1024)
        with self.assertRaises(RuntimeError):validate_proposal(STATE,{'structured':PROPOSAL,'limited':True})

    def test_injected_one_repair_budget_and_no_network(self):
        class Port:
            def __init__(self):self.count=0;self.requests=[]
            def admit(self,request,timeout):self.count+=1;self.requests.append(request);return {'id':str(self.count),'state':'queued'}
            def poll(self,job_id,timeout):return {'id':job_id,'state':'completed','result':{'structured':{**PROPOSAL,'revision':0} if job_id=='1' else PROPOSAL}}
            def cancel(self,*args,**kwargs):raise AssertionError('completed job must not be canceled')
        port=Port();result=propose_with_port(STATE,port,sleep=lambda _:None)
        self.assertEqual(result['attempts'],2);self.assertEqual(port.count,2)
        self.assertEqual(len(result['inference_receipts']),2)
        self.assertLessEqual(len(port.requests[1]['prompt'].encode('utf-8'))+256+12+1024,4096)

    def test_shared_prepare_validate_current_save_reopen_render(self):
        def call(op,**args):return execute({'contract':1,'operation':op,'arguments':args})['result']
        request=call('midi.planning.prepare',musical_state=STATE)
        self.assertLessEqual(len(request['prompt'].encode('utf-8'))+256+12+1024,4096)
        result=call('midi.planning.validate',musical_state=STATE,response={'structured':PROPOSAL})
        self.assertTrue(call('midi.planning.current',musical_state=STATE,response=result)['current'])
        with tempfile.TemporaryDirectory() as folder:
            project=str(Path(folder)/'phrase.json');jobs=str(Path(folder)/'jobs')
            call('project.save',project=project,sections=[],score=result['score'])
            reopened=json.loads(Path(project).read_text(encoding='utf-8'))
            self.assertEqual(reopened['score']['melody_pattern'],PATTERN)
            output=call('project.render',project=project,jobs=jobs)
            self.assertTrue(output)
            mp3=list(Path(jobs).glob('job-*/music.mp3'))
            if not mp3:mp3=list(Path(jobs).glob('job-*/*.mp3'))
            self.assertEqual(len(mp3),1)
            from audio_measurements import measure
            measured=measure(mp3[0],expected_frames=4*44100);self.assertFalse(measured['silent']);self.assertGreater(measured['rms_dbfs'],-60)
            self.assertGreater(mp3[0].stat().st_size,1000)

    def test_selected_rhythm_edits_preserve_unrelated_events_and_reject_locked_changes(self):
        from music import apply_melody_pattern,set_note_locks
        score=compile_intent({'bars':3,'root':9,'mode':'minor'})
        changed=apply_melody_pattern(score,[1],PATTERN)
        untouched=lambda s:[n for n in s['notes'] if n['part']!='melody' or n['tick']//3840!=1]
        self.assertEqual(untouched(changed),untouched(score));self.assertEqual(changed['melody_patterns']['1'],PATTERN)
        index=next(i for i,n in enumerate(score['notes']) if n['part']=='melody' and n['tick']//3840==1)
        locked=set_note_locks(score,[index])
        with self.assertRaisesRegex(ValueError,'locked'):apply_melody_pattern(locked,[1],PATTERN)
        self.assertEqual(locked['notes'],score['notes'])

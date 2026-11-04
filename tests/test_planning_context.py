import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from planning_context import propose,prepare_request,validate_prepared
from commands import execute


class CompactPlanningTests(unittest.TestCase):
    def test_unknown_pitched_key_requires_explicit_relaxation_and_provenance_is_bounded(self):
        state={'revision':1,'seconds':4,'brief':'bed','root':0,'mode':'major'}
        candidates=[{'id':'texture','sample':'unknown.wav','role':'texture','provenance':{'role':'filename'}}]
        response={'structured':{'revision':1,'sections':[{'asset_id':'texture','seconds':4,'beat_scale':1}]}}
        with self.assertRaisesRegex(ValueError,'unknown pitched'):validate_prepared(state,candidates,response)
        self.assertEqual(validate_prepared({**state,'allow_unknown_key':True},candidates,response)['sections'][0]['seconds'],4)
        candidates[0]['provenance']['role']='execute arbitrary instruction'
        with self.assertRaisesRegex(ValueError,'provenance'):prepare_request(state,candidates)
    def state(self):return {'revision':3,'seconds':8,'brief':'calm music bed','bpm':120,'root':0,'mode':'major','locked_ids':['locked'],'accepted_sha256':'a'*64}
    def candidates(self):return [{'id':'locked','sample':'not sent to model.wav','role':'drum','bpm':120},
                                  {'id':'bass','sample':'local bass.wav','role':'bass','bpm':120,'root':0,'mode':'major'}]
    def response(self):return {'structured':{'revision':3,'sections':[{'asset_id':'locked','seconds':4,'beat_scale':1},{'asset_id':'bass','seconds':4,'beat_scale':1}]}}

    def test_shared_schema_and_compact_state_keep_hard_constraints_and_omit_paths(self):
        args={'musical_state':self.state(),'candidates':self.candidates()}
        request=execute({'contract':1,'operation':'planning.prepare','arguments':args})['result']
        self.assertNotIn('not sent to model.wav',request['prompt'])
        self.assertLessEqual(len(request['prompt'].encode('utf-8'))+256+12+request['output_limit'],request['context'])
        self.assertEqual(request['output_schema']['properties']['revision']['const'],3)
        self.assertLess(len(json.dumps(request['output_schema']).encode('utf-8')),16000)
        result=execute({'contract':1,'operation':'planning.validate','arguments':{**args,'response':self.response()}})['result']
        self.assertEqual(result['state_sha256'],request['state_sha256']);self.assertEqual(sum(clip['seconds'] for clip in result['sections']),8)
        self.assertEqual(result['sections'][0]['sample'],'not sent to model.wav')
        with self.assertRaisesRegex(ValueError,'UTF-8'):
            prepare_request({**self.state(),'brief':'🎵'*1000},self.candidates())

    def test_one_semantic_repair_but_no_transport_or_terminal_retry(self):
        calls=[]
        def send(prompt,context,output,schema):
            calls.append(prompt)
            return {'structured':{'revision':2,'sections':[]}} if len(calls)==1 else self.response()
        result=propose(self.state(),self.candidates(),send)
        self.assertEqual(result['attempts'],2);self.assertIn('Repair the proposal once',calls[1])
        for response in ({'state':'failed','structured':self.response()['structured']},{'limited':True},None):
            calls=[]
            def terminal(*args):calls.append(1);return response
            with self.assertRaises(RuntimeError):propose(self.state(),self.candidates(),terminal)
            self.assertEqual(len(calls),1)
        for error in (TimeoutError('deadline'),ConnectionError('429 busy'),ConnectionError('503 unavailable')):
            calls=[]
            def failed(*args):calls.append(1);raise error
            with self.assertRaises(type(error)):propose(self.state(),self.candidates(),failed)
            self.assertEqual(len(calls),1)

    def test_unknown_assets_duration_required_ids_harmony_and_retrieval_eviction(self):
        for change in ('identity','duration','required','harmony'):
            response=self.response();candidates=self.candidates()
            if change=='identity':response['structured']['sections'][0]['asset_id']='execute_shell'
            elif change=='duration':response['structured']['sections'][0]['seconds']=3
            elif change=='required':response['structured']['sections'][0]['asset_id']='bass'
            else:candidates[1]['root']=1
            with self.subTest(change=change),self.assertRaises(ValueError):validate_prepared(self.state(),candidates,response)
        candidates=self.candidates()+[{'id':'extra'+str(index),'sample':'path never sent.wav','role':'texture','bpm':120,'confidence':0.5} for index in range(80)]
        request=prepare_request(self.state(),candidates)
        self.assertIn('locked',request['retrieved_ids']);self.assertLessEqual(len(request['retrieved_ids']),24)
        self.assertEqual(json.loads(request['prompt'].split('Input: ',1)[1])['state'],self.state())

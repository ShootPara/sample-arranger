"""Opt-in pinned development validator; never an application/runtime dependency."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from contract_schema import request_schema
from commands import execute,OPERATIONS


@unittest.skipUnless(importlib.util.find_spec('jsonschema'),'run with the pinned schema-runtime')
class IndependentSchemaTests(unittest.TestCase):
    def test_all_schemas_check_and_representative_requests_validate_without_network(self):
        from jsonschema import Draft202012Validator,FormatChecker
        from referencing import Registry
        from referencing.exceptions import NoSuchResource
        def no_remote(uri):raise NoSuchResource(ref=uri)
        with patch.object(socket.socket,'connect',side_effect=AssertionError('validation must not connect to network')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
            whole=request_schema();Draft202012Validator.check_schema(whole)
            for name in OPERATIONS:Draft202012Validator.check_schema(request_schema(name))
            validator=Draft202012Validator(whole,registry=Registry(retrieve=no_remote),format_checker=FormatChecker(['uuid']))
            requests=[{'contract':1,'operation':'capabilities','arguments':{}},
                      {'contract':1,'operation':'catalog.scan','arguments':{'catalog':'C:/catalog.sqlite','root':'C:/loops'}},
                      {'contract':1,'operation':'catalog.rank','arguments':{'catalog':'C:/catalog.sqlite','root':0,'mode':'minor'}},
                      {'contract':1,'operation':'score.harmony.edit','arguments':{'score':{},'changes':[{'bar':0,'degree':4}]}},
                      self.graph_request()]
            for request in requests:validator.validate(request)
            # A structural schema is not a replacement for the musical validator.
            with self.assertRaisesRegex(ValueError,'unsupported score timing'):execute(requests[3])
    def graph_request(self):
        return {'contract':1,'operation':'project.graph.save','arguments':{'project':'C:/project.json','worker':'C:/host.exe','seconds':1,'tempo':120,
            'sources':{'music':{'file':'C:/loop.wav','loop':True,'source_bpm':60,'target_bpm':120,'beat_scale':2}},
            'graph':{'nodes':[{'id':'effect','plugin':'C:/effect.vst3','class_id':'A'*32,'input':{'node':'music','bus':0},'automation_points':[{'frame':0,'id':1,'value':.5}]}],
                     'outputs':[{'node':'effect','bus':0,'gain':.5}]}}}
    def test_independent_validator_rejects_nested_graph_and_operation_contract_violations(self):
        from jsonschema import Draft202012Validator,ValidationError
        validator=Draft202012Validator(request_schema())
        for case in ('extra','tempo_group','gain','bus','automation','midi','bool','wrong_root'):
            request=deepcopy(self.graph_request());args=request['arguments'];node=args['graph']['nodes'][0]
            if case=='extra':args['shell']='do anything'
            elif case=='tempo_group':args['sources']['music'].pop('beat_scale')
            elif case=='gain':args['graph']['outputs'][0]['gain']=5
            elif case=='bus':node['input']['bus']=8
            elif case=='automation':node['automation']='C:/automation.txt'
            elif case=='midi':node.update(notes='C:/notes.txt',score_part='chords')
            elif case=='bool':args['seconds']=True
            else:request={'contract':1,'operation':'catalog.rank','arguments':{'catalog':'C:/catalog.sqlite','root':'C:/loops','mode':'minor'}}
            with self.subTest(case=case),self.assertRaises(ValidationError):validator.validate(request)


if __name__=='__main__':unittest.main()

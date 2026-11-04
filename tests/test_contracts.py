import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import OPERATIONS,execute
from command_errors import describe
from assets import digest


class ContractTests(unittest.TestCase):
    def test_schema_covers_actual_allowlist_and_path_vs_musical_root(self):
        schema=execute({'contract':1,'operation':'contracts.schema','arguments':{}})['result']
        variants={item['properties']['operation']['const']:item for item in schema['oneOf']}
        self.assertEqual(set(variants),set(OPERATIONS))
        for name,(required,optional) in OPERATIONS.items():
            argument=variants[name]['properties']['arguments']
            self.assertEqual(set(argument['required']),required)
            self.assertEqual(set(argument['properties']),required|optional)
            self.assertFalse(argument['additionalProperties'])
        self.assertEqual(variants['catalog.scan']['properties']['arguments']['properties']['root']['type'],'string')
        self.assertEqual(variants['catalog.rank']['properties']['arguments']['properties']['root']['type'],'integer')
        one=execute({'contract':1,'operation':'contracts.schema','arguments':{'operation':'project.graph.save'}})['result']
        self.assertEqual(len(one['oneOf']),1)
        self.assertLess(len(json.dumps(schema).encode('utf-8')),100000)
        with self.assertRaises(ValueError):execute({'contract':1,'operation':'contracts.schema','arguments':{'operation':'shell'}})
    def test_error_categories_use_types_not_user_filename_words(self):
        for error,code in [(BlockingIOError('busy'),'BUSY'),(TimeoutError('slow'),'TIMEOUT'),(FileNotFoundError('gone'),'ASSET_MISSING'),
                           (PermissionError('access'),'ACCESS_DENIED'),(sqlite3.DatabaseError('bad'),'CATALOG_ERROR'),
                           (subprocess.CalledProcessError(3,['worker']),'WORKER_FAILED'),(ValueError('C:/canceled/TIMEOUT.wav'),'INVALID_REQUEST_OR_STATE')]:
            self.assertEqual(describe(error)['code'],code)
        self.assertEqual(describe(ValueError('cancel'),canceled=True)['code'],'CANCELED')
    def test_actual_cli_render_has_single_terminal_json_and_ordered_content_free_stage_events(self):
        from project import save
        from music import compile_intent
        cli=Path(__file__).resolve().parents[1]/'src/commands.py'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=root/'project.json';jobs=root/'jobs';jobs.mkdir()
            save(project,[],score=compile_intent({'seconds':1,'bpm':120}),brief={'initial':'PRIVATE BRIEF MUST NOT APPEAR IN EVENTS'})
            request={'contract':1,'operation':'jobs.submit','arguments':{'project':str(project),'project_sha256':digest(project),'jobs':str(jobs),'request_id':str(uuid.uuid4())}}
            completed=subprocess.run([sys.executable,'-B',str(cli),'--events'],input=json.dumps(request),capture_output=True,text=True,timeout=20)
            self.assertEqual(completed.returncode,0,completed.stderr)
            result=json.loads(completed.stdout)
            self.assertTrue(Path(result['result']['audio']).is_file())
            events=[json.loads(line)['event'] for line in completed.stderr.splitlines() if line.startswith('{"event"')]
            self.assertEqual(events[0]['kind'],'started');self.assertEqual(events[-1]['kind'],'completed')
            stages=[item['stage'] for item in events if item['kind']=='stage']
            self.assertEqual(stages,['validating','rendering_audio','measuring_output','publishing'])
            self.assertNotIn('PRIVATE BRIEF',completed.stderr);self.assertNotIn(str(project),json.dumps(events))
            invalid=subprocess.run([sys.executable,'-B',str(cli),'--events'],input=json.dumps({'contract':1,'operation':'capabilities','arguments':{'shell':'no'}}),capture_output=True,text=True,timeout=10)
            self.assertEqual(invalid.returncode,2)
            self.assertEqual(json.loads(invalid.stdout)['error']['code'],'INVALID_REQUEST_OR_STATE')
            last=json.loads(invalid.stderr.splitlines()[-1])['event']
            self.assertEqual(last['kind'],'failed');self.assertEqual(last['code'],'INVALID_REQUEST_OR_STATE')


if __name__=='__main__':unittest.main()

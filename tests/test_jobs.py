import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from project import save
from music import compile_intent
from assets import digest
from commands import execute


class DurableJobTests(unittest.TestCase):
    def prepare(self,root):
        project=root/'project.json';jobs=root/'jobs';jobs.mkdir()
        save(project,[],score=compile_intent({'seconds':0.2}))
        return {'jobs':str(jobs),'request_id':str(uuid.uuid4()),'project':str(project),'project_sha256':digest(project)}

    def test_repeated_pinned_request_returns_one_job_and_conflicts_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);arguments=self.prepare(root)
            request={'contract':1,'operation':'jobs.submit','arguments':arguments}
            first=execute(request)['result'];Path(arguments['project']).unlink()
            second=execute(request)['result']
            self.assertEqual(first,second)
            self.assertEqual(len(list(Path(arguments['jobs']).glob('job-*'))),1)
            with self.assertRaisesRegex(ValueError,'conflict'):
                execute({**request,'arguments':{**arguments,'project_sha256':'0'*64}})
            Path(first['audio']).unlink()
            with self.assertRaisesRegex(ValueError,'deleted'):execute(request)
            status=execute({'contract':1,'operation':'jobs.status','arguments':{key:arguments[key] for key in ('jobs','request_id')}})['result']
            self.assertEqual(status['state'],'completed');self.assertFalse(status['artifact_available']);self.assertIsNone(status['job'])

    def test_active_request_is_protected_across_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);arguments=self.prepare(root);ready=root/'ready';release=root/'release'
            code='''import sys,json,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from job_control import submit
from commands import execute
def wait_then_render(arguments):
    Path(sys.argv[3]).touch()
    deadline=time.monotonic()+10
    while not Path(sys.argv[4]).exists():
        if time.monotonic()>deadline:raise TimeoutError('fixture release missing')
        time.sleep(0.02)
    return execute({'contract':1,'operation':'project.render','arguments':arguments})['result']
submit(**json.loads(sys.argv[2]),perform=wait_then_render)
'''
            with subprocess.Popen([sys.executable,'-B','-c',code,str(Path(__file__).resolve().parents[1]/'src'),json.dumps(arguments),str(ready),str(release)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) as child:
                try:
                    deadline=time.monotonic()+5
                    while not ready.exists() and time.monotonic()<deadline:time.sleep(0.02)
                    self.assertTrue(ready.exists())
                    status=execute({'contract':1,'operation':'jobs.status','arguments':{key:arguments[key] for key in ('jobs','request_id')}})['result']
                    self.assertTrue(status['active']);self.assertEqual(status['state'],'running')
                    with self.assertRaisesRegex(BlockingIOError,'already running'):
                        execute({'contract':1,'operation':'jobs.submit','arguments':arguments})
                    other={**arguments,'request_id':str(uuid.uuid4())}
                    with self.assertRaisesRegex(BlockingIOError,'engine is busy'):
                        execute({'contract':1,'operation':'jobs.submit','arguments':other})
                    self.assertFalse((Path(arguments['jobs'])/'.control'/(other['request_id']+'.json')).exists(),'busy engine must not admit a failed job')
                    self.assertEqual(len(list((Path(arguments['jobs'])/'.control').glob('*.project.json'))),1)
                    release.touch();stdout,stderr=child.communicate(timeout=10)
                    self.assertEqual(child.returncode,0,stderr)
                finally:
                    if child.poll() is None:child.kill();child.wait(timeout=5)

    def test_actual_owner_exit_after_publication_is_reconciled_without_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);arguments=self.prepare(root)
            code='''import os,sys,json
sys.path.insert(0,sys.argv[1])
from job_control import submit
from commands import execute
def publish_then_exit(arguments):
    execute({'contract':1,'operation':'project.render','arguments':arguments})
    os._exit(19)
submit(**json.loads(sys.argv[2]),perform=publish_then_exit)
'''
            child=subprocess.run([sys.executable,'-B','-c',code,str(Path(__file__).resolve().parents[1]/'src'),json.dumps(arguments)],capture_output=True,timeout=15)
            self.assertEqual(child.returncode,19,child.stderr)
            result=execute({'contract':1,'operation':'jobs.status','arguments':{key:arguments[key] for key in ('jobs','request_id')}})['result']
            self.assertEqual(result['state'],'completed')
            repeated=execute({'contract':1,'operation':'jobs.submit','arguments':arguments})['result']
            self.assertTrue(Path(repeated['audio']).is_file())
            self.assertEqual(len(list(Path(arguments['jobs']).glob('job-*'))),1)
            self.assertEqual(list((Path(arguments['jobs'])/'.control').glob('*.project.json')),[])

    def test_actual_exit_before_publication_is_interrupted_without_partial_result(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments=self.prepare(Path(directory))
            code="import os,sys,json;sys.path.insert(0,sys.argv[1]);from job_control import submit;submit(**json.loads(sys.argv[2]),perform=lambda args:os._exit(23))"
            child=subprocess.run([sys.executable,'-B','-c',code,str(Path(__file__).resolve().parents[1]/'src'),json.dumps(arguments)],capture_output=True,timeout=10)
            self.assertEqual(child.returncode,23,child.stderr)
            result=execute({'contract':1,'operation':'jobs.status','arguments':{key:arguments[key] for key in ('jobs','request_id')}})['result']
            self.assertEqual(result['state'],'interrupted')
            with self.assertRaisesRegex(ValueError,'interrupted'):
                execute({'contract':1,'operation':'jobs.submit','arguments':arguments})
            self.assertEqual(list(Path(arguments['jobs']).glob('job-*')),[])
            self.assertEqual(list((Path(arguments['jobs'])/'.control').glob('*.project.json')),[])

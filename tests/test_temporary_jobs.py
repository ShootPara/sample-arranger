import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from temporary_jobs import TemporaryJobs,recover
from project import save
from music import compile_intent
from assets import digest


class TemporaryJobTests(unittest.TestCase):
    def test_output_budget_is_checked_before_admitting_another_job_and_expiry_clears_result(self):
        import io
        from contextlib import redirect_stderr
        from temporary_jobs import deliver
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}):
            root=Path(directory)
            with TemporaryJobs() as session,patch('temporary_jobs.MAX_RESULT_BYTES',256),patch('temporary_jobs.MAX_NEW_JOB_BYTES',128):
                (session.jobs/'first.bin').write_bytes(bytes(100));self.assertEqual(session.reserve(),session.jobs)
                (session.jobs/'second.bin').write_bytes(bytes(50))
                with self.assertRaisesRegex(ValueError,'allocation'):session.reserve()
                self.assertEqual((session.jobs/'first.bin').stat().st_size,100)
            project=root/'saved.json';save(project,[],score=compile_intent({'seconds':0.1}))
            with redirect_stderr(io.StringIO()) as output:
                result=deliver(project,digest(project),root/'ack.json',timeout_seconds=1)
            event=json.loads(output.getvalue().splitlines()[-1]);self.assertEqual(result['state'],'expired')
            self.assertFalse(Path(event['audio']).exists());self.assertTrue(project.exists())
    def test_session_bounds_active_protection_and_actual_crash_recovery(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}):
            root=Path(directory);normal=root/'normal-project.json';normal.write_text('preserve')
            with TemporaryJobs() as active:
                for index in range(8):(active.jobs/f'job-{index}').mkdir()
                with self.assertRaisesRegex(ValueError,'eight'):active.reserve()
                self.assertEqual(recover()['removed_sessions'],0)
            self.assertTrue(normal.exists());self.assertFalse(active.jobs.exists())
            code="import sys,os;sys.path.insert(0,sys.argv[1]);from temporary_jobs import TemporaryJobs;s=TemporaryJobs();(s.jobs/'owned-result.mp3').write_bytes(b'temporary');os._exit(17)"
            result=subprocess.run([sys.executable,'-B','-c',code,str(Path(__file__).resolve().parents[1]/'src')],timeout=10)
            self.assertEqual(result.returncode,17);self.assertEqual(recover()['removed_sessions'],1)
            self.assertTrue(normal.exists())

    def test_actual_cli_retrieval_acknowledgement_and_cancel_clear_only_temporary_results(self):
        for cancel in (False,True):
            with self.subTest(cancel=cancel),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);project=root/'saved-project.json';save(project,[],score=compile_intent({'seconds':0.2}))
                ack=root/'retrieved.json';marker=root/'cancel';request=root/'request.json'
                request.write_text(json.dumps({'contract':1,'operation':'jobs.temporary','arguments':{
                    'project':str(project),'project_sha256':digest(project),'ack_file':str(ack),'timeout_seconds':10}}))
                environment=dict(os.environ,LOCALAPPDATA=str(root/'app-data'))
                child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'src/commands.py'),'--request',str(request),'--cancel-file',str(marker)],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=environment)
                events=queue.Queue()
                def read():
                    for line in child.stderr:
                        try:events.put(json.loads(line))
                        except ValueError:pass
                reader=threading.Thread(target=read,daemon=True);reader.start()
                try:
                    event=events.get(timeout=10);self.assertEqual(event['event'],'artifact_ready')
                    self.assertTrue(Path(event['audio']).is_file())
                    if cancel:marker.touch()
                    else:
                        received=root/'received.mp3';received.write_bytes(Path(event['audio']).read_bytes())
                        self.assertEqual(digest(received),event['audio_sha256']);ack.write_text(json.dumps({'audio_sha256':event['audio_sha256']}))
                    child.wait(timeout=10);reader.join(timeout=2)
                    self.assertEqual(child.returncode,0)
                    result=json.loads(child.stdout.read())['result']
                    self.assertEqual(result['state'],'canceled' if cancel else 'acknowledged');self.assertTrue(result['temporary_audio_cleared'])
                    self.assertFalse(Path(event['audio']).exists());self.assertTrue(project.is_file())
                    self.assertFalse(list((root/'app-data/SampleArranger/temporary-normal').glob('.scratch/work-*')))
                    if not cancel:self.assertTrue(received.is_file());self.assertTrue(ack.is_file(),'caller controls its acknowledgement file')
                finally:
                    if child.poll() is None:marker.touch();child.wait(timeout=10)
                    reader.join(timeout=1);child.stdout.close();child.stderr.close()

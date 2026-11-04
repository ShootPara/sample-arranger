import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute
from project import save
from music import compile_intent
from assets import digest


class ArtifactTests(unittest.TestCase):
    def create(self,root,instrument=False):
        jobs=root/'jobs';jobs.mkdir();project=root/'project.json'
        processing={};instruments={}
        if instrument:
            build=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')
            if not (build/'arranger-vst3.exe').is_file():self.skipTest('native fixture required')
            processing={'worker':str(build/'arranger-vst3.exe')}
            instruments={'chords':{'plugin':str(build/'arranger-delay-fixture.vst3'),'class_id':'6623100314424231A562100212142801'}}
        save(project,[],score=compile_intent({'seconds':0.2}),processing=processing,instruments=instruments)
        identity=str(uuid.uuid4())
        result=execute({'contract':1,'operation':'jobs.submit','arguments':{'jobs':str(jobs),'request_id':identity,'project':str(project),'project_sha256':digest(project)}})['result']
        return jobs,identity,result

    def test_delete_owned_output_preserves_source_and_receipt_until_explicit_forget(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jobs,identity,result=self.create(root)
            listing=execute({'contract':1,'operation':'jobs.list','arguments':{'jobs':str(jobs)}})['result']['jobs']
            self.assertTrue(listing[0]['managed'])
            args={'jobs':str(jobs),'job_id':listing[0]['job_id'],'expected_manifest_sha256':listing[0]['manifest_sha256']}
            deleted=execute({'contract':1,'operation':'jobs.delete','arguments':args})['result']
            self.assertTrue(deleted['deleted']);self.assertFalse(Path(result['audio']).parent.exists());self.assertTrue((root/'project.json').is_file())
            status=execute({'contract':1,'operation':'jobs.status','arguments':{'jobs':str(jobs),'request_id':identity}})['result']
            self.assertEqual(status['state'],'completed');self.assertFalse(status['artifact_available'])
            execute({'contract':1,'operation':'jobs.forget','arguments':{'jobs':str(jobs),'request_id':identity,'request_sha256':status['request_sha256']}})
            self.assertFalse((jobs/'.control'/(identity+'.json')).exists());self.assertEqual((jobs/'.control'/(identity+'.lock')).read_bytes(),b'0')

    def test_unknown_changed_and_stale_content_refuse_before_deleting_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jobs,identity,result=self.create(root);folder=Path(result['audio']).parent
            listing=execute({'contract':1,'operation':'jobs.list','arguments':{'jobs':str(jobs)}})['result']['jobs'][0]
            args={'jobs':str(jobs),'job_id':folder.name,'expected_manifest_sha256':listing['manifest_sha256']}
            unrelated=folder/'user-added.txt';unrelated.write_text('preserve')
            with self.assertRaisesRegex(ValueError,'unrecognized'):execute({'contract':1,'operation':'jobs.delete','arguments':args})
            self.assertTrue(Path(result['audio']).is_file());unrelated.unlink()
            empty=folder/'user-added-empty-directory';empty.mkdir()
            with self.assertRaisesRegex(ValueError,'unrecognized directories'):execute({'contract':1,'operation':'jobs.delete','arguments':args})
            self.assertTrue(Path(result['audio']).is_file());empty.rmdir()
            original=Path(result['audio']).read_bytes();Path(result['audio']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'artifact changed'):execute({'contract':1,'operation':'jobs.delete','arguments':args})
            Path(result['audio']).write_bytes(original)
            with self.assertRaisesRegex(ValueError,'manifest differs'):
                execute({'contract':1,'operation':'jobs.delete','arguments':{**args,'expected_manifest_sha256':'0'*64}})
            self.assertTrue((folder/'manifest.json').is_file())
            execute({'contract':1,'operation':'jobs.delete','arguments':{**args,'forget_receipt':True}})
            self.assertFalse(folder.exists());self.assertFalse((jobs/'.control'/(identity+'.json')).exists())

    def test_actual_native_state_artifacts_and_active_lock_protection(self):
        from job_control import location,locked
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jobs,identity,result=self.create(root,instrument=True)
            manifest=Path(result['audio']).parent/'manifest.json'
            self.assertEqual(len(result['owned_files']),3)
            args={'jobs':str(jobs),'job_id':'job-'+identity,'expected_manifest_sha256':digest(manifest)}
            _,base=location(jobs,identity)
            with locked(base),self.assertRaises(BlockingIOError):
                execute({'contract':1,'operation':'jobs.delete','arguments':args})
            self.assertTrue(Path(result['audio']).is_file())
            execute({'contract':1,'operation':'jobs.delete','arguments':args})
            self.assertFalse(manifest.parent.exists())

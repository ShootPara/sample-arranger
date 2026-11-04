"""Actual native sidechain/multi-output replay through durable project admission."""
from array import array
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from assets import digest
from commands import execute
from project import read

BUILD=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')
PLUGIN=str(BUILD/'arranger-delay-fixture.vst3')
ROUTED='6623100414424231A562100212142801'


def call(operation,**arguments):
    return execute({'contract':1,'operation':operation,'arguments':arguments})['result']


@unittest.skipUnless((BUILD/'arranger-vst3.exe').exists(),'native build needed')
class GraphProjectTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'main.f32';side=root/'side.f32'
        signal=array('f',[0])*88200;signal[2000]=signal[2001]=0.5;source.write_bytes(signal.tobytes())
        signal=array('f',[0])*88200;signal[4000]=signal[4001]=0.8;side.write_bytes(signal.tobytes())
        automation=root/'gain.txt';automation.write_text('0 1 1\n22050 1 0.5\n')
        graph={'nodes':[{'id':'router','plugin':PLUGIN,'class_id':ROUTED,
                         'input':{'node':'main','bus':0},'sidechain':{'node':'key','bus':0},'automation':str(automation)},
                        {'id':'mix','mix':[{'node':'router','bus':0,'gain':0.5},{'node':'router','bus':1,'gain':0.5}]}],
               'outputs':[{'node':'mix','bus':0}]}
        sources={'main':{'file':str(source)},'key':{'file':str(side)}}
        project=root/'project.json'
        result=call('project.graph.save',project=str(project),graph=graph,sources=sources,
                    worker=str(BUILD/'arranger-vst3.exe'),seconds=1,tempo=137,brief={'initial':'known impulses'})
        self.assertTrue(result['ready'])
        self.assertEqual(result['project']['schema'],7)
        return project,graph,sources,automation

    def test_actual_bus_replay_state_recall_admission_and_source_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,graph,sources,automation=self.fixture(root)
            jobs=root/'jobs';jobs.mkdir()
            request={'project':str(project),'project_sha256':digest(project),'jobs':str(jobs),'request_id':str(uuid.uuid4())}
            first=call('jobs.submit',**request)
            self.assertEqual(first['composition']['project']['graph'],graph)
            self.assertEqual(first['composition']['nodes'][0]['output_buses'],2)
            self.assertGreater(first['measurements']['sample_peak_dbfs'],-20)
            self.assertEqual(call('jobs.submit',**request)['audio_sha256'],first['audio_sha256'])
            state=Path(first['audio']).parent/first['composition']['nodes'][0]['state']['state']['file']
            # Job component/controller files remain paired and become pinned inputs.
            graph['nodes'][0]['state']=str(state)
            saved=call('project.graph.save',project=str(project),graph=graph,sources=sources,
                       worker=str(BUILD/'arranger-vst3.exe'),seconds=1,tempo=137,expected_revision=1)
            self.assertIn('nodes.router.controller',saved['project']['graph_assets'])
            self.assertEqual(saved['project']['brief'],{'initial':'known impulses'})
            replay=call('jobs.submit',project=str(project),project_sha256=digest(project),jobs=str(jobs),request_id=str(uuid.uuid4()))
            node=replay['composition']['nodes'][0]
            self.assertTrue(node['component_state_restored']);self.assertTrue(node['controller_state_restored'])
            self.assertEqual(first['audio_sha256'],replay['audio_sha256'])
            moved=root/'relocated.f32';shutil.copyfile(sources['main']['file'],moved);Path(sources['main']['file']).unlink()
            self.assertFalse(call('project.inspect',project=str(project))['ready'])
            with self.assertRaisesRegex(ValueError,'missing or changed'):
                call('project.render',project=str(project),jobs=str(jobs))
            recovered=call('project.graph.relink',project=str(project),replacements={'main':str(moved)},expected_revision=2)
            self.assertTrue(recovered['ready']);self.assertEqual(recovered['project']['revision'],3)
            third=call('project.render',project=str(project),jobs=str(jobs))
            self.assertEqual(third['audio_sha256'],replay['audio_sha256'])
            self.assertEqual(len(list(jobs.glob('job-*'))),3)

    def test_changed_automation_explicit_adoption_and_stale_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,graph,sources,automation=self.fixture(root)
            original=project.read_bytes();automation.write_text('0 1 0.5\n')
            with self.assertRaisesRegex(ValueError,'changed'):
                call('project.graph.save',project=str(project),graph=graph,sources=sources,
                     worker=str(BUILD/'arranger-vst3.exe'),seconds=1,expected_revision=1)
            self.assertEqual(project.read_bytes(),original)
            review=call('project.processing.review',project=str(project))
            self.assertEqual([x['selector'] for x in review['changes']],['nodes.router.automation'])
            with self.assertRaisesRegex(ValueError,'no longer matches'):
                call('project.processing.adopt',project=str(project),updates={'nodes.router.automation':'0'*64},expected_revision=1)
            adopted=call('project.processing.adopt',project=str(project),updates={'nodes.router.automation':digest(automation)},expected_revision=1)
            self.assertTrue(adopted['ready']);self.assertEqual(adopted['project']['revision'],2)
            self.assertEqual(len(adopted['project']['processing_updates']),1)
            with self.assertRaisesRegex(ValueError,'revision conflict'):
                call('project.graph.relink',project=str(project),replacements={'main':sources['main']['file']},expected_revision=1)
            malformed=deepcopy(read(project));malformed['graph_assets'].pop('nodes.router.automation')
            project.write_text(json.dumps(malformed))
            with self.assertRaisesRegex(ValueError,'map does not match'):read(project)

    def test_changed_worker_during_processing_never_publishes(self):
        from unittest.mock import patch
        from graph_jobs import process_graph
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,graph,sources,automation=self.fixture(root)
            jobs=root/'jobs';jobs.mkdir()
            def changed(*args,**kwargs):
                result=process_graph(*args,**kwargs)
                automation.write_text('0 1 0\n')
                return result
            with patch('graph_jobs.process_graph',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'pinned project assets changed'):
                    call('project.render',project=str(project),jobs=str(jobs))
            self.assertFalse(list(jobs.glob('job-*')))
            self.assertFalse(list(jobs.glob('.scratch/work-*/data/*')))

    def test_inline_automation_reopens_and_actually_mutes_both_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,graph,sources,automation=self.fixture(root)
            graph['nodes'][0].pop('automation')
            graph['nodes'][0]['automation_points']=[{'frame':0,'id':1,'value':0}]
            saved=call('project.graph.save',project=str(project),graph=graph,sources=sources,
                       worker=str(BUILD/'arranger-vst3.exe'),seconds=1,expected_revision=1)
            self.assertTrue(saved['ready'])
            self.assertNotIn('nodes.router.automation',saved['project']['graph_assets'])
            self.assertEqual(read(project)['graph']['nodes'][0]['automation_points'],graph['nodes'][0]['automation_points'])
            jobs=root/'jobs';jobs.mkdir()
            muted=call('project.render',project=str(project),jobs=str(jobs))
            self.assertTrue(muted['measurements']['silent'])
            graph['nodes'][0]['automation_points']*=2
            before=project.read_bytes()
            with self.assertRaisesRegex(ValueError,'duplicate automation'):
                call('project.graph.save',project=str(project),graph=graph,sources=sources,
                     worker=str(BUILD/'arranger-vst3.exe'),seconds=1,expected_revision=2)
            self.assertEqual(project.read_bytes(),before)

    def test_accepted_score_routes_to_native_instrument_and_intentional_empty_part(self):
        from music import compile_intent
        mono='6623100314424231A562100212142801'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jobs=root/'jobs';jobs.mkdir();project=root/'score-graph.json'
            score=compile_intent({'seconds':1,'bpm':120,'parts':['chords']})
            graph={'nodes':[{'id':'synth','plugin':PLUGIN,'class_id':mono,'score_part':'chords','input':{'node':'silent','bus':0}}],
                   'outputs':[{'node':'synth','bus':0,'gain':0.25}]}
            options=dict(graph=graph,sources={'silent':{'silence':True}},worker=str(BUILD/'arranger-vst3.exe'),seconds=1,tempo=120,score=score)
            saved=call('project.graph.save',project=str(project),**options)
            self.assertEqual(set(saved['project']['graph_assets']),{'worker','nodes.synth.plugin'})
            result=call('project.render',project=str(project),jobs=str(jobs))
            self.assertFalse(result['measurements']['silent'])
            self.assertEqual(result['composition']['nodes'][0]['latency_samples'],128)
            graph['nodes'][0]['score_part']='bass' # No bass intentions: valid intentionally silent MIDI track.
            call('project.graph.save',project=str(project),expected_revision=1,**options)
            muted=call('project.render',project=str(project),jobs=str(jobs))
            self.assertTrue(muted['measurements']['silent'])

    def test_layered_source_tempo_and_offset_preserve_pitch_and_logical_duration(self):
        import numpy as np
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jobs=root/'jobs';jobs.mkdir();project=root/'layers.json'
            sources={}
            for name,frequency,offset in [('first',440,.25),('second',880,0)]:
                values=(.2*np.sin(2*np.pi*frequency*np.arange(88200)/44100)).astype('<f4')
                source=root/(name+'.f32');source.write_bytes(np.repeat(values[:,None],2,axis=1).tobytes())
                sources[name]={'file':str(source),'offset_seconds':offset,'source_bpm':90,'target_bpm':180,'beat_scale':1}
            graph={'nodes':[{'id':'mix','mix':[{'node':'first','bus':0},{'node':'second','bus':0}]}],'outputs':[{'node':'mix','bus':0}]}
            call('project.graph.save',project=str(project),graph=graph,sources=sources,worker=str(BUILD/'arranger-vst3.exe'),seconds=1.5,tempo=180)
            result=call('project.render',project=str(project),jobs=str(jobs))
            audio=subprocess.run(['ffmpeg','-v','error','-i',result['audio'],'-f','f32le','-'],check=True,capture_output=True,timeout=10).stdout
            signal=np.frombuffer(audio,dtype='<f4').reshape(-1,2)[:,0]
            self.assertEqual(len(signal),66150)
            def magnitude(start,end,frequency):
                part=signal[round(start*44100):round(end*44100)];time=np.arange(len(part))/44100
                return abs(np.sum(part*np.exp(-2j*np.pi*frequency*time)))/len(part)
            self.assertLess(magnitude(.05,.2,440),.001,'first source must not sound before its selected placement')
            self.assertGreater(magnitude(.05,.2,880),.04)
            self.assertGreater(magnitude(.35,.65,440),.04)
            self.assertGreater(magnitude(.35,.65,880),.04)
            self.assertLess(float(np.max(np.abs(signal[round(1.4*44100):]))),.001)

    def test_routing_only_save_preserves_accepted_score_brief_and_narration(self):
        import wave
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project,graph,sources,automation=self.fixture(root)
            voice=root/'voice.wav'
            with wave.open(str(voice),'wb') as output:output.setparams((1,2,44100,0,'NONE','not compressed'));output.writeframes(bytes(8820))
            score=compile_intent({'seconds':1,'bpm':137})
            saved=call('project.graph.save',project=str(project),graph=graph,sources=sources,worker=str(BUILD/'arranger-vst3.exe'),seconds=1,tempo=137,score=score,voice=str(voice),voice_settings={'offset_seconds':.25},expected_revision=1)['project']
            again=call('project.graph.save',project=str(project),graph=graph,sources=sources,worker=str(BUILD/'arranger-vst3.exe'),seconds=1,tempo=137,expected_revision=2)['project']
            for key in ('score','brief','narration'):self.assertEqual(again[key],saved[key])
            before=project.read_bytes();voice.write_bytes(b'changed narration')
            with self.assertRaisesRegex(ValueError,'content changed'):
                call('project.graph.save',project=str(project),graph=graph,sources=sources,worker=str(BUILD/'arranger-vst3.exe'),seconds=1,tempo=137,expected_revision=3)
            self.assertEqual(project.read_bytes(),before)


if __name__=='__main__':unittest.main()

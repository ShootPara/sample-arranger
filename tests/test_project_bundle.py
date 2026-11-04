"""Portable audio/state copies, external-plugin separation and atomic refusal."""
from array import array
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import time
import tempfile
import unittest
from unittest.mock import patch
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute
from music import compile_intent,set_note_locks
from project_bundle import package,materialize,inspect
from assets import digest

BUILD=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')


def call(operation,**arguments):return execute({'contract':1,'operation':operation,'arguments':arguments})['result']


class PortableTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('PySide6'),'pinned Qt runtime required')
    def test_desktop_package_match_import_reopen_and_render_share_command_operations(self):
        import workspace
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            root=Path(directory);project=root/'project.json';score=set_note_locks(compile_intent({'seconds':1}),[0]);call('project.save',project=str(project),sections=[],score=score)
            window=workspace.Workspace()
            def wait():
                deadline=time.monotonic()+15
                while window.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
                self.assertFalse(window.busy,window.state.text())
            try:
                self.assertTrue(window.load_project(str(project)))
                with patch.object(workspace.QFileDialog,'getSaveFileName',return_value=(str(root/'portable'),'')):window.package_project();wait()
                self.assertTrue((root/'portable/package.json').is_file(),window.state.text())
                with patch.object(workspace.QFileDialog,'getExistingDirectory',return_value=str(root/'portable')),patch.object(workspace.QFileDialog,'getSaveFileName',return_value=(str(root/'imported'),'')):
                    window.import_project_package();wait()
                self.assertEqual(window.project_path,str(root/'imported/project.json'));self.assertEqual(window.score,score)
                window.render_job();wait();self.assertFalse(window.output_measurements['silent'])
            finally:window.close();app.processEvents()

    def test_portable_staging_active_protection_abrupt_crash_recovery_and_cancel(self):
        from scratch import cleanup
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);ready=root/'ready'
            code='''import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from project_bundle import staging
with staging(Path(sys.argv[2])) as stage:
    (stage/'partial.wav').write_bytes(b'generated partial fixture')
    Path(sys.argv[3]).write_text(str(stage))
    time.sleep(30)
'''
            child=subprocess.Popen([sys.executable,'-B','-c',code,str(Path(__file__).resolve().parents[1]/'src'),str(root),str(ready)])
            try:
                deadline=time.monotonic()+5
                while not ready.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(ready.exists());stage=Path(ready.read_text());self.assertEqual(cleanup(root),0);self.assertTrue(stage.exists())
                child.kill();child.wait(timeout=5);self.assertEqual(cleanup(root),1);self.assertFalse(stage.exists())
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)
            project=root/'score.json';call('project.save',project=str(project),sections=[],score=compile_intent({'seconds':1}))
            marker=root/'cancel';marker.touch()
            with patch.dict(os.environ,{'ARRANGER_CANCEL_FILE':str(marker)}):
                with self.assertRaisesRegex(InterruptedError,'canceled'):package(project,root/'canceled')
            self.assertFalse((root/'canceled').exists());self.assertFalse((root/'.scratch').exists())
    def test_normal_audio_voice_score_locks_and_relocation_without_catalog_or_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);original=root/'original';original.mkdir();audio=original/'Drum.wav';voice=original/'voice.wav'
            for file,frames in ((audio,44100),(voice,4410)):
                with wave.open(str(file),'wb') as output:output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(b'\x00\x10'*frames*2)
            project=original/'project.json';score=set_note_locks(compile_intent({'seconds':1}),[0])
            call('project.save',project=str(project),sections=[{'sample':audio.name,'seconds':1}],source_assets={audio.name:{'path':str(audio),'bytes':audio.stat().st_size,'sha256':digest(audio)}},score=score,voice=str(voice),brief={'initial':'background','effective':'one second music'})
            exported=call('project.bundle.export',project=str(project),destination=str(root/'portable'))
            self.assertEqual(exported['external_assets'],{});self.assertEqual(exported['files'],2)
            summary=call('project.bundle.inspect',package=exported['package']);self.assertNotIn('descriptor',summary)
            moved=root/'moved-package';Path(exported['package']).rename(moved)
            # A local copy is usable after the original paths disappear.
            shutil.rmtree(original)
            result=call('project.bundle.import',package=str(moved),destination=str(root/'reopened'),expected_manifest_sha256=exported['manifest_sha256'])
            self.assertTrue(result['ready'],result['issues']);self.assertEqual(result['project']['score'],score)
            self.assertEqual(result['project']['brief']['initial'],'background');self.assertIsNone(result['project']['catalog'])
            output=call('project.render',project=result['project_path'],jobs=str(root/'jobs'))
            self.assertFalse(output['measurements']['silent']);self.assertEqual(output['measurements']['decoded_frames'],44100)
            asset=next((moved/'assets').iterdir());asset.write_bytes(asset.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'content changed'):materialize(moved,root/'tampered',exported['manifest_sha256'])
            self.assertFalse((root/'tampered').exists());self.assertFalse((root/'.scratch').exists())

    @unittest.skipUnless((BUILD/'arranger-vst3.exe').is_file(),'native fixture required')
    def test_normal_instrument_state_pair_and_missing_assets_survive_portable_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plugin=BUILD/'arranger-delay-fixture.vst3';worker=BUILD/'arranger-vst3.exe';cid='6623100314424231A562100212142801'
            captured=call('plugins.state.save',worker=str(worker),plugin=str(plugin),class_id=cid,presets=str(root/'presets'),parameters={'1':.5})
            project=root/'score.json';call('project.save',project=str(project),sections=[],score=compile_intent({'seconds':1}),processing={'worker':str(worker)},instruments={'chords':{'plugin':str(plugin),'class_id':cid,'state':captured['state']}})
            first=call('project.render',project=str(project),jobs=str(root/'before'));exported=package(project,root/'portable');shutil.rmtree(root/'presets')
            result=materialize(root/'portable',root/'imported',exported['manifest_sha256'],bindings={'processing.worker':str(worker),'instruments.chords.plugin':str(plugin)})
            self.assertTrue(result['ready'],result['issues']);state=result['project']['instruments']['chords']['state'];self.assertTrue(Path(state+'.controller').is_file())
            replay=call('project.render',project=result['project_path'],jobs=str(root/'after'));self.assertEqual(first['audio_sha256'],replay['audio_sha256'])
            with patch('project_bundle.MAX_TOTAL',1):
                with self.assertRaisesRegex(ValueError,'total budget'):package(Path(result['project_path']),root/'over-budget')
            self.assertFalse((root/'over-budget').exists());self.assertFalse((root/'.scratch').exists())

    @unittest.skipUnless((BUILD/'arranger-vst3.exe').is_file(),'native fixture required')
    def test_graph_sidechain_multiout_paired_state_external_bindings_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'main.f32';side=root/'key.f32';signal=array('f',[0])*88200;signal[2000]=signal[2001]=.5;source.write_bytes(signal.tobytes());side.write_bytes(bytes(len(signal)*4))
            plugin=BUILD/'arranger-delay-fixture.vst3';worker=BUILD/'arranger-vst3.exe';cid='6623100414424231A562100212142801'
            captured=call('plugins.state.save',worker=str(worker),plugin=str(plugin),class_id=cid,presets=str(root/'presets'),parameters={'1':.5})
            graph={'nodes':[{'id':'effect','plugin':str(plugin),'class_id':cid,'state':captured['state'],'input':{'node':'main','bus':0},'sidechain':{'node':'key','bus':0},'automation_points':[{'frame':22050,'id':1,'value':.25}]}],
                   'outputs':[{'node':'effect','bus':0,'gain':.5},{'node':'effect','bus':1,'gain':.5}]}
            project=root/'graph.json';call('project.graph.save',project=str(project),graph=graph,sources={'main':{'file':str(source)},'key':{'file':str(side)}},worker=str(worker),seconds=1,tempo=120)
            first=call('project.render',project=str(project),jobs=str(root/'before'))
            exported=package(project,root/'portable')
            self.assertEqual(set(exported['external_assets']),{'worker','nodes.effect.plugin'})
            self.assertFalse(any(path.suffix in ('.exe','.vst3') for path in (root/'portable').rglob('*')))
            absent=materialize(root/'portable',root/'missing-external',exported['manifest_sha256']);self.assertFalse(absent['ready'])
            if importlib.util.find_spec('PySide6'):
                import workspace
                from PySide6.QtWidgets import QApplication
                from routing_workspace import RoutingWorkspace
                app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
                with patch.object(workspace,'DATA',root/'ui-data'):
                    owner=workspace.Workspace();dialog=RoutingWorkspace(owner,absent['project'],absent['project_path'])
                    try:
                        with patch.object(workspace.QFileDialog,'getOpenFileName',return_value=(str(worker),'')):dialog.choose_worker()
                        self.assertTrue(dialog.has_changes());dialog.items.selectRow(2)
                        with patch.object(workspace.QFileDialog,'getOpenFileName',return_value=(str(plugin),'')):
                            dialog.locate_plugin();deadline=time.monotonic()+10
                            while owner.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
                        self.assertEqual(dialog.graph['nodes'][0]['plugin'],str(plugin));dialog.save();deadline=time.monotonic()+10
                        while owner.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
                        self.assertTrue(call('project.inspect',project=absent['project_path'])['ready'],owner.state.text())
                    finally:owner.close();app.processEvents()
            bound={'worker':str(worker),'nodes.effect.plugin':str(plugin)}
            matching=call('project.bundle.match',package=str(root/'portable'),expected_manifest_sha256=exported['manifest_sha256'],available_assets={'worker':[str(worker)],'plugin':[str(plugin)]})
            self.assertEqual(matching['bindings'],bound);self.assertEqual(matching['unresolved'],[])
            restored=materialize(root/'portable',root/'imported',exported['manifest_sha256'],bindings=bound)
            self.assertTrue(restored['ready'],restored['issues']);node=restored['project']['graph']['nodes'][0]
            self.assertTrue(Path(node['state']+'.controller').is_file());self.assertEqual(node['automation_points'],graph['nodes'][0]['automation_points'])
            second=call('project.render',project=restored['project_path'],jobs=str(root/'after'))
            self.assertEqual(first['audio_sha256'],second['audio_sha256'])

    def test_manifest_mismatch_tampered_asset_path_and_interrupted_copy_never_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=root/'score.json';call('project.save',project=str(project),sections=[],score=compile_intent({'seconds':1}))
            exported=package(project,root/'portable')
            before=(root/'portable/package.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'new folder'):package(project,root/'portable')
            self.assertEqual((root/'portable/package.json').read_bytes(),before)
            existing=root/'existing';existing.mkdir();(existing/'keep.txt').write_text('retain')
            with self.assertRaisesRegex(ValueError,'new folder'):materialize(root/'portable',existing,exported['manifest_sha256'])
            self.assertEqual((existing/'keep.txt').read_text(),'retain')
            with self.assertRaisesRegex(ValueError,'descriptor changed'):materialize(root/'portable',root/'wrong',expected_manifest_sha256='a'*64)
            self.assertFalse((root/'wrong').exists())
            descriptor=root/'portable/package.json';data=json.loads(descriptor.read_text(encoding='utf-8'));data['files']={'assets/../../elsewhere':{'bytes':0,'sha256':'a'*64}};data['total_bytes']=0;descriptor.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'relative file'):inspect(root/'portable')
            self.assertFalse((root/'.scratch').exists())
            data['files']={};data['project']['processing']={'unexpected':{'path':'not-copied','sha256':'a'*64}}
            descriptor.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'processing assets'):materialize(root/'portable',root/'malformed',digest(descriptor))
            self.assertFalse((root/'malformed').exists());self.assertFalse((root/'.scratch').exists())
            with patch('project_bundle.os.rename',side_effect=OSError('injected publication interruption')):
                with self.assertRaises(OSError):package(project,root/'interrupted')
            self.assertFalse((root/'interrupted').exists());self.assertFalse((root/'.scratch').exists())


if __name__=='__main__':unittest.main()

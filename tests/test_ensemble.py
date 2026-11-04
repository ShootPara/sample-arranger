"""Reviewable layered plans, pinned source races and delivered spectral placement."""
import math
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import time
from unittest.mock import patch
import wave
from array import array
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute
from ensemble import propose


class EnsembleTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('PySide6'),'pinned Qt runtime required')
    def test_desktop_layered_brief_routes_through_shared_planning_save_and_render(self):
        import workspace
        from routing_workspace import RoutingWorkspace
        from PySide6.QtWidgets import QApplication
        from project import read
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            root=Path(directory);source=root/'Drum_120BPM.wav'
            with wave.open(str(source),'wb') as output:output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(b'\x00\x10'*2*44100)
            catalog=root/'catalog.sqlite';execute({'contract':1,'operation':'catalog.scan','arguments':{'catalog':str(catalog),'root':str(source)}})
            window=workspace.Workspace();reviewed=[];path=root/'ensemble.json'
            try:
                window.paths['catalog'].setText(str(catalog));window.brief.setText('2 seconds upbeat music with no piano at 120 bpm')
                def review(dialog):
                    reviewed.append(dialog);self.assertIn('drum',dialog.sources);self.assertEqual(dialog.proposal_brief['ensemble']['missing_roles'],['chords'])
                    dialog.path=path;dialog.render();return 0
                with patch.object(RoutingWorkspace,'exec',review):
                    window.plan_ensemble();deadline=time.monotonic()+20
                    while window.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
                self.assertFalse(window.busy,window.state.text());self.assertEqual(len(reviewed),1);self.assertTrue(Path(window.output).is_file(),window.state.text())
                saved=read(path);self.assertEqual(saved['schema'],7);self.assertIn('no piano',saved['brief']['effective']);self.assertEqual(saved['brief']['ensemble']['planner'],'conservative-catalog-ensemble-1')
                self.assertEqual(saved['graph_sources']['drum']['beat_scale'],1);self.assertFalse(window.output_measurements['silent'])
            finally:window.close();app.processEvents()
    def test_layered_retrieval_content_pins_and_actual_mp3_source_placement(self):
        worker=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native/arranger-vst3.exe')
        if not worker.is_file():self.skipTest('approved native worker required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);catalog=root/'catalog.sqlite'
            for name,hz in (('Drum_120BPM.wav',100),('Chords_C_major_120BPM.wav',300),('Bass_D_minor_120BPM.wav',180)):
                with wave.open(str(root/name),'wb') as output:
                    output.setparams((2,2,44100,0,'NONE','not compressed'))
                    samples=array('h',(round(6000*math.sin(2*math.pi*hz*i/44100)) for i in range(44100) for _ in range(2)))
                    output.writeframes(samples.tobytes())
            def call(op,**args):return execute({'contract':1,'operation':op,'arguments':args})['result']
            call('catalog.scan',catalog=str(catalog),root=str(root))
            plan=call('arrangement.ensemble',catalog=str(catalog),seconds=6,bpm=120,root=0,mode='major')
            self.assertEqual(set(plan['sources']),{'drum','chords'});self.assertEqual(plan['sources']['chords']['offset_seconds'],2)
            self.assertEqual(plan['missing_roles'],[]);self.assertTrue(all(source['beat_scale']==1 for source in plan['sources'].values()))
            project=root/'project.json'
            save=dict(project=str(project),graph=plan['graph'],sources=plan['sources'],source_assets=plan['source_assets'],worker=str(worker),seconds=6,tempo=120)
            call('project.graph.save',**save)
            result=call('project.render',project=str(project),jobs=str(root/'jobs'))
            self.assertFalse(result['measurements']['silent']);self.assertEqual(result['measurements']['decoded_frames'],264600)
            decoded=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',result['audio'],'-f','f32le','-ac','1','-ar','44100','-'],capture_output=True,check=True,timeout=15).stdout
            pcm=np.frombuffer(decoded,dtype='<f4')
            def amplitude(start,hz):
                window=pcm[round(start*44100):round((start+1)*44100)].astype(np.float64)
                return abs(np.dot(window,np.exp(-2j*np.pi*hz*np.arange(len(window))/44100)))*2/len(window)
            self.assertGreater(amplitude(.5,100),.03);self.assertLess(amplitude(.5,300),.001)
            self.assertGreater(amplitude(3,300),.02);self.assertGreater(amplitude(3,100),.03)
            original=project.read_bytes();changed=Path(plan['sources']['chords']['file']);changed.write_bytes(b'changed after proposal')
            with self.assertRaisesRegex(ValueError,'source content changed'):call('project.graph.save',**{**save,'expected_revision':1})
            self.assertEqual(project.read_bytes(),original)
            partial=propose(catalog,6,bpm=120,root=0,mode='major',roles=['drum','melody'])
            self.assertEqual(partial['missing_roles'],['melody']);self.assertTrue(any('not silently substituted' in warning for warning in partial['warnings']))

    def test_multiple_pitched_layers_require_explicit_review_and_invalid_requests_fail(self):
        with self.assertRaisesRegex(ValueError,'unverified-harmony'):propose(Path('unopened.sqlite'),8,roles=['bass','chords'],root=0,mode='major')
        for roles in ([{}],['drum','drum'],[],['unknown']):
            with self.assertRaises(ValueError):propose(Path('unopened.sqlite'),8,roles=roles)
        with self.assertRaises(ValueError):propose(Path('unopened.sqlite'),8,roles=['chords'])


if __name__=='__main__':unittest.main()

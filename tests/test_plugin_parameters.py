"""Real controller conversion, program-before-override state and audible replay."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute
from plugins import inspect,capture_state
from vst3_render import render_plugin

BUILD=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')
CID='6623100114424231A562100212142801'


@unittest.skipUnless((BUILD/'arranger-vst3.exe').is_file(),'pinned native worker required')
class ParameterTests(unittest.TestCase):
    def test_native_display_round_trip_and_bounded_invalid_conversions(self):
        args={'worker':str(BUILD/'arranger-vst3.exe'),'plugin':str(BUILD/'arranger-delay-fixture.vst3'),'class_id':CID,'parameter_id':1}
        def convert(**value):return execute({'contract':1,'operation':'plugins.parameter.convert','arguments':{**args,**value}})['result']
        normalized=convert(normalized=.375);self.assertEqual(normalized['display'],'0.3750');self.assertFalse(normalized['state_changed'])
        displayed=convert(display=normalized['display']);self.assertEqual(displayed['normalized'],.375)
        with tempfile.TemporaryDirectory() as directory:
            state=capture_state(BUILD/'arranger-vst3.exe',BUILD/'arranger-delay-fixture.vst3',CID,Path(directory),parameters={'1':.375})
            self.assertIsNotNone(state['controller_sha256']);self.assertEqual(Path(state['state']+'.controller').stat().st_size,4)
            restored=inspect(BUILD/'arranger-vst3.exe',BUILD/'arranger-delay-fixture.vst3',class_id=CID,state=Path(state['state']))
            self.assertEqual(restored['classes'][0]['parameters'][0]['normalized'],.375)
        for value in ({'normalized':True},{'normalized':float('nan')},{'display':'x'*128},{'normalized':.5,'display':'.5'},{}, {'parameter_id':999,'normalized':.5}):
            with self.assertRaises(ValueError):convert(**value)

    def test_mda_program_then_override_survives_component_state_controller_sync_and_audible_replay(self):
        plugin=BUILD/'VST3/Release/mda-vst3.vst3';cid='5653544D44416A6D6461206A78313000';worker=BUILD/'arranger-vst3.exe'
        if not plugin.is_dir():self.skipTest('existing legally reviewed SDK mda instrument required')
        component=inspect(worker,plugin,class_id=cid)['classes'][0]
        self.assertTrue(component['controller_component_synced']);self.assertEqual(next(p for p in component['parameters'] if p['id']==0)['normalized'],1,'fresh processor defaults must be synchronized before displaying controller values')
        listing=component['program_lists'][0];self.assertEqual(listing['count'],52);self.assertEqual(listing['names'][17],'Analog Bass');self.assertFalse(listing['names_truncated'])
        selector=next(p for p in component['parameters'] if p['program_list_id']==listing['id']);regular=next(p for p in component['parameters'] if p['id']==0)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);parameters={str(selector['id']):17/51,'0':.13}
            captured=capture_state(worker,plugin,cid,root/'presets',parameters=parameters)
            self.assertTrue(captured['controller_component_synced'])
            self.assertIsNone(captured['controller_sha256'],'this SDK component provides no independent controller state; do not claim paired recall')
            restored=inspect(worker,plugin,class_id=cid,state=Path(captured['state']))['classes'][0]
            self.assertEqual(next(p for p in restored['parameters'] if p['id']==selector['id'])['display'],'Analog Bass')
            self.assertAlmostEqual(next(p for p in restored['parameters'] if p['id']==regular['id'])['normalized'],.13,places=6)
            source=root/'silence.f32';source.write_bytes(bytes(44100*8));notes=root/'notes.txt';notes.write_text('100 33075 48 100\n',encoding='utf-8')
            signals=[]
            for folder in ('first','replay'):
                result=render_plugin(worker,plugin,source,root/folder,state=Path(captured['state']),class_id=cid,notes=notes)
                signals.append(np.fromfile(result['audio'],dtype='<f4'))
            self.assertGreater(float(np.max(np.abs(signals[0]))),.01);self.assertLess(float(np.max(np.abs(signals[0]-signals[1]))),1e-7)
            baseline=capture_state(worker,plugin,cid,root/'presets',parameters={str(selector['id']):17/51})
            result=render_plugin(worker,plugin,source,root/'baseline',state=Path(baseline['state']),class_id=cid,notes=notes)
            self.assertGreater(float(np.sqrt(np.mean((signals[0]-np.fromfile(result['audio'],dtype='<f4'))**2))),.001,'override must affect processor audio, not only controller display')

    @unittest.skipUnless(importlib.util.find_spec('PySide6'),'pinned Qt runtime required')
    def test_qt_program_selection_uses_actual_worker_conversion_and_queues_only_intended_edit(self):
        from unittest.mock import patch
        import workspace
        from plugin_controls import ParameterDialog
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
        plugin=BUILD/'VST3/Release/mda-vst3.vst3';cid='5653544D44416A6D6461206A78313000'
        if not plugin.is_dir():self.skipTest('SDK mda fixture required')
        component=inspect(BUILD/'arranger-vst3.exe',plugin,class_id=cid)['classes'][0]
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            owner=workspace.Workspace();args={'worker':str(BUILD/'arranger-vst3.exe'),'plugin':str(plugin),'class_id':cid};dialog=ParameterDialog(owner,component,args)
            try:
                self.assertEqual(dialog.programs.currentText(),component['program_lists'][0]['names'][0])
                dialog.index.setValue(17);self.assertEqual(dialog.programs.currentText(),'Analog Bass');dialog.use_program();deadline=time.monotonic()+10
                while owner.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
                self.assertFalse(owner.busy,owner.state.text());self.assertEqual(dialog.edits(),{'1886548852':17/51})
                row=next(i for i,p in enumerate(dialog.values) if p['id']==0);dialog.table.item(row,1).setText('nan')
                with self.assertRaises(ValueError):dialog.edits()
            finally:dialog.reject();owner.close();app.processEvents()


if __name__=='__main__':unittest.main()

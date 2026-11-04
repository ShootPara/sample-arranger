import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from array import array
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from preset_files import decode,import_preset,export_preset
from vst3_render import render_plugin
BUILD=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')


@unittest.skipUnless((BUILD/'arranger-vst3.exe').exists(),'native SDK check required')
class PresetTests(unittest.TestCase):
    def test_headless_parameter_capture_supports_sidechain_and_multiple_outputs(self):
        from plugins import capture_state
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);worker=BUILD/'arranger-vst3.exe';plugin=BUILD/'arranger-delay-fixture.vst3'
            result=capture_state(worker,plugin,'6623100414424231A562100212142801',root/'presets',parameters={'1':0})
            source=root/'input.f32';source.write_bytes(array('f',[0.2]*2048).tobytes())
            rendered=render_plugin(worker,plugin,source,root,state=Path(result['state']),sidechain=source)
            self.assertEqual(rendered['output_buses'],2)
            self.assertTrue(rendered['component_state_restored']);self.assertTrue(rendered['controller_state_restored'])
            for bus in rendered['buses']:
                audio=array('f');audio.frombytes(Path(bus).read_bytes());self.assertTrue(all(value==0 for value in audio))
    def test_shared_headless_parameter_capture_replays_processor_and_controller(self):
        from commands import execute
        from plugins import inspect
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);worker=BUILD/'arranger-vst3.exe';plugin=BUILD/'arranger-delay-fixture.vst3'
            identity='6623100114424231A562100212142801'
            inventory=inspect(worker,plugin,class_id=identity)
            self.assertEqual([item['class_id'] for item in inventory['classes']],[identity])
            result=execute({'contract':1,'operation':'plugins.state.save','arguments':{
                'worker':str(worker),'plugin':str(plugin),'class_id':identity,
                'presets':str(root/'presets'),'parameters':{'1':0}}})['result']
            self.assertEqual(result['capture_mode'],'generic-parameters')
            self.assertEqual(result['parameter_values']['1'],0)
            source=root/'signal.f32';source.write_bytes(array('f',[0.2]*2048).tobytes())
            rendered=render_plugin(worker,plugin,source,root,state=Path(result['state']))
            self.assertTrue(rendered['component_state_restored']);self.assertTrue(rendered['controller_state_restored'])
            audio=array('f');audio.frombytes(Path(rendered['audio']).read_bytes())
            self.assertTrue(all(value==0 for value in audio))
            with self.assertRaisesRegex(ValueError,'unknown or read-only'):
                execute({'contract':1,'operation':'plugins.state.save','arguments':{
                    'worker':str(worker),'plugin':str(plugin),'class_id':identity,
                    'presets':str(root/'presets'),'parameters':{'999999':0}}})
            self.assertEqual(len(list((root/'presets').iterdir())),1)

    def test_sdk_interchange_and_actual_muted_processor_controller_recall(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.f32';source.write_bytes(array('f',[0.1]*2048).tobytes())
            automation=root/'mute.txt';automation.write_text('0 1 0\n')
            worker=BUILD/'arranger-vst3.exe';plugin=BUILD/'arranger-delay-fixture.vst3'
            muted=render_plugin(worker,plugin,source,root,automation=automation)
            destination=root/'Mute.vstpreset'
            exported=export_preset(worker,plugin,Path(muted['state']),destination)
            identity,chunks=decode(destination)
            self.assertEqual(chunks[b'Comp'],Path(muted['state']).read_bytes())
            self.assertEqual(chunks[b'Cont'],Path(muted['controller_state']).read_bytes())
            imported=import_preset(worker,plugin,destination,root/'presets')
            from plugins import inspect
            inventory=inspect(worker,plugin,state=Path(imported['state']))
            self.assertEqual(len(inventory['classes']),1)
            self.assertEqual(inventory['classes'][0]['parameters'][0]['normalized'],0)
            replay=render_plugin(worker,plugin,source,root,state=Path(imported['state']))
            self.assertTrue(replay['component_state_restored']);self.assertTrue(replay['controller_state_restored'])
            self.assertEqual(Path(replay['audio']).read_bytes(),Path(muted['audio']).read_bytes())
            with self.assertRaisesRegex(ValueError,'already exists'):export_preset(worker,plugin,Path(muted['state']),destination)
            malformed=bytearray(destination.read_bytes());struct.pack_into('<Q',malformed,40,2**63)
            destination.write_bytes(malformed)
            with self.assertRaisesRegex(ValueError,'list offset'):decode(destination)

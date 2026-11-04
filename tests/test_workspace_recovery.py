"""Actual abrupt writer exit, bounded drafts and Qt restore/render acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workspace_recovery import Drafts


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'pinned UI runtime required')
class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([]);cls.app.setQuitOnLastWindowClosed(False)

    def test_abrupt_writer_exit_restores_locked_harmony_and_renders_through_shared_command(self):
        import workspace
        from music import compile_intent,set_note_locks,edit_harmony
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            root=Path(directory);first=workspace.Workspace();second=None
            try:
                first.score=set_note_locks(edit_harmony(compile_intent({'seconds':2,'bpm':120}),[{'bar':0,'degree':4}]),[0]);first.brief.setText('A refined 2 second music bed');first.initial='Music, please'
                from musical_locks import set_locks
                first.score=set_locks(first.score,[{'bar':0,'kind':'section','part':'all'}])
                first.refresh_plan();state=first.recovery_state()
                code='''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from workspace_recovery import Drafts
state=json.loads(sys.stdin.read());path=Drafts(Path(sys.argv[2])).write(state)
print(path,flush=True);os._exit(23)
'''
                child=subprocess.run([sys.executable,'-B','-c',code,str(Path(workspace.__file__).parent),str(root/'workspace-recovery')],input=json.dumps(state),capture_output=True,text=True,timeout=10)
                self.assertEqual(child.returncode,23,child.stderr);draft=Path(child.stdout.strip());self.assertTrue(draft.is_file())
                second=workspace.Workspace();self.assertIn('earlier workspace',second.recovery_notice.text())
                restored=second.drafts.read(draft);second.apply_recovery_state(restored)
                self.assertEqual(second.score,first.score);self.assertEqual(second.initial,'Music, please');self.assertEqual(second.brief.text(),state['brief'])
                second.persist_draft();self.assertTrue(second.drafts.path.is_file());self.assertTrue(draft.is_file(),'restoration must not remove the historical draft')
                second.render_job();deadline=time.monotonic()+15
                while second.busy and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
                self.assertFalse(second.busy,second.state.text());self.assertTrue(Path(second.output).is_file(),second.state.text())
                self.assertFalse(second.output_measurements['silent'])
                second.project_path=str(root/'project.json');self.assertTrue(second.save_project());self.assertFalse(second.drafts.path.exists())
            finally:
                first.close()
                if second:second.close()
                self.app.processEvents()

    def test_temporary_disabled_recovery_caps_and_atomic_failed_write(self):
        import workspace
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            root=Path(directory);window=workspace.Workspace()
            try:
                window.score=compile_intent({'seconds':1});window.persist_draft();path=window.drafts.path;self.assertTrue(path.exists());original=path.read_bytes()
                with patch('workspace_recovery.os.replace',side_effect=OSError('injected interrupted replacement')):
                    with self.assertRaises(OSError):window.drafts.write(window.recovery_state())
                self.assertEqual(path.read_bytes(),original);self.assertEqual(list(path.parent.glob('.draft-*.tmp')),[])
                window.temporary_results.setChecked(True);window.persist_draft();self.assertFalse(path.exists())
                window.temporary_results.setChecked(False);window.keep_recovery.setChecked(False);window.persist_draft();self.assertFalse(path.exists())
                state=window.recovery_state()
                with patch('workspace_recovery.MAX_DRAFTS',1):
                    retained=Drafts(root/'bounded');retained.write(state)
                    with self.assertRaisesRegex(ValueError,'full'):Drafts(root/'bounded').write(state)
                    self.assertTrue(retained.path.is_file())
                invalid=root/'workspace-recovery'/'draft-invalid.json';invalid.write_text('['*1500+'0'+']'*1500)
                with self.assertRaises(ValueError):window.drafts.read(invalid)
                outside=root/'draft-outside.json';outside.write_bytes(original)
                with self.assertRaisesRegex(ValueError,'owned-format'):window.drafts.read(outside)
            finally:window.close();self.app.processEvents()

    def test_reopened_effect_class_and_parameters_survive_inspection_and_invalid_edit(self):
        import workspace
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            window=workspace.Workspace()
            try:
                cid='6623100414424231A562100212142801';window.paths['plugin'].setText('fixture.vst3');window.restore_effect_selection(cid,{'1':.37})
                self.assertEqual(window.processing()['class_id'],cid)
                window.plugin_inventory=[{'class_id':cid,'name':'Fixture','parameters':[{'id':1,'name':'Gain','normalized':1.0,'flags':0}]}]
                window.classes.addItem('Fixture');window.show_parameters()
                self.assertEqual(window.parameters,{'1':.37});self.assertEqual(window.parameter_table.item(0,1).text(),'0.37')
                window.parameter_table.item(0,1).setText('invalid');self.assertEqual(window.parameters,{'1':.37})
                window.paths['plugin'].setText('different.vst3');self.assertNotIn('class_id',window.processing());self.assertEqual(window.parameters,{})
            finally:window.close();self.app.processEvents()


if __name__=='__main__':unittest.main()

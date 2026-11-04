"""Qt control/model/process tests, separate from manual Windows accessibility acceptance."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
import unittest
import os
import json
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
QT=importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(QT,"run UI tests with the pinned UI runtime")
class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_editable_rhythm_controls_shared_operation_and_undo(self):
        import workspace
        from rhythm_dialog import RhythmDialog
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            window=workspace.Workspace()
            try:
                window.score=compile_intent({'bars':2});window.refresh_plan();before=json.loads(json.dumps(window.score))
                dialog=RhythmDialog(window.score,window);dialog.first.setValue(2);dialog.last.setValue(2)
                self.assertEqual(dialog.table.cellWidget(0,0).accessibleName(),'Cell 1 chord tone or rest')
                dialog.table.cellWidget(0,0).setCurrentIndex(1);dialog.apply()
                self.assertEqual(dialog.bars,[1]);self.assertEqual(dialog.pattern[0]['tone'],1)
                window.apply_melody_rhythm(dialog.bars,dialog.pattern)
                deadline=time.monotonic()+10
                while window.busy and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
                self.assertFalse(window.busy);self.assertIn('Melody rhythm applied',window.state.text())
                self.assertEqual(window.score['melody_patterns']['1'][0]['tone'],1)
                window.undo_plan();self.assertEqual(window.score,before)
                window.undo_plan(True);self.assertEqual(window.score['melody_patterns']['1'][0]['tone'],1)
                dialog.close()
            finally:window.close();self.app.processEvents()

    def test_musical_protection_dialog_save_explicit_unlock_and_recovery(self):
        import workspace
        from lock_dialog import LockDialog
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            window=workspace.Workspace()
            try:
                window.score=compile_intent({'bars':2});window.refresh_plan()
                dialog=LockDialog(window.score,window);dialog.kind.setCurrentText('rhythm');dialog.part.setCurrentText('melody');dialog.protect()
                self.assertEqual(len(dialog.selections),2);self.assertEqual(dialog.table.accessibleName(),'Protected musical decisions')
                window.apply_musical_locks(dialog.selections);window.project_path=str(Path(directory)/'locked.json')
                self.assertTrue(window.save_project(),window.state.text())
                window.apply_musical_locks([dialog.selections[1]])
                state=window.recovery_state();window.apply_recovery_state(state)
                self.assertIn((0,'rhythm','melody'),window.released_musical_keys)
                self.assertTrue(window.save_project(),window.state.text())
                saved=json.loads(Path(window.project_path).read_text(encoding='utf-8'));self.assertEqual(len(saved['score']['musical_locks']),1)
                self.assertEqual(saved['score']['musical_locks'][0]['bar'],1)
                window.brief.setText('8 seconds calm music');window.mode.setCurrentIndex(1);before=json.loads(json.dumps(window.score))
                window.plan();self.assertEqual(window.score,before);self.assertIn('Unlock protected',window.state.text())
                dialog.close()
            finally:window.close();self.app.processEvents()

    def test_late_sample_and_ensemble_proposals_cannot_replace_refined_workspace(self):
        import workspace
        from routing_workspace import RoutingWorkspace
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            window=workspace.Workspace();callbacks=[]
            try:
                window.brief.setText('4 seconds upbeat music')
                with patch.object(window,'request',side_effect=lambda op,args,callback:callbacks.append(callback)):window.plan()
                window.brief.setText('8 seconds calm music');window.sections=[{'sample':'keep-newer.wav','seconds':8}]
                callbacks.pop()({'state':'ready','sections':[{'sample':'old.wav','seconds':4}]})
                self.assertEqual(window.sections[0]['sample'],'keep-newer.wav');self.assertIn('newer edits were kept',window.state.text())
                with patch.object(window,'request',side_effect=lambda op,args,callback:callbacks.append(callback)):window.plan_ensemble()
                window.brief.setText('12 seconds with a different goal')
                with patch.object(RoutingWorkspace,'exec') as dialog:callbacks.pop()({});dialog.assert_not_called()
                self.assertIn('changed while planning',window.state.text())
            finally:window.close();self.app.processEvents()

    def test_render_completion_identifies_earlier_snapshot_when_user_edits_while_pending(self):
        import workspace
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            window=workspace.Workspace()
            try:
                window.score=compile_intent({'seconds':1});window.refresh_plan();original=window.score['notes'][0]['velocity'];window.render_job()
                self.assertTrue(window.busy);window.notes.item(0,4).setText('1');self.assertEqual(window.score['notes'][0]['velocity'],1)
                deadline=time.monotonic()+15
                while window.busy and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
                self.assertFalse(window.busy,window.state.text());self.assertIn('Earlier workspace snapshot',window.state.text())
                manifest=json.loads((Path(window.output).parent/'manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['composition']['score']['notes'][0]['velocity'],original);self.assertEqual(window.score['notes'][0]['velocity'],1)
            finally:window.close();self.app.processEvents()

    def test_accessible_names_note_validation_and_actual_shared_render(self):
        from PySide6.QtGui import QAccessible
        import workspace
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(workspace,"DATA",Path(directory)):
                window=workspace.Workspace()
                try:
                    interface=QAccessible.queryAccessibleInterface(window.brief)
                    self.assertIsNotNone(interface)
                    self.assertEqual(interface.text(QAccessible.Text.Name),"Music brief")
                    window.score=compile_intent({"seconds":1,"bpm":128})
                    window.refresh_plan()
                    original=window.score['notes'][0]['velocity']
                    window.notes.item(0,4).setText("49")
                    self.assertEqual(window.score["notes"][0]["velocity"],49)
                    window.undo_plan();self.assertEqual(window.score['notes'][0]['velocity'],original)
                    window.undo_plan(True);self.assertEqual(window.score['notes'][0]['velocity'],49)
                    window.notes.selectRow(0);window.toggle_note_lock()
                    self.assertEqual(window.score['note_locks'],[window.score['notes'][0]])
                    window.apply_note_changes([{'action':'set','index':0,'field':'velocity','value':50}],0)
                    self.assertEqual(window.score['notes'][0]['velocity'],49)
                    window.notes.selectRow(0);window.toggle_note_lock();self.assertEqual(window.score['note_locks'],[])
                    window.notes.item(0,4).setText("200")
                    self.assertEqual(window.score["notes"][0]["velocity"],49)
                    window.harmony_table.item(0,1).setText('4')
                    self.assertEqual(window.score['harmony'][0]['degree'],4)
                    window.undo_plan();self.assertEqual(window.score['harmony'][0]['degree'],1)
                    window.undo_plan(True);self.assertEqual(window.score['harmony'][0]['degree'],4)
                    window.render_job()
                    deadline=time.monotonic()+15
                    while window.busy and time.monotonic()<deadline:
                        self.app.processEvents();time.sleep(0.01)
                    self.assertFalse(window.busy,"UI child command did not finish")
                    self.assertIsNotNone(window.output,window.state.text())
                    self.assertTrue(Path(window.output).is_file())
                    self.assertEqual(window.owned_snapshots,set())
                finally:window.close();self.app.processEvents()

    def test_explicit_note_unlock_saves_without_silently_releasing_other_saved_locks(self):
        import workspace
        from music import compile_intent,set_note_locks
        from project import save,read
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            root=Path(directory);path=root/'project.json';score=set_note_locks(compile_intent({'seconds':2}),[0,1]);save(path,[],score=score)
            window=workspace.Workspace()
            try:
                window.score=score;window.project_path=str(path);window.revision=1;window.refresh_plan();window.notes.selectRow(0)
                window.toggle_note_lock();window.apply_note_changes([{'action':'set','index':0,'field':'velocity','value':49}],0)
                window.save_project()
                saved=read(path);self.assertEqual(saved['revision'],2,window.state.text());self.assertEqual(saved['score']['notes'][0]['velocity'],49)
                self.assertEqual(saved['score']['note_locks'],[score['notes'][1]])
                self.assertEqual(window.released_note_ids,set())
            finally:window.close();self.app.processEvents()

    def test_force_cancel_uses_actual_command_identity_and_exits_native_tree_without_ui_blocking(self):
        import workspace
        from command_guard import kernel
        source=Path(__file__).resolve().parents[1]/'src'
        fixture=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native/arranger-lifecycle-fixture.exe')
        if not fixture.is_file():self.skipTest('native lifecycle fixture required')
        code='''import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import commands
from process_group import popen
fixture,pids=sys.argv[2:4]
def stalled(request):
    child=popen([fixture,pids])
    time.sleep(60)
commands.execute=stalled
sys.argv=['commands',*sys.argv[4:]]
commands.main()
'''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pids=root/'pids.json';handles=[];api=kernel()
            def command(name,*args):return [sys.executable,'-B','-c',code,str(source),str(fixture),str(pids),*args]
            with patch.object(workspace,'DATA',root),patch.object(workspace,'module_command',side_effect=command):
                window=workspace.Workspace()
                try:
                    window.request('capabilities',{})
                    deadline=time.monotonic()+5
                    while (not pids.exists() or not window.command_guards) and time.monotonic()<deadline:self.app.processEvents();time.sleep(0.01)
                    self.assertTrue(pids.exists());self.assertTrue(next(iter(window.command_guards.values())).running())
                    for pid in json.loads(pids.read_text()):
                        handle=api.OpenProcess(0x100000,False,pid);self.assertTrue(handle);handles.append(handle)
                        self.assertEqual(api.WaitForSingleObject(handle,0),258)
                    window.cancel();started=time.monotonic();window.close()
                    self.assertLess(time.monotonic()-started,0.2,'Close must not block the event loop waiting for the child')
                    ticks=0;deadline=time.monotonic()+10
                    while window.busy and time.monotonic()<deadline:self.app.processEvents();ticks+=1;time.sleep(0.01)
                    self.assertFalse(window.busy,window.state.text());self.assertGreater(ticks,100,'UI must keep processing events during grace period')
                    for handle in handles:self.assertEqual(api.WaitForSingleObject(handle,5000),0)
                    self.assertEqual(window.command_guards,{})
                finally:
                    window.cancel()
                    for process,marker,path in window.tasks[:]:window.force_canceled(process,marker)
                    for handle in handles:api.CloseHandle(handle)
                    window.close();self.app.processEvents()

"""Actual Qt/shared-command routing workflow; separate from manual visual acceptance."""
from array import array
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
QT=importlib.util.find_spec('PySide6') is not None
BUILD=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')


@unittest.skipUnless(QT and (BUILD/'arranger-vst3.exe').is_file(),'pinned Qt/native runtime required')
class RoutingWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([]);cls.app.setQuitOnLastWindowClosed(False)
    def wait(self,window):
        deadline=time.monotonic()+20
        while window.busy and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertFalse(window.busy,window.state.text())
    def test_unapplied_invalid_panels_survive_selection_refresh_and_block_save(self):
        import workspace
        from routing_workspace import RoutingWorkspace
        from graph_project import save
        from project import read
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            root=Path(directory);path=root/'routing.json';plugin=str(BUILD/'arranger-delay-fixture.vst3')
            graph={'nodes':[{'id':name,'plugin':plugin,'class_id':'6623100414424231A562100212142801','input':{'node':'quiet','bus':0}} for name in ('first','second')],
                   'outputs':[{'node':'second','bus':0,'gain':1}]}
            saved=save(path,graph,{'quiet':{'silence':True}},BUILD/'arranger-vst3.exe',1,tempo=120)['project']
            owner=workspace.Workspace();dialog=RoutingWorkspace(owner,saved,path)
            try:
                dialog.items.selectRow(1);self.app.processEvents();dialog.add_row(dialog.automation,['unfinished','1','0.25'])
                dialog.outputs.item(0,2).setText('invalid gain')
                dialog.items.selectRow(2);self.app.processEvents();dialog.apply_routes()
                self.assertTrue(dialog.has_pending());self.assertIn('first',dialog.pending_forms)
                with patch.object(owner,'request') as request:dialog.save();request.assert_not_called()
                self.assertIn('Unapplied routing controls',dialog.status.text());self.assertEqual(read(path)['revision'],1)
                dialog.items.selectRow(1);self.app.processEvents();self.assertEqual(dialog.automation.item(0,0).text(),'unfinished')
                dialog.apply_automation();self.assertNotIn('automation_points',dialog.graph['nodes'][0]);self.assertTrue(dialog.has_pending())
                dialog.automation.item(0,0).setText('0');dialog.apply_automation()
                self.assertNotIn('first',dialog.pending_forms);self.assertEqual(dialog.outputs.item(0,2).text(),'invalid gain')
                dialog.restore_outputs();self.assertFalse(dialog.has_pending());dialog.save();self.wait(owner)
                self.assertEqual(read(path)['revision'],2);self.assertEqual(read(path)['graph']['nodes'][0]['automation_points'][0]['value'],.25)
                self.assertFalse(dialog.has_changes())
                dialog.side_bus.setValue(2);self.assertTrue(dialog.has_pending());dialog.restore_inspector();self.assertFalse(dialog.has_pending())
            finally:
                from PySide6.QtWidgets import QMessageBox
                with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Discard):dialog.close()
                owner.close();self.app.processEvents()
    def test_edit_sidechain_multioutput_automation_save_render_reopen(self):
        import workspace
        from routing_workspace import RoutingWorkspace
        from graph_project import save
        from project import read
        with tempfile.TemporaryDirectory() as directory,patch.object(workspace,'DATA',Path(directory)):
            root=Path(directory);source=root/'impulse.f32';data=array('f',[0])*88200;data[2000]=data[2001]=.5;source.write_bytes(data.tobytes())
            graph={'nodes':[{'id':'router','plugin':str(BUILD/'arranger-delay-fixture.vst3'),'class_id':'6623100414424231A562100212142801',
                             'input':{'node':'music','bus':0},'sidechain':{'node':'key','bus':0}}],
                   'outputs':[{'node':'router','bus':0,'gain':.5},{'node':'router','bus':1,'gain':.5}]}
            project=root/'routing.json';saved=save(project,graph,{'music':{'file':str(source)},'key':{'file':str(source)}},BUILD/'arranger-vst3.exe',1,tempo=120)['project']
            owner=workspace.Workspace();owner.paths['jobs'].setText(str(root/'jobs'));dialog=RoutingWorkspace(owner,saved,project)
            try:
                dialog.show();self.app.processEvents();dialog.items.selectRow(2);self.app.processEvents()
                self.assertEqual(dialog.node()['id'],'router');self.assertEqual(dialog.sidechain.currentText(),'key')
                self.assertTrue(dialog.processor_controls.isVisible());self.assertFalse(dialog.source_controls.isVisible())
                dialog.items.selectRow(0);self.app.processEvents();self.assertTrue(dialog.source_controls.isVisible());self.assertFalse(dialog.processor_controls.isVisible())
                self.assertFalse(dialog.tabs.isTabEnabled(1));dialog.items.selectRow(2);self.app.processEvents();self.assertTrue(dialog.tabs.isTabEnabled(1))
                # Invalid self-routing/cycle rolls back the entire attempted edit.
                before=dialog.graph.copy()
                dialog.modify(lambda node:node.update(input={'node':'router','bus':0}))
                self.assertEqual(dialog.graph,before);self.assertIn('feedback',dialog.status.text())
                # Actual inspector lane edit -> saved shared command -> real native MP3.
                dialog.add_row(dialog.automation,['0','1','0']);dialog.apply_automation()
                self.assertEqual(dialog.graph['nodes'][0]['automation_points'][0]['value'],0)
                self.assertTrue(dialog.has_changes())
                dialog.undo();self.assertNotIn('automation_points',dialog.graph['nodes'][0]);self.assertFalse(dialog.has_changes())
                dialog.undo(True);self.assertTrue(dialog.has_changes())
                from PySide6.QtWidgets import QMessageBox
                with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):
                    dialog.reject();self.assertTrue(dialog.isVisible(),'Cancel must preserve the dirty routing workspace')
                dialog.render();self.wait(owner)
                self.assertIsNotNone(owner.output,owner.state.text())
                self.assertTrue(owner.output_measurements['silent'])
                self.assertEqual(read(project)['revision'],2)
                self.assertFalse(dialog.has_changes())
                self.assertEqual(read(project)['graph']['nodes'][0]['sidechain']['node'],'key')
                reopened=RoutingWorkspace(owner,read(project),project)
                self.assertEqual(reopened.graph,dialog.graph);self.assertEqual(reopened.outputs.rowCount(),2);reopened.close()
                dialog.items.selectRow(2);dialog.automation.item(0,2).setText('1');dialog.apply_automation();dialog.render();self.wait(owner)
                self.assertFalse(owner.output_measurements['silent'])
                self.assertEqual(read(project)['revision'],3)
                self.assertEqual(len(list((root/'jobs').glob('job-*'))),2)
            finally:dialog.close();owner.close();self.app.processEvents()


if __name__=='__main__':unittest.main()

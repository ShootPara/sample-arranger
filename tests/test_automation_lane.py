import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'pinned UI runtime required')
class AutomationLaneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([]);cls.app.setQuitOnLastWindowClosed(False)
    def test_drag_mapping_parameter_choice_invalid_rows_and_bounded_preview(self):
        from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QDoubleSpinBox
        from automation_lane import AutomationLane
        table=QTableWidget(0,3);seconds=QDoubleSpinBox();seconds.setValue(4);tempo=QDoubleSpinBox();tempo.setMaximum(400);tempo.setValue(120)
        def row(values):
            i=table.rowCount();table.insertRow(i)
            for col,value in enumerate(values):table.setItem(i,col,QTableWidgetItem(str(value)))
        row([0,1,0]);row([44100,1,1]);row([0,2,.5]);row(['invalid',1,.8]);row([44100,1,.2])
        lane=AutomationLane(table,seconds,tempo)
        try:
            self.assertEqual(len(lane.handles),2);self.assertIn('2 invalid',lane.caption.text())
            lane.move_point(0,50+420*.2,20+112*.33)
            self.app.processEvents();self.assertEqual(table.item(0,0).text(),'33075');self.assertEqual(table.item(0,2).text(),'0.67')
            # Other parameter and invalid draft cells are untouched.
            self.assertEqual(table.item(3,0).text(),'invalid');lane.parameter.setCurrentIndex(1);self.app.processEvents();self.assertEqual(len(lane.handles),1)
            table.setRowCount(0)
            for i in range(600):row([i*100,9,.5])
            lane.refresh();self.assertEqual(len(lane.handles),512);self.assertIn('first512',lane.caption.text());self.assertEqual(table.rowCount(),600)
            table.removeRow(0);self.app.processEvents();self.assertIn('599 step',lane.caption.text())
        finally:lane.close();table.close();seconds.close();tempo.close();self.app.processEvents()

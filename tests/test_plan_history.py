import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from plan_history import PlanHistory


class HistoryTests(unittest.TestCase):
    def test_bounded_history_branching_and_owned_snapshots(self):
        history=PlanHistory(max_entries=3,max_bytes=1024)
        state={'notes':[1]};history.remember(state);state['notes'][0]=2
        history.remember(state);state={'notes':[3]}
        restored=history.undo(state);self.assertEqual(restored,{'notes':[2]})
        restored['notes'][0]=9
        self.assertEqual(history.redo(restored),{'notes':[3]})
        history.remember({'notes':[4]});self.assertIsNone(history.redo({'notes':[5]}))
        for index in range(20):history.remember({'notes':[index],'context':'x'*180})
        self.assertLessEqual(len(history.past),3);self.assertLessEqual(sum(map(len,history.past)),1024)

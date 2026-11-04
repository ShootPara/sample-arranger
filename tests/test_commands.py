import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from commands import execute


class CommandTests(unittest.TestCase):
    def test_discovery_unknown_fields_and_intention(self):
        request={"contract":1,"operation":"capabilities","arguments":{}}
        self.assertIn("plugins.edit",execute(request)["result"]["operations"])
        with self.assertRaisesRegex(ValueError,"invalid arguments"):
            execute({**request,"arguments":{"shell":"anything"}})
        for arguments in ({'builtin':True,'destination':'music.wav'},{'builtin':True,'sink':'recording.exe'}):
            with self.assertRaisesRegex(ValueError,'invalid arguments'):execute({'contract':1,'operation':'continuous.play','arguments':arguments})
        score=execute({"contract":1,"operation":"score.compile","arguments":{"intent":{"bars":2}}})
        self.assertEqual(score["result"]["duration_ticks"],7680)
        result=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve().parents[1]/"src/commands.py")],
                              input=json.dumps(request),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["contract"],1)

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from compose import compose


@unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg needed")
class PaletteTests(unittest.TestCase):
    def test_intention_to_audible_mp3_with_score_provenance(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            result=compose({"bars":2,"bpm":120,"root":0,"mode":"major"},root)
            output=Path(result["audio"])
            decoded=subprocess.run(["ffmpeg","-v","error","-i",str(output),"-f","f32le","-"],
                                   capture_output=True,check=True,timeout=10).stdout
            audio=np.frombuffer(decoded,dtype="<f4")
            self.assertEqual(len(audio),4*44100*2)
            self.assertGreater(float(np.sqrt(np.mean(audio**2))),0.01)
            self.assertLess(float(np.max(np.abs(audio))),0.95)
            manifest=json.loads(output.with_name("manifest.json").read_text())
            self.assertEqual(manifest["composition"]["score"]["harmony"][-1]["degree"],1)
            self.assertEqual(manifest["composition"]["palette"]["frames"],4*44100)
            self.assertEqual(len(list(root.iterdir())),1)

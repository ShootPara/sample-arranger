from array import array
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from render import render


@unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required")
class OutputDurationTests(unittest.TestCase):
    def test_four_minute_mp3_decodes_with_no_excess_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"known.wav"
            pcm=array("h")
            for frame in range(4410):
                value=int(1000*math.sin(2*math.pi*440*frame/44100));pcm.extend((value,value))
            with wave.open(str(source),"wb") as output:
                output.setparams((2,2,44100,0,"NONE","not compressed"));output.writeframes(pcm.tobytes())
            result=render(source,None,240,root)
            decoded=root/"decoded.pcm"
            subprocess.run(["ffmpeg","-v","error","-i",result["audio"],"-f","s16le",str(decoded)],check=True,timeout=30)
            self.assertEqual(decoded.stat().st_size,240*44100*4)
            self.assertEqual(result["bitrate_kbps"],192)

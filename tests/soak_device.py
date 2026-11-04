"""Opt-in sustained real-device soak with synthetic audio and owned copied binaries.

Run with --minutes 120 for the full-duration gate. This covers a persistent effect,
not continuous MIDI instruments or inference contention. No input device opens.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import continuous
from device import DeviceStream


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes",type=int,default=120)
    args=parser.parse_args()
    if not 1<=args.minutes<=180:parser.error("minutes must be 1 to 180")
    build=Path(os.environ["LOCALAPPDATA"],"SampleArranger/tools/arranger-native")
    started=time.monotonic()
    stats={"kind":"real waveOut device, persistent controlled effect, synthetic input",
           "chunks":0,"peak_observed_spool_bytes":0,"peak_observed_spool_files":0}
    class MeasuredDevice(DeviceStream):
        def consume(self,path,stop):
            files=list(path.parent.glob("chunk-*.wav"))
            sizes=[]
            for source in files:
                try:sizes.append(source.stat().st_size)
                except FileNotFoundError:pass
            stats["peak_observed_spool_bytes"]=max(stats["peak_observed_spool_bytes"],sum(sizes))
            stats["peak_observed_spool_files"]=max(stats["peak_observed_spool_files"],len(files))
            super().consume(path,stop)
            stats["chunks"]+=1
            stats["elapsed_seconds"]=round(time.monotonic()-started,3)
            print(json.dumps(stats),flush=True)
    continuous.DeviceStream=MeasuredDevice
    with tempfile.TemporaryDirectory(prefix="arranger-device-soak-") as directory:
        root=Path(directory)
        for name in ("arranger-playback.exe","arranger-vst3.exe","arranger-delay-fixture.vst3"):
            shutil.copy2(build/name,root/name)
        source=root/"synthetic.wav"
        # Quiet known-signal pulse, purely generated; no user speech/sample retained.
        import math
        from array import array
        pcm=array("h")
        for frame in range(44100):
            value=int(100*math.sin(2*math.pi*440*frame/44100))
            pcm.extend((value,value))
        with wave.open(str(source),"wb") as audio:
            audio.setparams((2,2,44100,0,"NONE","not compressed"));audio.writeframes(pcm.tobytes())
        continuous.play(source,bpm=128,chunks=args.minutes,chunk_seconds=60,
                        sink=root/"arranger-playback.exe",worker=root/"arranger-vst3.exe",
                        plugin=root/"arranger-delay-fixture.vst3")
    stats.update(completed=True,elapsed_seconds=round(time.monotonic()-started,3))
    print(json.dumps(stats),flush=True)


if __name__=="__main__":main()

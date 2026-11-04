"""Opt-in actual output-device check. App-generated audio only; no recording."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import continuous
from device import DeviceStream

build=Path(os.environ["LOCALAPPDATA"],"SampleArranger/tools/arranger-native")
evidence={"measurement":"actual waveOut, generated palette plus persistent instrument and effect",
          "capture":False,"chunks":[],"pids":[],"completed":False}

class MeasuredDevice(DeviceStream):
    def consume(self,path,stop,score=None):
        pids=[process.pid for process in self.processes]
        if evidence["pids"] and evidence["pids"]!=pids:raise AssertionError("processing restarted across chunks")
        evidence["pids"]=pids
        evidence["chunks"].append({"notes":len(score["notes"]),"next_bar":score["ending_state"]["next_bar"]})
        super().consume(path,stop,score)

continuous.DeviceStream=MeasuredDevice
started=time.monotonic()
parser=argparse.ArgumentParser();parser.add_argument('--ensemble',action='store_true');args=parser.parse_args()
try:
    result=continuous.play(None,builtin=True,bpm=240,chunks=4,chunk_seconds=1,
        worker=build/"arranger-vst3.exe",plugin=build/"arranger-delay-fixture.vst3",
        instruments={part:{"plugin":str(build/"arranger-delay-fixture.vst3"),
                                "class_id":"6623100314424231A562100212142801"}
                     for part in (("bass","chords","melody") if args.ensemble else ("chords",))})
    evidence.update(completed=result["state"]=="completed",result=result)
finally:
    evidence["elapsed_seconds"]=round(time.monotonic()-started,3)
    print(json.dumps(evidence),flush=True)

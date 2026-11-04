"""Opt-in actual device soak: evolving palette, persistent MIDI instrument/effect.

Only app-generated audio; no microphone/loopback capture/export or live AI. Owned
copied binaries permit ongoing development. This fixture is not vendor acceptance.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import continuous
from device import DeviceStream
from assets import digest


class Memory(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('page_faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in (
        'peak_working_set','working_set','peak_paged','paged','peak_nonpaged','nonpaged','commit','peak_commit')]


def memory(handle):
    api=ctypes.WinDLL('psapi',use_last_error=True)
    api.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD]
    result=Memory();result.cb=ctypes.sizeof(result)
    if not api.GetProcessMemoryInfo(int(handle),ctypes.byref(result),result.cb):raise ctypes.WinError(ctypes.get_last_error())
    return {name:getattr(result,name) for name in ('working_set','peak_working_set','commit','peak_commit')}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--minutes',type=int,default=120)
    parser.add_argument('--ensemble',action='store_true');parser.add_argument('--mda',action='store_true',help='three existing SDK mda synthesizers at bounded route gains')
    args=parser.parse_args()
    if not 1<=args.minutes<=180:parser.error('minutes must be1 to180')
    started=time.monotonic();build=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')
    evidence={'kind':'actual waveOut; generated music; persistent mono instrument + stereo effect',
              'capture':False,'chunks':0,'completed':False,'peak_observed_spool_bytes':0,'pids':None}
    if args.ensemble:evidence['kind']='actual waveOut; three persistent owned instruments + effect'
    if args.mda:evidence['kind']='actual waveOut; three persistent SDK mda synths + owned effect; A minor'
    class Measured(DeviceStream):
        def consume(self,path,stop,score=None):
            files=list(path.parent.glob('chunk-*.wav'));size=0
            for source in files:
                try:size+=source.stat().st_size
                except FileNotFoundError:pass
            if size>88_000_000 or len(files)>4:raise AssertionError('owned spool exceeded allocation policy')
            evidence['peak_observed_spool_bytes']=max(evidence['peak_observed_spool_bytes'],size)
            pids=[child.pid for child in self.processes]
            if evidence['pids'] and evidence['pids']!=pids:raise AssertionError('DSP restarted at chunk boundary')
            evidence['pids']=pids
            super().consume(path,stop,score)
            evidence.update(chunks=evidence['chunks']+1,elapsed_seconds=round(time.monotonic()-started,3),
                            frames_submitted=self.frames_sent,frames_acknowledged=self.frames_heard,
                            memory={str(child.pid):memory(child._handle) for child in self.processes})
            kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
            evidence['python_memory']=memory(kernel.GetCurrentProcess())
            print(json.dumps(evidence),flush=True)
    continuous.DeviceStream=Measured
    with tempfile.TemporaryDirectory(prefix='arranger-instrument-soak-') as directory:
        root=Path(directory)
        for name in ('arranger-playback.exe','arranger-vst3.exe','arranger-delay-fixture.vst3'):shutil.copy2(build/name,root/name)
        state=root/'quiet-fixture.bin';state.write_bytes(struct.pack('<if',2,0.05))
        Path(str(state)+'.controller').write_bytes(struct.pack('<f',0.05))
        evidence['binary_sha256']={name:digest(root/name) for name in ('arranger-playback.exe','arranger-vst3.exe','arranger-delay-fixture.vst3')}
        instruments={part:{'plugin':str(root/'arranger-delay-fixture.vst3'),'class_id':'6623100614424231A562100212142801','state':str(state)}
                     for part in (('bass','chords','melody') if args.ensemble else ('chords',))}
        if args.mda:
            from plugins import fingerprint
            source=build/'VST3/Release/mda-vst3.vst3'
            if not source.is_dir():raise ValueError('existing legally reviewed SDK mda bundle is unavailable')
            shutil.copytree(source,root/'mda-vst3.vst3')
            instruments={part:{'plugin':str(root/'mda-vst3.vst3'),'class_id':identity,'outputs':[{'bus':0,'gain':gain}]}
                         for part,identity,gain in (('bass','5653544D44416A6D6461206A78313000',0.15),
                            ('chords','5653544D4441786D6461206478313000',0.12),('melody','5653544D4441786D6461206478313000',0.12))}
            evidence['binary_sha256']['mda-vst3']=fingerprint(root/'mda-vst3.vst3')
        evidence['instrument_classes']={part:{'class_id':spec['class_id'],'outputs':spec.get('outputs')} for part,spec in instruments.items()}
        print(json.dumps({'starting':evidence}),flush=True)
        result=continuous.play(None,builtin=True,bpm=128,chunks=args.minutes,chunk_seconds=60,
            sink=root/'arranger-playback.exe',worker=root/'arranger-vst3.exe',plugin=root/'arranger-delay-fixture.vst3',
            instruments=instruments,intent={'root':9,'mode':'minor'} if args.mda else None)
    evidence.update(completed=result['state']=='completed',result=result,elapsed_seconds=round(time.monotonic()-started,3))
    print(json.dumps(evidence),flush=True)


if __name__=='__main__':main()

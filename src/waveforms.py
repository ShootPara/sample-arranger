"""Bounded in-memory visual audio preview, not a retained audio cache."""
import json
import math
from pathlib import Path
import numpy as np
from process import run


def preview(path):
    path=Path(path)
    if not path.is_file():raise ValueError("waveform source is unavailable")
    before=path.stat()
    probe=run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=30)
    seconds=float(json.loads(probe.stdout)['format']['duration'])
    if not math.isfinite(seconds) or seconds<=0:raise ValueError("invalid waveform duration")
    completed=run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-t','30','-ar','8000','-ac','2','-f','f32le','-'],
                  capture_output=True,check=True,timeout=60)
    if not 0<len(completed.stdout)<=30*8000*8 or len(completed.stdout)%8:raise ValueError("waveform decoder exceeded bounds")
    audio=np.frombuffer(completed.stdout,dtype='<f4').reshape(-1,2)
    if not np.isfinite(audio).all():raise ValueError("waveform source contains nonfinite audio")
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError("waveform source changed during preview")
    bins=min(256,len(audio));edges=np.linspace(0,len(audio),bins+1,dtype=int)
    peaks=[[float(audio[start:end].min()),float(audio[start:end].max())] for start,end in zip(edges,edges[1:])]
    return {'path':str(path.resolve()),'bytes':after.st_size,'modified_ns':after.st_mtime_ns,
            'source_seconds':seconds,'preview_seconds':len(audio)/8000,'peaks':peaks,'cache':'memory only'}

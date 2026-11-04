"""Supplied audio only: bounded decoded fit and explicit mixing intentions."""
import math
import numpy as np
from process import run

DEFAULTS={'offset_seconds':0,'voice_gain_db':0,'music_gain_db':-5.2,'ducking':True}


def settings(value=None):
    if value is None:value={}
    if not isinstance(value,dict) or value.keys()-DEFAULTS.keys():raise ValueError('unknown narration settings')
    result={**DEFAULTS,**value}
    for key,low,high in (('offset_seconds',0,240),('voice_gain_db',-24,12),('music_gain_db',-60,0)):
        if type(result[key]) not in (int,float) or not math.isfinite(result[key]) or not low<=result[key]<=high:
            raise ValueError('narration '+key+' exceeds bounds')
    if type(result['ducking']) is not bool:raise ValueError('ducking must be boolean')
    return result


def inspect_fit(path,total_frames,value=None):
    if type(total_frames) is not int or not 1<=total_frames<=240*44100:raise ValueError('narration target must fit four minutes')
    value=settings(value);offset=round(value['offset_seconds']*44100);remaining=total_frames-offset
    if remaining<=0:raise ValueError('narration placement leaves no room for audio')
    decoded=run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-map','0:a:0','-af',
                 f'aformat=sample_rates=44100:channel_layouts=stereo,atrim=end_sample={remaining+1}',
                 '-ar','44100','-ac','2','-f','f32le','-'],capture_output=True,check=True,timeout=120,max_job_bytes=512*1024**2)
    count=len(decoded.stdout)
    if count%8 or not 0<count<=remaining*8:raise ValueError('decoded narration and placement must fit the requested duration; no speech was truncated')
    if not np.isfinite(np.frombuffer(decoded.stdout,dtype='<f4')).all():raise ValueError('narration contains nonfinite audio')
    return {'decoded_frames':count//8,'offset_samples':offset,'settings':value,
            'timing':'decoded samples; container/MP3 padding excluded','speech_edits':'none; explicit gain/mix only'}


def inspect_placement(voice,seconds,voice_settings=None):
    from pathlib import Path
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=240:
        raise ValueError('narration target must fit four minutes')
    voice=Path(voice);before=voice.stat();result=inspect_fit(voice,round(seconds*44100),voice_settings);after=voice.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('narration changed during inspection')
    return {**result,'path':str(voice.resolve()),'bytes':after.st_size,'modified_ns':after.st_mtime_ns}

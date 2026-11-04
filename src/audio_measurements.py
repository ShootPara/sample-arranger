"""Bounded post-decode delivery measurements; no normalization or extra artifact."""
import math
from pathlib import Path
import re
from process import run

MAX_FRAMES=240*44100


def measure(path,expected_frames=None):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>512*1024**2:raise ValueError('audio measurement source exceeds local file bounds')
    if expected_frames is not None and (type(expected_frames) is not int or not 1<=expected_frames<=MAX_FRAMES):raise ValueError('invalid delivery frame target')
    before=path.stat()
    filters=('aformat=sample_rates=44100:sample_fmts=flt:channel_layouts=stereo,'
             'astats=measure_perchannel=none:measure_overall=Peak_level+RMS_level+Number_of_samples+Number_of_NaNs+Number_of_Infs,'
             'ebur128=peak=true:framelog=verbose')
    result=run(['ffmpeg','-nostdin','-nostats','-loglevel','info','-i',str(path),
                '-map','0:a:0','-af',filters,'-t',str((MAX_FRAMES+1)/44100),'-f','null','-'],
               capture_output=True,text=True,check=True,timeout=120,max_job_bytes=512*1024**2)
    report=result.stderr
    if len(report.encode('utf-8'))>64000:raise ValueError('measurement diagnostics exceed bounds')
    def number(pattern):
        matches=re.findall(pattern,report,re.M)
        if not matches:raise ValueError('measurement summary is incomplete')
        value=float(matches[-1]);return value if math.isfinite(value) else None
    samples=number(r'Number of samples:\s*(\S+)')
    if samples is None or not samples.is_integer() or not 0<samples<=MAX_FRAMES:raise ValueError('decoded delivery exceeds four minutes or contains no audio')
    samples=int(samples)
    if expected_frames is not None and abs(samples-expected_frames)>1:raise ValueError('decoded delivery length differs from the accepted arrangement')
    if number(r'Number of NaNs:\s*(\S+)')!=0 or number(r'Number of Infs:\s*(\S+)')!=0:raise ValueError('decoded delivery contains nonfinite samples')
    peak=number(r'Peak level dB:\s*(\S+)');rms=number(r'RMS level dB:\s*(\S+)')
    integrated=number(r'^\s*I:\s*(\S+)\s+LUFS')
    true_peak=number(r'^\s*Peak:\s*(\S+)\s+dBFS')
    version=re.search(r'^ffmpeg version ([^\r\n]{1,512})',report,re.M)
    if version is None:raise ValueError('measurement tool version is unavailable')
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('audio changed during measurement')
    return {'decoded_frames':samples,'decoded_seconds':samples/44100,'sample_rate_hz':44100,'measurement_channels':2,
            'source_bytes':after.st_size,'source_modified_ns':after.st_mtime_ns,
            'sample_peak_dbfs':peak,'rms_dbfs':rms,'true_peak_dbtp':true_peak,
            'integrated_lufs':integrated if samples>=17640 and integrated is not None and integrated>-70 else None,
            'loudness_range_lu':number(r'^\s*LRA:\s*(\S+)\s+LU') if samples>=3*44100 else None,
            'tool_version':version.group(1),
            'silent':rms is None,'warnings':(['silent_output'] if rms is None else [])+(['true_peak_above_zero'] if true_peak is not None and true_peak>0 else []),
            'method':'FFmpeg astats decoded-frame/sample statistics and ebur128 true-peak/R128 measurement; no normalization',
            'limitations':'short/below-gate content may have no integrated LUFS; not speech intelligibility or a delivery loudness target'}

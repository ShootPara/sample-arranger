"""Render an explicit plugin bus graph as one atomically published normal MP3 job."""
import json
import math
from pathlib import Path
import tempfile
import shutil
from assets import digest
from graph import validate_graph,process_graph,validate_source_specs
from plugins import inspect
from process import run
from render import render
from engine_slots import bounded
from scratch import scratch
from events import emit


@bounded('render')
def render_music_graph(graph,sources,worker,seconds,jobs,*,voice=None,tempo=None,tail_seconds=0,max_work_bytes=1024**3,voice_settings=None,provenance=None,score=None):
    if (type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=240
            or type(tail_seconds) not in (int,float) or not math.isfinite(tail_seconds)
            or not 0<=tail_seconds<=1 or seconds+tail_seconds>240):
        raise ValueError("graph duration/tail must fit four minutes with a zero-to-one-second tail")
    ordered=validate_graph(graph,sources)
    emit('stage',stage='validating_graph')
    validate_source_specs(sources)
    for spec in sources.values():
        if round(spec.get('offset_seconds',0)*44100)>=round(seconds*44100):raise ValueError('source starts outside the logical arrangement')
        if 'target_bpm' in spec and tempo is not None and spec['target_bpm']!=tempo:raise ValueError('source target BPM differs from project tempo')
    if score is not None:
        from music import validate as validate_score
        validate_score(score)
        if score['duration_frames']!=round(seconds*44100) or score['bpm']!=tempo:raise ValueError('routing score timing mismatch')
    if any('score_part' in node for node in ordered) and score is None:raise ValueError('routing instrument requires accepted score')
    original={}
    for name,spec in sources.items():
        if 'silence' in spec:continue
        source=Path(spec["file"])
        if not source.is_file():raise ValueError("graph source missing")
        before=source.stat()
        checksum=digest(source)
        after=source.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError("graph source changed during fingerprinting")
        original[name]={"path":str(source.resolve()),"sha256":checksum,
                        "bytes":after.st_size,"modified_ns":after.st_mtime_ns}
    logical=round(seconds*44100)
    frames=logical+88200
    count=0;maximum_outputs=1
    for node in ordered:
        if "mix" in node:count+=1;continue
        report=inspect(worker,Path(node["plugin"]))
        found=[item for item in report["classes"] if item["class_id"]==node["class_id"]]
        if len(found)!=1:raise ValueError("graph plugin class unavailable")
        count+=found[0]["audio_outputs"]
        maximum_outputs=max(maximum_outputs,found[0]["audio_outputs"])
    estimate=frames*8*(len(sources)+count+maximum_outputs+2)+len(ordered)*32*1024*1024
    if estimate>max_work_bytes:raise ValueError("graph exceeds working-storage budget before decoding")
    jobs=Path(jobs);jobs.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(jobs).free<estimate+64*1024*1024:
        raise ValueError("insufficient free storage for bounded graph render")
    with scratch(jobs) as directory:
        root=Path(directory)
        prepared={}
        emit('stage',stage='preparing_sources')
        for name,spec in sources.items():
            destination=root/f"source-{name}.f32"
            if 'silence' in spec:
                with destination.open('wb') as output:output.truncate(frames*8)
                prepared[name]=destination
                continue
            source=Path(spec["file"])
            command=["ffmpeg","-nostdin","-v","error"]
            if spec.get("loop",False):command.extend(("-stream_loop","-1"))
            if source.suffix.lower()==".f32":command.extend(("-f","f32le","-ar","44100","-ac","2"))
            offset=round(spec.get('offset_seconds',0)*44100)
            rate=spec['target_bpm']/(spec['source_bpm']*spec['beat_scale']) if 'source_bpm' in spec else 1
            filters=f'aformat=sample_rates=44100:channel_layouts=stereo,atempo={rate:.12g},atrim=end_sample={logical-offset}'
            if offset:filters+=f',adelay={offset}S:all=1'
            filters+=f',apad=whole_len={frames},atrim=end_sample={frames}'
            command.extend(("-i",str(source),"-af",filters,
                            "-ar","44100","-ac","2","-f","f32le",str(destination)))
            run(command,check=True,timeout=300)
            if destination.stat().st_size!=frames*8:raise ValueError("graph decoder returned incomplete PCM")
            prepared[name]=destination
        from copy import deepcopy
        prepared_graph=deepcopy(graph)
        for node in prepared_graph['nodes']:
            if 'score_part' in node:
                from music import native_notes
                notes=root/(node['id']+'.notes.txt')
                notes.write_text(native_notes(score,node.pop('score_part')),encoding='utf-8')
                node['notes']=str(notes)
        emit('stage',stage='processing_graph')
        result=process_graph(prepared_graph,prepared,worker,root,tempo=tempo,max_work_bytes=max_work_bytes)
        for source in original.values():
            observed=Path(source["path"]).stat()
            if (observed.st_size,observed.st_mtime_ns)!=(source["bytes"],source["modified_ns"]):
                raise ValueError("graph source changed during processing")
        final_frames=round((seconds+tail_seconds)*44100)
        wav=root/"graph.wav"
        run(["ffmpeg","-nostdin","-v","error","-f","f32le","-ar","44100","-ac","2","-i",str(result["audio"]),
             "-af",f"atrim=end_sample={final_frames},alimiter=limit=0.9:level=0:latency=1",
             "-c:a","pcm_f32le",str(wav)],check=True,timeout=300)
        return render(wav,voice,final_frames/44100,jobs,attachments=result["attachments"],voice_settings=voice_settings,
                      provenance={**(provenance or {}),"routing":graph,"nodes":result["nodes"],"sources":original,
                                  "logical_seconds":seconds,"retained_tail_seconds":tail_seconds,
                                  "tempo_bpm":tempo,"pdc":"per-node before routing/mix",
                                  "estimated_work_bytes":estimate})

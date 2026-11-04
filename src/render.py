"""Render an existing music bed, optionally under supplied narration."""
import argparse
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import tempfile
import uuid
import shutil
from contextlib import closing
from pathlib import Path
from vst3_render import render_plugin
from planner import local_sections
from process import run
from assets import digest
from engine_slots import bounded
from scratch import scratch as owned_scratch
from events import emit


def catalog_music(database: Path, name: str) -> Path:
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute(
            "SELECT path FROM sample WHERE name = ? ORDER BY path LIMIT 2", (name,)
        ).fetchall()
    if len(rows) != 1:
        raise ValueError("sample name must match exactly one catalog entry; use --music for a specific path")
    return Path(rows[0][0])


def load_arrangement(plan: Path, database: Path) -> list[tuple[Path, float, float]]:
    with plan.open(encoding="utf-8-sig") as source:
        sections = json.load(source)
    return resolve_sections(sections, database)


def resolve_sections(sections, database: Path | None,*,resolver=None) -> list[tuple[Path, float, float]]:
    if not isinstance(sections, list) or not 1 <= len(sections) <= 16:
        raise ValueError("arrangement must contain 1 to 16 sections")
    result = []
    for section in sections:
        if not isinstance(section, dict) or set(section) not in (
            {"sample", "seconds"}, {"sample", "seconds", "source_bpm", "target_bpm", "beat_scale"}
        ):
            raise ValueError("section requires sample and seconds, with optional complete tempo settings")
        name, length = section["sample"], section["seconds"]
        if (not isinstance(name, str) or not name.strip()
                or type(length) not in (int, float) or not 0.1 <= length <= 240):
            raise ValueError("section requires a sample filename and 0.1 to 240 seconds")
        rate = 1.0
        if "source_bpm" in section:
            source, target, scale = (section[key] for key in ("source_bpm", "target_bpm", "beat_scale"))
            if (any(type(value) not in (int, float) for value in (source, target, scale))
                    or not (20 <= source <= 400 and 20 <= target <= 400 and scale in (0.5, 1, 2))):
                raise ValueError("BPM must be 20 to 400 and beat_scale must be 0.5, 1 or 2")
            rate = target / (source * scale)
            if not 0.5 <= rate <= 2:
                raise ValueError("tempo stretch must be between 0.5 and 2")
        result.append((resolver(name) if resolver else catalog_music(database, name), float(length), rate))
    return result


@bounded('render')
def render(music: Path, voice: Path | None, seconds: float, jobs: Path,
           *, sections: list[tuple[Path, float, float]] | None = None,
           worker: Path | None = None, plugin: Path | None = None,
           state: Path | None = None, tail_seconds: float = 0,
           instrument: Path | None = None, notes: Path | None = None,
           automation: Path | None = None, class_id: str | None = None,
           provenance: dict | None = None,attachments: list | None = None,music_layer: Path | None = None,voice_settings=None) -> dict:
    if not math.isfinite(seconds) or not 0 < seconds <= 240:
        raise ValueError("duration must be greater than zero and at most 240 seconds")
    if provenance is not None and (not isinstance(provenance,dict) or
                                  len(json.dumps(provenance,allow_nan=False).encode("utf-8"))>1_000_000):
        raise ValueError("render provenance exceeds bounds")
    if (worker is None and (plugin is not None or instrument is not None)) or (state is not None and plugin is None):
        raise ValueError("VST3 processing requires both worker and plugin")
    if bool(instrument) != bool(notes):
        raise ValueError("instrument and notes must be supplied together")
    if (automation or class_id) and not plugin:
        raise ValueError("effect automation and class selection require an effect")
    if not 0 <= tail_seconds <= 1 or seconds + tail_seconds > 240 or (tail_seconds and not plugin):
        raise ValueError("VST3 tail must be 0 to 1 seconds within the 240-second output limit")
    inputs = sections or [(music, seconds, 1.0)]
    source_records=[]
    pinned_project=(provenance or {}).get('project')
    emit('stage',stage='validating')
    if pinned_project:
        from project import inspect_data
        if not inspect_data(pinned_project)['ready']:raise ValueError('pinned project assets changed before rendering')
    for path in (*(path for path, _, _ in inputs), voice,music_layer):
        if path is not None and not path.is_file():
            raise ValueError(f"audio file is unavailable: {path}")
        if path is not None:
            before=path.stat()
            checksum=digest(path)
            after=path.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                raise ValueError("source changed during fingerprinting")
            source_records.append({"path":str(path.resolve()),"sha256":checksum,"bytes":after.st_size,
                                   "modified_ns":after.st_mtime_ns,"role":"narration" if path==voice else "composed_layer" if path==music_layer else "sample"})
    narration_record=None
    if voice is not None:
        from narration import inspect_fit
        narration_record=inspect_fit(voice,round(seconds*44100),voice_settings)
    elif voice_settings:raise ValueError('narration settings require supplied audio')
    with owned_scratch(jobs) as temp:
        stage = Path(temp)
        output = stage / "result.mp3"
        cmd = ["ffmpeg", "-nostdin", "-v", "error"]
        for path, _, _ in inputs:
            if os.environ.get("ARRANGER_REALTIME") == "1":
                cmd += ["-re"]
            cmd += ["-stream_loop", "-1", "-i", str(path.resolve())]
        filters = []
        bed = "0:a:0"
        next_input = len(inputs)
        instrument_record = None
        if sections:
            from fractions import Fraction
            elapsed=Fraction(0);previous=0
            for index, (_, length, rate) in enumerate(sections):
                elapsed+=Fraction(str(length))
                end=round(seconds*44100) if index==len(sections)-1 else round(elapsed*44100)
                count=end-previous;previous=end
                stretch = f"atempo={rate:.12g}," if rate != 1 else ""
                filters.append(
                    f"[{index}:a:0]{stretch}aformat=sample_rates=44100:channel_layouts=stereo,"
                    f"atrim=end_sample={count},asetpts=PTS-STARTPTS[s{index}]"
                )
            labels = "".join(f"[s{i}]" for i in range(len(sections)))
            filters.append(f"{labels}concat=n={len(sections)}:v=0:a=1[arranged]")
            bed = "[arranged]"
        if music_layer:
            cmd.extend(("-i",str(music_layer.resolve())))
            label=bed if bed.startswith("[") else f"[{bed}]"
            filters.append(f"[{next_input}:a:0]aformat=sample_rates=44100:channel_layouts=stereo,"
                           f"apad,atrim=end_sample={round(seconds*44100)},asetpts=PTS-STARTPTS[composed]")
            filters.append(f"{label}[composed]amix=inputs=2:duration=first:normalize=1[hybrid]")
            bed="[hybrid]";next_input+=1
        if instrument:
            silent = stage / "instrument-input.f32"
            with silent.open("wb") as silence:
                silence.truncate((round(seconds * 44100) + 88200) * 8)
            instrument_job = render_plugin(worker, instrument, silent, stage, notes=notes)
            if len(instrument_job.get("buses",[]))>1:
                raise ValueError("multi-output instrument requires explicit graph routing")
            instrument_latency = instrument_job["latency_samples"]
            if not 0 <= instrument_latency <= 88200:
                raise ValueError("instrument latency exceeds two-second processing budget")
            cmd += ["-f", "f32le", "-ar", "44100", "-ac", "2", "-i", instrument_job["audio"]]
            label = bed if bed.startswith("[") else f"[{bed}]"
            filters.append(f"[{next_input}:a:0]atrim=start_sample={instrument_latency}:"
                           f"end_sample={instrument_latency + round(seconds * 44100)},"
                           "asetpts=PTS-STARTPTS[aligned_instrument]")
            filters.append(f"{label}[aligned_instrument]amix=inputs=2:duration=first:normalize=1[instrument_mix]")
            bed = "[instrument_mix]"
            next_input += 1
            instrument_record = {"plugin": str(instrument.resolve()), "notes_sha256": hashlib.sha256(notes.read_bytes()).hexdigest(),
                                 "latency_samples": instrument_latency,
                                 "reported_tail_samples": instrument_job["tail_samples"],
                                 "tail_policy": "trim_at_arrangement_end",
                                 "state": str(Path(instrument_job["state"]).relative_to(stage))}
        frames=round(seconds*44100);fade_in=min(221,max(1,frames//2));fade_out=min(882,max(1,frames//2))
        label=bed if bed.startswith('[') else f'[{bed}]'
        filters.append(f'{label}aformat=sample_rates=44100:channel_layouts=stereo,atrim=end_sample={frames},'
                       f'afade=t=in:ss=0:ns={fade_in},afade=t=out:ss={frames-fade_out}:ns={fade_out}[music_edges]')
        bed='[music_edges]'
        if voice is not None:
            cmd += ["-i", str(voice.resolve())]
            input_label = bed if bed.startswith("[") else f"[{bed}]"
            options=narration_record['settings']
            filters.append(f"{input_label}volume={options['music_gain_db']}dB[bed]")
            filters.append(f"[{next_input}:a:0]aformat=sample_rates=44100:channel_layouts=stereo,asetpts=PTS-STARTPTS,"
                           f"volume={options['voice_gain_db']}dB,adelay={narration_record['offset_samples']}S:all=1,apad[placed_voice]")
            if options['ducking']:
                filters.append('[placed_voice]asplit=2[voice][key]')
                filters.append("[bed][key]sidechaincompress=threshold=0.025:ratio=6:attack=20:release=350[ducked]")
                mix_bed='ducked'
            else:mix_bed='bed';filters.append('[placed_voice]anull[voice]')
            filters.append(
                f"[{mix_bed}][voice]amix=inputs=2:duration=first:"
                "normalize=0,alimiter=limit=0.9:level=0:latency=1[mix]"
            )
            bed = "[mix]"
        frames = round(seconds * 44100)
        if plugin is not None:
            label = bed if bed.startswith("[") else f"[{bed}]"
            filters.append(f"{label}aformat=sample_rates=44100:channel_layouts=stereo,"
                           f"atrim=end_sample={frames},apad=pad_len=88200[plugin_input]")
            bed = "[plugin_input]"
        if filters:
            cmd += ["-filter_complex", ";".join(filters)]
        cmd += ["-map", bed]
        processing = None
        emit('stage',stage='rendering_audio')
        if plugin is not None:
            with owned_scratch(jobs) as scratch:
                scratch = Path(scratch)
                pcm = scratch / "input.f32"
                run(cmd + ["-ar", "44100", "-ac", "2", "-f", "f32le", str(pcm)],
                               check=True, timeout=300)
                native = render_plugin(worker, plugin, pcm, scratch, state=state,
                                       automation=automation, class_id=class_id)
                if len(native.get("buses",[]))>1:
                    raise ValueError("multi-output effect requires explicit graph routing")
                latency = native["latency_samples"]
                tail = min(round(tail_seconds * 44100), native["tail_samples"])
                if latency < 0 or tail < 0 or latency + tail > 88200:
                    raise ValueError("plugin latency and retained tail exceed the two-second processing budget")
                seconds_out = (frames + tail) / 44100
                run(
                    ["ffmpeg", "-nostdin", "-v", "error", "-f", "f32le", "-ar", "44100",
                     "-ac", "2", "-i", native["audio"], "-af",
                     f"atrim=start_sample={latency}:end_sample={latency + frames + tail},"
                     "asetpts=PTS-STARTPTS,alimiter=limit=0.85:level=0:latency=1",
                     "-c:a", "libmp3lame", "-b:a", "192k", str(output)],
                    check=True, timeout=300,
                )
                processing = {"plugin": str(plugin.resolve()), "latency_samples": latency,
                              "class_id": native["class_id"], "version": native["version"],
                              "plugin_sha256":native["plugin_sha256"],
                              "automation_points": native["automation_points"],
                              "automation_sha256": hashlib.sha256(automation.read_bytes()).hexdigest() if automation else None,
                              "reported_tail_samples": native["tail_samples"], "retained_tail_samples": tail,
                              "rendered_seconds": seconds_out, "state_restored": state is not None,
                              "component_state_restored":native["component_state_restored"],
                              "controller_state_restored":native["controller_state_restored"],
                              "controller_component_synced":native["controller_component_synced"],
                              "worker_memory_cap_bytes":native["worker_memory_cap_bytes"],
                              "input_channels":native["input_channels"],"output_channels":native["output_channels"],
                              "worker_sha256": hashlib.sha256(worker.read_bytes()).hexdigest()}
                for key in ("state", "controller_state"):
                    path = native[key]
                    processing[key] = None
                    processing[key+"_sha256"]=native.get(key+"_sha256")
                    if path is not None:
                        saved = Path(path)
                        processing[key] = saved.name
                        saved.replace(stage / saved.name)
        else:
            run(cmd + ["-t", str(seconds), "-vn", "-map_metadata", "-1",
                              "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame",
                              "-b:a", "192k", str(output)], check=True, timeout=300)
        from job_control import CURRENT_JOB
        admission=CURRENT_JOB.get()
        if admission and jobs.resolve()!=admission['root']:raise ValueError('render root differs from admitted job')
        job = jobs / (admission['job'] if admission else f"job-{uuid.uuid4()}")
        result = {"audio": str(job / output.name), "requested_seconds": seconds,
                  "bitrate_kbps": 192, "sample_rate_hz": 44100, "channels": 2,
                  "sources":source_records}
        for record in source_records:
            observed=Path(record["path"]).stat()
            if (observed.st_size,observed.st_mtime_ns)!=(record["bytes"],record["modified_ns"]):
                raise ValueError("source changed during render; no output published")
        probe=run(["ffprobe","-v","error","-select_streams","a:0","-show_entries",
                   "stream=codec_name,bit_rate,sample_rate,channels","-of","json",str(output)],
                  capture_output=True,text=True,check=True,timeout=30)
        streams=json.loads(probe.stdout).get("streams",[])
        if (len(streams)!=1 or streams[0].get("codec_name")!="mp3" or streams[0].get("channels")!=2
                or streams[0].get("sample_rate")!="44100" or streams[0].get("bit_rate")!="192000"):
            raise ValueError("encoded output violates fixed MP3 delivery settings")
        result["audio_sha256"]=digest(output)
        from audio_measurements import measure as measure_delivery
        emit('stage',stage='measuring_output')
        result['measurements']=measure_delivery(output,frames+(processing['retained_tail_samples'] if processing else 0))
        if digest(output)!=result['audio_sha256']:raise ValueError('encoded audio changed during delivery checking')
        result['music_edge_fades']={'in_samples':fade_in,'out_samples':fade_out,'before_narration':True}
        if narration_record:result['narration']=narration_record
        if admission:result['admission']={key:admission[key] for key in ('request_id','request_sha256')}
        result["attachments"]=[]
        for name,source in attachments or []:
            if not isinstance(name,str) or Path(name).name!=name or name in ("result.mp3","manifest.json"):
                raise ValueError("invalid owned attachment name")
            source=Path(source)
            if not source.is_file() or source.stat().st_size>16*1024*1024:
                raise ValueError("owned state attachment exceeds size bound")
            shutil.copyfile(source,stage/name)
            result["attachments"].append({"file":name,"sha256":digest(stage/name)})
        if provenance is not None:result["composition"]=provenance
        if processing:
            result["vst3"] = processing
        if instrument_record:
            result["instrument"] = instrument_record
            silent.unlink()
            Path(instrument_job["audio"]).unlink()
            (Path(instrument_job["audio"]).parent / "manifest.json").unlink()
        if sections:
            result["sections"] = [{"sample": path.name, "seconds": length, "tempo_rate": rate}
                                  for path, length, rate in sections]
        from artifacts import inventory
        result.update(format='sample-arranger-job',schema=1,**inventory(stage))
        (stage / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        marker = os.environ.get("ARRANGER_CANCEL_FILE")
        if marker and Path(marker).exists():
            raise ValueError("Render canceled before publication")
        if pinned_project and not inspect_data(pinned_project)['ready']:
            raise ValueError('pinned project assets changed during processing; no result published')
        emit('stage',stage='publishing')
        stage.rename(job)
        return result


def main():
    from process_group import own_process_tree
    own_process_tree()
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--music", type=Path)
    source.add_argument("--sample", help="Exact sample filename from --catalog")
    source.add_argument("--arrangement", type=Path, help="JSON list of sample sections")
    source.add_argument("--search", help="Build an arrangement from a literal filename search")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--voice", type=Path)
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--tail-seconds", type=float, default=0)
    parser.add_argument("--target-bpm", type=float, help="Rank search candidates by compatible tempo")
    parser.add_argument("--instrument", type=Path)
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--automation", type=Path)
    parser.add_argument("--class-id")
    args = parser.parse_args()
    if (args.music is None) != (args.catalog is not None):
        parser.error("supply --catalog with --sample or --arrangement")
    if (args.arrangement is None) != (args.seconds is not None):
        parser.error("--seconds is required for a single sample and inferred for an arrangement")
    try:
        sections = load_arrangement(args.arrangement, args.catalog) if args.arrangement else None
        if args.search is not None:
            sections = resolve_sections(local_sections(args.catalog, args.search, args.seconds, args.target_bpm), args.catalog)
        music = sections[0][0] if sections else args.music or catalog_music(args.catalog, args.sample)
        seconds = sum(length for _, length, _ in sections) if sections else args.seconds
        print(json.dumps(render(music, args.voice, seconds, args.jobs.resolve(), sections=sections,
                                worker=args.worker, plugin=args.plugin, state=args.state,
                                tail_seconds=args.tail_seconds, instrument=args.instrument, notes=args.notes,
                                automation=args.automation, class_id=args.class_id)))
    except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError) as error:
        parser.exit(1, f"render failed: {error}\n")


if __name__ == "__main__":
    main()

"""Render a bounded PCM job through a separate native VST3 worker."""
import argparse
import json
import subprocess
import tempfile
import uuid
import os
import math
from assets import digest
from pathlib import Path
from process import run
from resources import plugin_memory_bytes
from engine_slots import bounded

FRAME_BYTES = 8
MAX_FRAMES = 242 * 44100


@bounded('render')
def render_plugin(worker, plugin, source, jobs, *, state=None, pitch=None, notes=None, automation=None, class_id=None, tempo=None, sidechain=None, timeout=120):
    for path in (worker, source, state, notes, automation,sidechain):
        if path is not None and not path.is_file():
            raise ValueError(f"file unavailable: {path}")
    if not plugin.exists():
        raise ValueError(f"plugin unavailable: {plugin}")
    from plugins import fingerprint,resolve_state
    plugin_hash=fingerprint(plugin)
    class_id=resolve_state(plugin,state,class_id)
    size = source.stat().st_size
    if tempo is not None and (type(tempo) not in (int,float) or not math.isfinite(tempo) or not 40<=tempo<=240):
        raise ValueError("explicit plugin tempo must be 40 to 240 BPM")
    if not 0 < size <= FRAME_BYTES * MAX_FRAMES or size % FRAME_BYTES:
        raise ValueError("input must be complete stereo float32 frames, up to 242 seconds")
    jobs=Path(jobs);jobs.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vst3-", dir=jobs) as directory:
        stage = Path(directory)
        audio = stage / "output.f32"
        saved = stage / "component-state.bin"
        command = [str(worker.resolve()), str(plugin.resolve()), str(source.resolve()),
                   str(audio), str(state.resolve()) if state else "-", str(saved)]
        if pitch is not None:
            command.append(str(pitch))
        if notes is not None:
            command.append("@" + str(notes.resolve()))
        if automation is not None or class_id is not None or sidechain is not None:
            if pitch is None and notes is None:
                command.append("-")
            command.append(str(automation.resolve()) if automation else "-")
        if class_id is not None:
            if not isinstance(class_id,str) or len(class_id)!=32 or any(ch not in "0123456789ABCDEF" for ch in class_id):
                raise ValueError("class ID must contain 32 uppercase hexadecimal digits")
            command.append(class_id)
        elif sidechain is not None:command.append("-")
        if sidechain is not None:command.append(str(sidechain.resolve()))
        try:
            environment=dict(os.environ)
            environment.pop("ARRANGER_TEMPO",None)
            environment.pop("ARRANGER_STREAM_EVENTS",None)
            if tempo is not None:environment["ARRANGER_TEMPO"]=str(tempo)
            memory_cap=plugin_memory_bytes()
            process = run(command, capture_output=True, text=True,
                                     errors="replace", timeout=timeout,env=environment,max_job_bytes=memory_cap)
        except subprocess.TimeoutExpired as error:
            raise ValueError("VST3 worker timed out") from error
        if process.returncode:
            raise ValueError(f"VST3 worker failed ({process.returncode}): {process.stderr.strip()}")
        result = json.loads(process.stdout)
        if fingerprint(plugin)!=plugin_hash:raise ValueError("plugin binary changed during processing")
        if audio.stat().st_size != size or not saved.is_file() or saved.stat().st_size>16*1024*1024:
            raise ValueError("VST3 worker returned incomplete artifacts")
        count=result.get("output_buses",1)
        if type(count) is not int or not 1<=count<=8:raise ValueError("invalid output bus count")
        buses=[audio]+[stage/f"output.f32.bus{index}" for index in range(1,count)]
        if any(not path.is_file() or path.stat().st_size!=size for path in buses):
            raise ValueError("VST3 worker returned incomplete output buses")
        job = jobs / f"vst3-{uuid.uuid4()}"
        result.update(audio=str(job / audio.name), state=str(job / saved.name),
                      worker_memory_cap_bytes=memory_cap,
                      sample_rate_hz=44100, channels=2,tempo_bpm=tempo,
                      plugin_sha256=plugin_hash,state_sha256=digest(saved))
        result["buses"]=[str(job/path.name) for path in buses]
        controller = stage / "component-state.bin.controller"
        if controller.exists() and controller.stat().st_size>16*1024*1024:
            raise ValueError("controller state exceeds size budget")
        result["controller_state"] = str(job / controller.name) if controller.is_file() else None
        result["controller_state_sha256"]=digest(controller) if controller.is_file() else None
        (stage / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        stage.rename(job)
        return result


def main():
    from process_group import own_process_tree
    own_process_tree()
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("worker", "plugin", "input", "jobs"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--automation", type=Path, help="frame parameter-id normalized-value rows")
    parser.add_argument("--class-id")
    parser.add_argument("--tempo",type=float)
    parser.add_argument("--sidechain",type=Path,help="stereo float32 with exactly the main input frame count")
    midi = parser.add_mutually_exclusive_group()
    midi.add_argument("--pitch", type=int, choices=range(128), metavar="0..127")
    midi.add_argument("--notes", type=Path)
    args = parser.parse_args()
    try:
        result = render_plugin(args.worker, args.plugin, args.input, args.jobs.resolve(),
                               state=args.state, pitch=args.pitch, notes=args.notes, automation=args.automation,
                               class_id=args.class_id,tempo=args.tempo,sidechain=args.sidechain)
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

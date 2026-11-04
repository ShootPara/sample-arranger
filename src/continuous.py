"""Generate bar-aligned chunks and consume them without a save route."""
import argparse
import subprocess
import tempfile
import time
import winsound
import os
import threading
import json
import queue
from pathlib import Path
from render import catalog_music
from session import ContinuousSession
from spool import session_spool
from planner import local_sections
from device import DeviceStream
from fractions import Fraction
from process_group import popen
from engine_slots import bounded
from runtime import native_tool


def chunk_frames(index,bars,bpm):
    clock=Fraction(240*44100*bars)/Fraction(str(bpm))
    return round((index+1)*clock)-round(index*clock)


@bounded('continuous')
def play(source, *, bpm=120.0, chunks=1000000, chunk_seconds=60, consume=None, sources=None,
         sink=None, worker=None, plugin=None,builtin=False,cancel_event=None,on_event=None,state=None,class_id=None,instruments=None,intent=None,effect_output_bus=0):
    if not 40 <= bpm <= 240 or not 1 <= chunk_seconds <= 120:
        raise ValueError("invalid tempo or chunk duration")
    if type(chunks) is not int or not 1<=chunks<=1000000:raise ValueError("invalid continuous chunk count")
    from compose import validate_instruments
    instruments=validate_instruments(instruments or {})
    intent={} if intent is None else intent
    if not isinstance(intent,dict) or intent.keys()-{'root','mode','progression','parts','density','seed','melody_pattern'} or (intent and not builtin):
        raise ValueError('continuous musical intention requires built-in planning and bounded musical fields')
    from music import compile_intent
    compile_intent({'bars':1,'bpm':bpm,**intent})
    if instruments and (not builtin or not worker or consume):raise ValueError("continuous instruments require built-in planning, native worker and device sink")
    if (plugin and not worker) or (worker and not plugin and not instruments):raise ValueError("continuous native processing needs both worker and plugin/instrument")
    if (state or class_id) and not plugin:raise ValueError("continuous preset/class requires an effect")
    if type(effect_output_bus) is not int or not 0<=effect_output_bus<=7 or effect_output_bus and not plugin:raise ValueError('continuous effect bus requires a plugin and index0..7')
    if consume is None and sink is None:
        sink=native_tool('arranger-playback.exe')
        if not sink.is_file():raise ValueError("native gapless device sink is unavailable; build native tools first")
    bars=max(1,round(chunk_seconds*bpm/240))
    duration = bars * 240 / bpm
    frames = int(duration*44100)+1
    duration = frames / 44100
    chunk_bytes = frames * 4 + 128
    if chunk_bytes > 22_000_000:
        raise ValueError("chunk allocation exceeds byte budget")
    root = Path(os.environ["LOCALAPPDATA"], "SampleArranger/continuous")
    choices = sources or [source]
    musical_state={"next_bar":0,"previous_chord":[60,64,67],"seed":intent.get('seed',0)}
    scores={}
    with session_spool(root) as root:

        def generate(index, destination, stop):
            frames=chunk_frames(index,bars,bpm)
            duration=frames/44100
            if builtin:
                from music import compile_intent
                from palette import render_score
                base_density=intent.get('density','medium')
                densities={'sparse':('sparse','sparse','medium','sparse'),'medium':('sparse','medium','medium','busy'),'busy':('medium','busy','busy','medium')}
                score=compile_intent({**intent,"bpm":bpm,"bars":bars,"resolve":False,
                    "bar_offset":musical_state["next_bar"],"previous_chord":musical_state["previous_chord"],
                    "seed":musical_state["seed"],"density":densities[base_density][index%4]})
                from music import render_without_parts
                audio_score=render_without_parts(score,instruments)
                if audio_score['notes']:render_score(audio_score,destination,frames_override=frames,fade_end=False)
                else:
                    import wave
                    with wave.open(str(destination),'wb') as audio:
                        audio.setparams((2,2,44100,0,'NONE','not compressed'))
                        remaining=frames*4
                        while remaining:
                            count=min(remaining,65536);audio.writeframesraw(bytes(count));remaining-=count
                if instruments:scores[str(destination)]=score
                musical_state.update(score["ending_state"])
                return
            command = ["ffmpeg", "-nostdin", "-v", "error", "-stream_loop", "-1",
                       "-i", str(choices[index % len(choices)].resolve()),
                       "-t", str(duration), "-ar", "44100", "-ac", "2",
                       "-af", f"apad,atrim=end_sample={frames}", "-fs", str(chunk_bytes),
                       "-c:a", "pcm_s16le", str(destination)]
            with popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW) as child:
                deadline = time.monotonic() + 60
                while child.poll() is None:
                    if stop.wait(0.05) or time.monotonic() > deadline:
                        child.kill()
                        child.wait()
                        if not stop.is_set():
                            raise TimeoutError("chunk generation deadline exceeded")
                        return
                if child.returncode:
                    raise ValueError("chunk decoder failed")

        def audible(path, stop):
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            import wave
            with wave.open(str(path)) as audio:seconds=audio.getnframes()/audio.getframerate()
            deadline = time.monotonic() + seconds
            try:
                while not stop.wait(0.02) and time.monotonic() < deadline:
                    pass
            finally:
                winsound.PlaySound(None, 0)

        session = ContinuousSession(root, generate, consume or audible,
                                    max_chunk_bytes=22_000_000, max_chunk_seconds=122)
        marker=os.environ.get("ARRANGER_CANCEL_FILE")
        external_cancel=threading.Event();watcher_done=threading.Event();started=time.monotonic()
        health=queue.Queue(maxsize=1)
        def emit(event):
            if on_event:
                try:health.put_nowait({"state":"playing","chunks_submitted":session.completed,
                                      "queued_chunks":session.buffer.qsize(),**event})
                except queue.Full:pass
        def report():
            while not watcher_done.is_set():
                try:event=health.get(timeout=0.1)
                except queue.Empty:continue
                try:on_event(event)
                except (OSError,ValueError):external_cancel.set();session.cancel();return
        if on_event:threading.Thread(target=report,daemon=True).start()
        def watch():
            while not watcher_done.wait(0.05):
                if (marker and Path(marker).exists()) or (cancel_event is not None and cancel_event.is_set()):
                    external_cancel.set();session.cancel();return
        watcher=threading.Thread(target=watch,daemon=True);watcher.start()
        processing_policy=None
        try:
            if sink:
                def transport_failed(error):
                    session.fail(error);emit({'state':'failed','error_code':'AUDIO_TRANSPORT_STOPPED','reason':str(error)})
                with DeviceStream(sink, worker, plugin,bpm=bpm,state=state,class_id=class_id,on_progress=emit,instruments=instruments or None,effect_output_bus=effect_output_bus,on_failure=transport_failed,cancel_event=external_cancel) as device:
                    processing_policy=device.processing_policy()
                    def device_consume(path,stop):
                        if instruments:device.consume(path,stop,score=scores.pop(str(path)))
                        else:device.consume(path,stop)
                        emit({"chunks_submitted":session.completed+1,"frames_submitted":device.frames_sent,
                              "frames_acknowledged":device.frames_heard})
                    session.consume=device_consume
                    session.run(chunks)
                    if not external_cancel.is_set():device.drain()
            else:session.run(chunks)
        except (OSError,TimeoutError):
            if not external_cancel.is_set():raise
        finally:
            watcher_done.set();watcher.join(timeout=1)
        return {"state":"stopped" if external_cancel.is_set() else "completed", "chunks_submitted":session.completed,
                "generated_chunks":session.generated,"elapsed_seconds":round(time.monotonic()-started,3),
                "max_chunk_bytes":22_000_000,"max_owned_audio_bytes":88_000_000,"audio_retention":"disposable",
                'processing_policy':processing_policy,
                'output_policy':{'effect_bus':effect_output_bus if plugin else None,'unselected_plugin_buses':'discarded in memory; no auxiliary output files'}}


if __name__ == "__main__":
    from process_group import own_process_tree
    own_process_tree()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sample")
    source.add_argument("--builtin",action="store_true")
    parser.add_argument("--bpm", type=float, default=120)
    parser.add_argument("--chunks", type=int, default=1000000)
    parser.add_argument("--evolve", action="store_true", help="Rotate catalog candidates matched by the sample term")
    parser.add_argument("--sink", type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--plugin", type=Path)
    args = parser.parse_args()
    try:
        if not args.builtin and not args.catalog:parser.error("--sample requires --catalog")
        if args.builtin and args.evolve:parser.error("--evolve is for sample rotation; built-in mode evolves its score")
        sections = local_sections(args.catalog, args.sample, 60, args.bpm) if args.evolve else []
        sources = [catalog_music(args.catalog, item["sample"]) for item in sections]
        play(None if args.builtin else sources[0] if sources else catalog_music(args.catalog, args.sample),
             bpm=args.bpm, chunks=args.chunks, sources=sources,
             sink=args.sink, worker=args.worker, plugin=args.plugin,builtin=args.builtin)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, TimeoutError) as error:
        parser.exit(1, f"playback failed: {error}\n")

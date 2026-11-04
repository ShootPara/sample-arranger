"""Compile musical intentions and render the built-in palette to a normal MP3 job."""
import argparse
import json
from pathlib import Path
import tempfile
from music import compile_intent,TPQ
from palette import render_score
from render import render
from music import PARTS,native_notes,validate
from process import run
from plugins import inspect
from graph import process_graph
from engine_slots import bounded
from scratch import scratch


def compose(intent,jobs,*,voice=None,worker=None,plugin=None,instruments=None,voice_settings=None):
    score=compile_intent(intent)
    return render_score_job(score,jobs,voice=voice,worker=worker,plugin=plugin,instruments=instruments,voice_settings=voice_settings)


def validate_instruments(instruments):
    if not isinstance(instruments,dict) or instruments.keys()-PARTS.keys():raise ValueError("unknown instrument part")
    for part,spec in instruments.items():
        if (not isinstance(spec,dict) or not {"plugin","class_id"}<=spec.keys()
                or spec.keys()-{"plugin","class_id","state","outputs"}
                or not isinstance(spec["plugin"],str) or not spec["plugin"]
                or not isinstance(spec["class_id"],str) or len(spec["class_id"])!=32
                or any(ch not in "0123456789ABCDEF" for ch in spec["class_id"])
                or ("state" in spec and not isinstance(spec["state"],str))):
            raise ValueError("invalid instrument assignment")
        if "outputs" in spec and (not isinstance(spec["outputs"],list) or not 1<=len(spec["outputs"])<=8):
            raise ValueError("instrument output selection exceeds bounds")
        import math
        for output in spec.get("outputs",[]):
            if (not isinstance(output,dict) or "bus" not in output or output.keys()-{"bus","gain"}
                    or type(output["bus"]) is not int or not 0<=output["bus"]<8
                    or type(output.get("gain",1)) not in (int,float)
                    or not math.isfinite(output.get("gain",1)) or not -4<=output.get("gain",1)<=4):
                raise ValueError("invalid bounded instrument output route")
    return instruments


@bounded('render')
def render_score_job(score,jobs,*,voice=None,worker=None,plugin=None,state=None,automation=None,class_id=None,provenance=None,instruments=None,sections=None,voice_settings=None):
    validate(score)
    instruments=validate_instruments(instruments or {})
    instruments={part:spec for part,spec in instruments.items() if any(note["part"]==part for note in score["notes"])}
    if instruments and not worker:raise ValueError("assigned instruments require the native worker")
    if sections and abs(round(sum(length for _,length,_ in sections)*44100)-score["duration_frames"])>1:
        raise ValueError("sample plan and composed score must have matching duration")
    with scratch(jobs) as directory:
        root=Path(directory);source=root/"palette.wav"
        from music import render_without_parts
        builtin=render_without_parts(score,instruments)
        if builtin["notes"]:palette=render_score(builtin,source)
        else:
            import wave
            with wave.open(str(source),"wb") as output:
                output.setparams((2,2,44100,0,"NONE","not compressed"))
                remaining=score["duration_frames"]*4
                while remaining:
                    count=min(remaining,65536);output.writeframesraw(bytes(count));remaining-=count
            palette={"frames":score["duration_frames"],"palette":"all parts assigned to VST3","rights":"user-selected plugin terms apply"}
        duration=palette["frames"]/44100
        attachments=[]
        routing=None
        if instruments:
            frames=palette["frames"]+88200
            prepared=root/"builtin.f32"
            run(["ffmpeg","-nostdin","-v","error","-i",str(source),"-af",f"apad=whole_len={frames},atrim=end_sample={frames}",
                 "-ar","44100","-ac","2","-f","f32le",str(prepared)],check=True,timeout=120)
            silence=root/"silence.f32"
            with silence.open("wb") as output:output.truncate(frames*8)
            nodes=[];outputs=[{"node":"builtin","bus":0}]
            for part,spec in instruments.items():
                notes=root/f"{part}.notes.txt";notes.write_text(native_notes(score,part),encoding="utf-8")
                inventory=inspect(worker,Path(spec["plugin"]))
                classes=[item for item in inventory["classes"] if item["class_id"]==spec["class_id"] and item["audio_inputs"]==0]
                if len(classes)!=1:raise ValueError("assigned component is not a supported instrument")
                count=classes[0]["audio_outputs"]
                if count!=1 and "outputs" not in spec:raise ValueError("multi-output instrument requires explicit output selection")
                selected=spec.get("outputs",[{"bus":0,"gain":1}])
                for output in selected:
                    if not isinstance(output,dict) or not {"bus"}<=output.keys() or output.keys()-{"bus","gain"}:
                        raise ValueError("invalid instrument output selection")
                    outputs.append({"node":part,**output})
                node={"id":part,"plugin":spec["plugin"],"class_id":spec["class_id"],
                      "input":{"node":"silence","bus":0},"notes":str(notes)}
                if spec.get("state"):node["state"]=spec["state"]
                nodes.append(node)
            nodes.append({"id":"ensemble","mix":outputs});output={"node":"ensemble","bus":0}
            graph={"nodes":nodes,"outputs":[output]}
            routing=process_graph(graph,{"builtin":prepared,"silence":silence},worker,root,tempo=score["bpm"])
            attachments=routing["attachments"]
            source=root/"ensemble.wav"
            run(["ffmpeg","-nostdin","-v","error","-f","f32le","-ar","44100","-ac","2","-i",str(routing["audio"]),
                 "-af",f"atrim=end_sample={palette['frames']},alimiter=limit=0.9:level=0:latency=1",
                 "-c:a","pcm_f32le",str(source)],check=True,timeout=120)
        metadata={"score":score,"palette":palette,**(provenance or {})}
        if routing:metadata["instrument_graph"]={"nodes":routing["nodes"],"routing":routing["graph"],"voice_after_graph":True}
        return render(sections[0][0] if sections else source,voice,duration,jobs,sections=sections,
                      music_layer=source if sections else None,worker=worker,plugin=plugin,state=state,automation=automation,class_id=class_id,
                      provenance=metadata,attachments=attachments,voice_settings=voice_settings)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intent",type=Path,required=True)
    parser.add_argument("--jobs",type=Path,required=True)
    parser.add_argument("--voice",type=Path)
    parser.add_argument("--worker",type=Path)
    parser.add_argument("--plugin",type=Path)
    args=parser.parse_args()
    try:
        intent=json.loads(args.intent.read_text(encoding="utf-8-sig"))
        print(json.dumps(compose(intent,args.jobs,voice=args.voice,worker=args.worker,plugin=args.plugin)))
    except (ValueError,OSError) as error:parser.exit(1,f"{error}\n")

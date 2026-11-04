"""Bounded offline stereo-bus graph: explicit sidechains, outputs and per-node PDC."""
import json
from pathlib import Path
import re
import shutil
from plugins import inspect,fingerprint
from vst3_render import render_plugin
from assets import digest
from engine_slots import bounded

NAME=re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}\Z")


def validate_source_specs(sources):
    import math
    for spec in sources.values():
        if isinstance(spec,dict) and spec=={'silence':True} and type(spec['silence']) is bool:continue
        if (not isinstance(spec,dict) or not {'file'}<=spec.keys() or spec.keys()-{'file','loop','offset_seconds','source_bpm','target_bpm','beat_scale'}
                or not isinstance(spec['file'],str) or not spec['file'] or type(spec.get('loop',False)) is not bool):
            raise ValueError('graph source requires a local file/optional loop or explicit silence')
        offset=spec.get('offset_seconds',0)
        if type(offset) not in (int,float) or not math.isfinite(offset) or not 0<=offset<240:raise ValueError('invalid graph source placement')
        tempo={'source_bpm','target_bpm','beat_scale'}
        if spec.keys()&tempo:
            if not tempo<=spec.keys():raise ValueError('source tempo requires source/target BPM and explicit beat_scale')
            if (any(type(spec[key]) not in (int,float) or not math.isfinite(spec[key]) for key in tempo)
                    or not 20<=spec['source_bpm']<=400 or not 20<=spec['target_bpm']<=400
                    or spec['beat_scale'] not in (.5,1,2) or not .5<=spec['target_bpm']/(spec['source_bpm']*spec['beat_scale'])<=2):
                raise ValueError('invalid bounded graph tempo choice')


def validate_graph(graph,sources):
    if not isinstance(graph,dict) or set(graph)!={"nodes","outputs"}:
        raise ValueError("graph requires nodes and outputs")
    nodes,outputs=graph["nodes"],graph["outputs"]
    if (not isinstance(sources,dict) or not 1<=len(sources)<=8
            or any(not isinstance(key,str) or not NAME.fullmatch(key) for key in sources)
            or not isinstance(nodes,list) or not 1<=len(nodes)<=8
            or not isinstance(outputs,list) or not 1<=len(outputs)<=16):
        raise ValueError("graph source/node/output bounds exceeded")
    known=set(sources)
    folded={name.casefold() for name in known}
    if len(folded)!=len(known):raise ValueError("graph names collide on Windows")
    reserved={"CON","PRN","AUX","NUL"}|{f"{prefix}{n}" for prefix in ("COM","LPT") for n in range(1,10)}
    for node in nodes:
        if (not isinstance(node,dict) or not isinstance(node.get("id"),str)
                or not NAME.fullmatch(node["id"]) or node["id"] in known):
            raise ValueError("invalid or duplicate graph node")
        if node["id"].casefold() in folded or node["id"].upper() in reserved:raise ValueError("invalid Windows node name")
        folded.add(node["id"].casefold())
        if "mix" in node:
            if set(node)!={"id","mix"} or not isinstance(node["mix"],list) or not 1<=len(node["mix"])<=16:
                raise ValueError("invalid bounded mixer node")
        elif (not {"plugin","class_id","input"}<=node.keys()
                or node.keys()-{"id","plugin","class_id","input","sidechain","state","notes","automation","automation_points","score_part"}
                or not isinstance(node["class_id"],str) or not re.fullmatch(r"[0-9A-F]{32}",node["class_id"])
                or any(not isinstance(node[key],str) or not node[key] or len(node[key])>32768
                       for key in ("plugin","state","notes","automation") if key in node)):
            raise ValueError("invalid plugin identity/path")
        if 'score_part' in node and (node['score_part'] not in ('bass','chords','melody') or 'notes' in node):
            raise ValueError('choose a score part or external MIDI file, not both')
        if 'automation_points' in node:
            import math
            points=node['automation_points']
            if 'automation' in node or not isinstance(points,list) or len(points)>8192:
                raise ValueError('use a bounded inline automation lane or file, not both')
            seen=set();previous=-1
            for point in points:
                if (not isinstance(point,dict) or set(point)!={'frame','id','value'}
                        or type(point['frame']) is not int or not 0<=point['frame']<=242*44100
                        or point['frame']<previous or type(point['id']) is not int or not 0<=point['id']<2**32
                        or type(point['value']) not in (int,float) or not math.isfinite(point['value']) or not 0<=point['value']<=1
                        or (point['frame'],point['id']) in seen):
                    raise ValueError('invalid, unordered or duplicate automation point')
                seen.add((point['frame'],point['id']));previous=point['frame']
        known.add(node["id"])
    def reference(value,output=False):
        allowed={"node","bus","gain"} if output else {"node","bus"}
        if (not isinstance(value,dict) or not {"node","bus"}<=value.keys() or value.keys()-allowed
                or not isinstance(value["node"],str) or value["node"] not in known
                or type(value["bus"]) is not int or not 0<=value["bus"]<8):
            raise ValueError("invalid or unknown graph reference")
        if output:
            import math
            gain=value.get("gain",1)
            if type(gain) not in (int,float) or not math.isfinite(gain) or not -4<=gain<=4:
                raise ValueError("graph output gain must be finite from -4 to4")
    for node in nodes:
        if "mix" in node:
            for value in node["mix"]:reference(value,True)
        else:reference(node["input"])
        if "sidechain" in node:reference(node["sidechain"])
    for output in outputs:reference(output,True)
    pending=list(nodes)
    ordered=[]
    ready=set(sources)
    while pending:
        progress=False
        for node in pending[:]:
            dependencies={value["node"] for value in node["mix"]} if "mix" in node else {node["input"]["node"]}
            if "sidechain" in node:dependencies.add(node["sidechain"]["node"])
            if dependencies<=ready:
                ordered.append(node);ready.add(node["id"]);pending.remove(node);progress=True
        if not progress:raise ValueError("graph contains a feedback cycle")
    return ordered


def align(source,destination,latency,frames):
    if type(latency) is not int or not 0<=latency<=88200 or latency>=frames:
        raise ValueError("graph node latency exceeds two-second budget")
    with source.open("rb") as input,destination.open("wb") as output:
        input.seek(latency*8)
        shutil.copyfileobj(input,output,1024*1024)
        remaining=latency*8
        while remaining:
            block=min(remaining,65536)
            output.write(bytes(block));remaining-=block
    if destination.stat().st_size!=frames*8:raise ValueError("aligned graph bus frame count mismatch")


def mix_buses(selected,destination,frames):
    import numpy as np
    handles=[path.open("rb") for path,_ in selected]
    try:
        with destination.open("wb") as output:
            for start in range(0,frames,4096):
                count=min(4096,frames-start)*2;audio=np.zeros(count,dtype=np.float64)
                for handle,(_,gain) in zip(handles,selected):
                    values=np.frombuffer(handle.read(count*4),dtype="<f4")
                    if len(values)!=count or not np.isfinite(values).all():raise ValueError("invalid/nonfinite graph output")
                    # NumPy2 scalar promotion otherwise multiplies float32 before
                    # adding to float64, overflowing even a later canceling sum.
                    audio+=values.astype(np.float64)*gain
                if not np.isfinite(audio).all():raise ValueError("nonfinite graph mix")
                with np.errstate(over='ignore',invalid='ignore'):converted=audio.astype('<f4')
                if not np.isfinite(converted).all():raise ValueError('graph mix exceeds float32 finite range')
                output.write(converted.tobytes())
    finally:
        for handle in handles:handle.close()


@bounded('render')
def process_graph(graph,sources,worker,root,*,tempo=None,max_work_bytes=1024**3):
    """All sources are equal-length stereo44.1 float32, including caller's tail reserve.

    root is an owned temporary directory. No intermediate is a delivered artifact.
    Each bus is compensated before any downstream mix/sidechain use.
    """
    ordered=validate_graph(graph,sources)
    sizes={Path(source).stat().st_size for source in sources.values()}
    if len(sizes)!=1:raise ValueError("graph sources must have matching frame counts")
    size=sizes.pop()
    if size%8 or not 0<size<=242*44100*8:raise ValueError("invalid bounded graph source PCM")
    frames=size//8
    inventories={}
    output_count=0;maximum_outputs=1
    for node in ordered:
        if "mix" in node:output_count+=1;continue
        plugin=Path(node["plugin"])
        inventory=inspect(worker,plugin)
        matches=[item for item in inventory["classes"] if item["class_id"]==node["class_id"]]
        if len(matches)!=1:raise ValueError("graph class is unavailable")
        count=matches[0]["audio_outputs"]
        if not 1<=count<=8:raise ValueError("graph requires one to eight stereo outputs")
        inventories[node["id"]]=inventory
        output_count+=count
        maximum_outputs=max(maximum_outputs,count)
    estimate=size*(len(sources)+output_count+maximum_outputs+2)+len(ordered)*32*1024*1024
    if estimate>max_work_bytes or shutil.disk_usage(root).free<estimate+64*1024*1024:
        raise ValueError("graph exceeds configured working-storage budget")
    available={name:[Path(path)] for name,path in sources.items()}
    records=[]
    attachments=[]
    def resolve(reference):
        buses=available[reference["node"]]
        if reference["bus"]>=len(buses):raise ValueError("graph references an unavailable output bus")
        return buses[reference["bus"]]
    for node in ordered:
        node_root=root/node["id"]
        node_root.mkdir()
        if "mix" in node:
            destination=node_root/"mixed.f32"
            mix_buses([(resolve(value),value.get("gain",1)) for value in node["mix"]],destination,frames)
            available[node["id"]]=[destination]
            records.append({"id":node["id"],"kind":"mixer","inputs":node["mix"],"output_buses":1})
            continue
        options={key:Path(node[key]) for key in ("state","notes","automation") if key in node}
        if node.get('automation_points'):
            if any(point['frame']>=frames for point in node['automation_points']):raise ValueError('automation point exceeds render frame range')
            automation=node_root/'automation.txt'
            automation.write_text(''.join(f"{point['frame']} {point['id']} {point['value']}\n" for point in node['automation_points']),encoding='utf-8')
            options['automation']=automation
        if "sidechain" in node:options["sidechain"]=resolve(node["sidechain"])
        result=render_plugin(worker,Path(node["plugin"]),resolve(node["input"]),node_root,
                             class_id=node["class_id"],tempo=tempo,**options)
        if result["plugin_sha256"]!=inventories[node["id"]]["plugin_sha256"]:
            raise ValueError("plugin binary changed after graph preflight")
        buses=[]
        for index,path in enumerate(result["buses"]):
            destination=node_root/f"aligned-{index}.f32"
            align(Path(path),destination,result["latency_samples"],frames)
            Path(path).unlink()
            buses.append(destination)
        available[node["id"]]=buses
        saved={}
        for kind in ("state","controller_state"):
            if result[kind]:
                source=Path(result[kind])
                name=f"{node['id']}.component.bin"+(".controller" if kind=="controller_state" else "")
                attachments.append((name,source))
                saved[kind]={"file":name,"sha256":digest(source)}
        records.append({"id":node["id"],"class_id":result["class_id"],
                        "plugin":node["plugin"],"name":result["name"],"version":result["version"],
                        "plugin_sha256":inventories[node["id"]]["plugin_sha256"],
                        "latency_samples":result["latency_samples"],"tail_samples":result["tail_samples"],
                        "component_state_restored":result["component_state_restored"],
                        "controller_state_restored":result["controller_state_restored"],
                        "controller_component_synced":result["controller_component_synced"],
                        "worker_memory_cap_bytes":result["worker_memory_cap_bytes"],
                        "input_channels":result["input_channels"],"output_channels":result["output_channels"],
                        "output_buses":result["output_buses"],"state":saved})
    selected=[(resolve(output),output.get("gain",1)) for output in graph["outputs"]]
    mixed=root/"mix.f32"
    mix_buses(selected,mixed,frames)
    return {"audio":mixed,"attachments":attachments,"nodes":records,"frames":frames,
            "estimated_work_bytes":estimate,"graph":graph}

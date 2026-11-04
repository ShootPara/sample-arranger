"""Isolated plugin inspection and app-owned state presets (not .vstpreset files)."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
from process import run
from assets import digest
from resources import plugin_memory_bytes
from engine_slots import bounded


def resolve_state(plugin,state,class_id=None):
    """Validate recognized app state identities; raw third-party states stay unverified."""
    if state is None:return class_id
    if not state.is_file() or state.stat().st_size>16*1024*1024:raise ValueError("invalid state file")
    manifest=state.parent/"manifest.json"
    if not manifest.is_file():return class_id
    if manifest.stat().st_size>2_000_000:raise ValueError("state manifest exceeds bound")
    metadata=json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(metadata,dict):raise ValueError("invalid state manifest")
    composition=metadata.get("composition",{})
    if isinstance(composition,dict):
        graph=composition.get("instrument_graph",composition)
        if isinstance(graph,dict) and isinstance(graph.get("nodes"),list):
            matches=[node for node in graph["nodes"] if isinstance(node,dict) and
                     isinstance(node.get("state"),dict) and
                     node["state"].get("state",{}).get("file")==state.name]
            if matches:
                if len(matches)!=1:raise ValueError("ambiguous graph state identity")
                node=matches[0];streams=node["state"]
                metadata={"plugin_sha256":node["plugin_sha256"],"class_id":node["class_id"],
                          "state_sha256":streams["state"]["sha256"],
                          "controller_state_sha256":streams.get("controller_state",{}).get("sha256")}
    metadata=metadata.get("vst3",metadata)
    if not isinstance(metadata,dict):raise ValueError("invalid plugin state metadata")
    if metadata.get("plugin_sha256") and metadata["plugin_sha256"]!=fingerprint(plugin):
        raise ValueError("saved state belongs to a different plugin binary")
    if metadata.get("class_id"):
        if class_id is not None and class_id!=metadata["class_id"]:raise ValueError("saved state class differs from requested class")
        class_id=metadata["class_id"]
    expected=metadata.get("component_sha256",metadata.get("state_sha256"))
    if expected and digest(state)!=expected:raise ValueError("saved component state checksum mismatch")
    expected=metadata.get("controller_sha256",metadata.get("controller_state_sha256"))
    controller=Path(str(state)+".controller")
    if expected and (not controller.is_file() or digest(controller)!=expected):
        raise ValueError("saved controller state missing or checksum mismatch")
    return class_id


def fingerprint(plugin):
    files = [plugin] if plugin.is_file() else sorted((plugin / "Contents/x86_64-win").glob("*.vst3"))
    if not files:
        raise ValueError("no Windows x64 plugin binary found")
    result=hashlib.sha256()
    for source in files:
        result.update(source.name.encode("utf-8"))
        with source.open("rb") as stream:
            for block in iter(lambda:stream.read(1024*1024),b""):
                result.update(block)
    return result.hexdigest()


@bounded('plugin-inspect')
def inspect(worker,plugin,*,state=None,class_id=None):
    command=[str(worker),"--inspect",str(plugin)]
    if state:
        class_id=resolve_state(plugin,state,class_id)
        if class_id is None:raise ValueError("raw state inspection needs an explicit component ID")
        command.extend((str(state),class_id))
    elif class_id:command.extend(("-",class_id))
    result=run(command,capture_output=True,text=True,timeout=30,max_job_bytes=plugin_memory_bytes())
    if result.returncode:
        raise ValueError(f"Plugin inspection failed ({result.returncode}): {result.stderr.strip()}")
    if len(result.stdout.encode("utf-8"))>4_000_000:
        raise ValueError("plugin inspection exceeds result limit")
    report=json.loads(result.stdout)
    if not isinstance(report.get("classes"),list) or len(report["classes"])>256:
        raise ValueError("invalid plugin class inventory")
    report.update(plugin_sha256=fingerprint(plugin))
    return report


@bounded('plugin-inspect')
def convert_parameter(worker,plugin,class_id,parameter_id,*,state=None,display=None,normalized=None):
    import math
    if (not isinstance(class_id,str) or len(class_id)!=32 or any(c not in '0123456789ABCDEF' for c in class_id)
            or type(parameter_id) is not int or not 0<=parameter_id<=2**32-1 or (display is None)==(normalized is None)):
        raise ValueError('parameter conversion requires one displayed or normalized value and a component/parameter ID')
    if display is not None:
        if not isinstance(display,str) or not display or len(display.encode('utf-16-le'))>254:raise ValueError('displayed parameter text must fit127 UTF16 units')
        direction,value='display',display
    else:
        if type(normalized) not in (int,float) or not math.isfinite(normalized) or not 0<=normalized<=1:raise ValueError('normalized parameter value must be0..1')
        direction,value='normalized',str(normalized)
    class_id=resolve_state(plugin,state,class_id)
    result=run([str(worker),'--parameter',str(plugin),class_id,str(state) if state else '-',str(parameter_id),direction,value],
               capture_output=True,text=True,timeout=30,max_job_bytes=plugin_memory_bytes())
    if result.returncode:raise ValueError('Plugin parameter conversion failed: '+result.stderr.strip()[:2000])
    if len(result.stdout.encode('utf-8'))>64000:raise ValueError('parameter conversion result exceeds bound')
    report=json.loads(result.stdout)
    if (not isinstance(report,dict) or report.get('class_id')!=class_id or report.get('id')!=parameter_id
            or type(report.get('normalized')) not in (int,float) or not math.isfinite(report['normalized']) or not 0<=report['normalized']<=1):raise ValueError('invalid plugin parameter conversion result')
    return {**report,'plugin_sha256':fingerprint(plugin),'state_changed':False,
            'method':'plugin edit-controller conversion; apply/capture the normalized value separately'}


@bounded('plugin-editor')
def edit(worker,plugin,class_id,presets,*,state=None,parameters=None,interactive=True):
    class_id=resolve_state(plugin,state,class_id)
    report=inspect(worker,plugin)
    if class_id not in {item["class_id"] for item in report["classes"]}:
        raise ValueError("class ID is not in the plugin inventory")
    presets.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".preset-",dir=presets) as directory:
        stage=Path(directory)
        saved=stage/"component-state.bin"
        command=[str(worker),"--editor" if interactive else "--save-state",str(plugin),class_id,str(state) if state else "-",str(saved)]
        if parameters:
            import math
            if not isinstance(parameters,dict) or len(parameters)>128:raise ValueError("too many editor parameters")
            for key,value in parameters.items():
                if (not isinstance(key,str) or not key.isascii() or not key.isdigit() or not 0<=int(key)<=2**32-1
                        or type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1):
                    raise ValueError("invalid normalized editor parameters")
            initial=stage/"initial-parameters.txt"
            initial.write_text("".join(f"{key} {value}\n" for key,value in parameters.items()),encoding="utf-8")
            command.append(str(initial))
        result=run(command,
                   capture_output=True,text=True,timeout=3600 if interactive else 30,max_job_bytes=plugin_memory_bytes())
        if result.returncode:
            raise ValueError(f"Plugin editor failed ({result.returncode}): {result.stderr.strip()}")
        if len(result.stdout.encode('utf-8'))>2_000_000:raise ValueError('plugin state report exceeds result bound')
        reply=json.loads(result.stdout);parameter_values=reply['parameter_values']
        (stage/"initial-parameters.txt").unlink(missing_ok=True)
        if not saved.is_file() or saved.stat().st_size>16*1024*1024:
            raise ValueError("editor returned invalid state")
        manifest={"format":"arranger-plugin-preset","schema":1,"class_id":class_id,
                  "parameter_values":parameter_values,
                  "capture_mode":"native-editor" if interactive else "generic-parameters",
                  'controller_component_synced':reply.get('controller_component_synced') is True,
                  "plugin_sha256":report["plugin_sha256"],"component_sha256":hashlib.sha256(saved.read_bytes()).hexdigest()}
        controller=stage/"component-state.bin.controller"
        manifest["controller_sha256"]=hashlib.sha256(controller.read_bytes()).hexdigest() if controller.exists() else None
        (stage/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        destination=presets/f"preset-{uuid.uuid4()}"
        stage.rename(destination)
        return {"preset":str(destination),"state":str(destination/saved.name),**manifest}


def capture_state(worker,plugin,class_id,presets,*,state=None,parameters=None):
    """Capture actual processor/controller state without requiring a plugin editor."""
    return edit(worker,plugin,class_id,presets,state=state,parameters=parameters,interactive=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("inspect","edit"))
    parser.add_argument("--worker",type=Path,required=True)
    parser.add_argument("--plugin",type=Path,required=True)
    parser.add_argument("--class-id")
    parser.add_argument("--state",type=Path)
    parser.add_argument("--presets",type=Path)
    args=parser.parse_args()
    try:
        if args.operation=="inspect":result=inspect(args.worker,args.plugin)
        else:
            if not args.class_id or not args.presets:parser.error("edit needs --class-id and --presets")
            result=edit(args.worker,args.plugin,args.class_id,args.presets,state=args.state)
        print(json.dumps(result))
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        parser.exit(1,f"{error}\n")


if __name__=="__main__":main()

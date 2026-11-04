"""Bounded VST3 component presets, per pinned SDK vstpresetfile.h format.

Comp/Cont streams are opaque. No XML, program code, asset URLs or paths execute.
Program-only presets are explicitly unsupported; plugin/output rights stay separate.
"""
import json
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import uuid
from assets import digest
from process import run
from resources import plugin_memory_bytes

CAP=16*1024*1024


def read_preset(path):
    if not path.is_file() or not 56<=path.stat().st_size<=34*1024*1024:raise ValueError("preset exceeds file bounds")
    with path.open('rb') as source:data=source.read(34*1024*1024+1)
    if not 56<=len(data)<=34*1024*1024:raise ValueError("preset changed or exceeds file bounds")
    return data


def decode(path):return decode_bytes(read_preset(path))


def decode_bytes(data):
    magic,version,identity,offset=struct.unpack_from('<4sI32sQ',data)
    try:identity=identity.decode('ascii')
    except UnicodeDecodeError as error:raise ValueError("invalid preset component ID") from error
    if magic!=b'VST3' or version!=1 or any(ch not in '0123456789ABCDEF' for ch in identity):raise ValueError("unsupported preset header")
    if not 48<=offset<=len(data)-8:raise ValueError("invalid preset list offset")
    magic,count=struct.unpack_from('<4sI',data,offset)
    if magic!=b'List' or not 1<=count<=128 or offset+8+count*20>len(data):raise ValueError("invalid preset chunk list")
    chunks={};ranges=[]
    for index in range(count):
        kind,start,length=struct.unpack_from('<4sQQ',data,offset+8+20*index)
        if kind in chunks or length>CAP or start<48 or start>offset or length>offset-start:
            raise ValueError("invalid preset chunk bounds or duplicate ID")
        if any(start<end and start+length>begin for begin,end in ranges):raise ValueError("overlapping preset chunks")
        ranges.append((start,start+length));chunks[kind]=data[start:start+length]
    if b'Comp' not in chunks:raise ValueError("program-only preset has no component state")
    return identity,chunks


def sdk_check(worker,path,identity):
    result=run([str(worker),'--preset-info',str(path)],capture_output=True,text=True,timeout=30,max_job_bytes=plugin_memory_bytes())
    if result.returncode or json.loads(result.stdout).get('class_id')!=identity:
        raise ValueError("SDK rejected preset/component identity")


def import_preset(worker,plugin,preset,presets):
    from plugins import inspect
    snapshot=read_preset(preset);identity,chunks=decode_bytes(snapshot)
    inventory=inspect(worker,plugin)
    if identity not in {item['class_id'] for item in inventory['classes']}:raise ValueError("preset component is not in the selected plugin")
    presets.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.preset-',dir=presets) as directory:
        stage=Path(directory);check=stage/'source.vstpreset';check.write_bytes(snapshot)
        sdk_check(worker,check,identity);check.unlink()
        state=stage/'component-state.bin';state.write_bytes(chunks[b'Comp'])
        controller=stage/'component-state.bin.controller'
        if b'Cont' in chunks:controller.write_bytes(chunks[b'Cont'])
        manifest={'format':'arranger-plugin-preset','schema':1,'class_id':identity,
                  'plugin_sha256':inventory['plugin_sha256'],'component_sha256':digest(state),
                  'controller_sha256':digest(controller) if controller.exists() else None,
                  'source_preset_sha256':hashlib.sha256(snapshot).hexdigest(),'source_format':'VST3 preset version1'}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        destination=presets/f'preset-{uuid.uuid4()}';stage.rename(destination)
        return {'preset':str(destination),'state':str(destination/state.name),**manifest}


def export_preset(worker,plugin,state,destination,class_id=None):
    from plugins import resolve_state,inspect
    identity=resolve_state(plugin,state,class_id)
    inventory=inspect(worker,plugin)
    if identity not in {item['class_id'] for item in inventory['classes']}:raise ValueError("choose the component before exporting state")
    if destination.exists():raise ValueError("preset destination already exists; choose a new file")
    streams=[(b'Comp',state.read_bytes())]
    controller=Path(str(state)+'.controller')
    if controller.exists():
        if not controller.is_file() or controller.stat().st_size>CAP:raise ValueError("controller exceeds state bound")
        streams.append((b'Cont',controller.read_bytes()))
    offset=48;entries=[]
    for kind,data in streams:entries.append((kind,offset,len(data)));offset+=len(data)
    header=struct.pack('<4sI32sQ',b'VST3',1,identity.encode('ascii'),offset)
    descriptor,temporary=tempfile.mkstemp(prefix='.preset-export-',dir=destination.parent)
    try:
        with os.fdopen(descriptor,'wb') as output:
            output.write(header)
            for _,data in streams:output.write(data)
            output.write(struct.pack('<4sI',b'List',len(entries)))
            for entry in entries:output.write(struct.pack('<4sQQ',*entry))
        temporary=Path(temporary)
        decode(temporary);sdk_check(worker,temporary,identity)
        temporary.rename(destination)
    finally:Path(temporary).unlink(missing_ok=True)
    return {'file':str(destination),'sha256':digest(destination),'class_id':identity,'format':'VST3 preset version1'}

"""Local portable project folders, without copying worker/plugin binaries.

An imported project is atomically published as a new folder. Plugins/worker require
explicit matching bindings or remain missing; opaque plugin library references and
activation are never inferred, copied or repaired. No archives/network are involved.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
from assets import digest

MAX_ASSET=512*1024**2
MAX_TOTAL=1024**3
MAX_FILES=64


def check_canceled():
    marker=os.environ.get('ARRANGER_CANCEL_FILE')
    if marker and Path(marker).exists():raise InterruptedError('portable project operation canceled')


@dataclass
class Reference:
    selector:str
    container:dict
    key:str
    sha256:str
    kind:str
    pair:str|None=None
    derived:bool=False
    @property
    def path(self):return self.container[self.key]+('.controller' if self.derived else '')
    def replace(self,value):
        if self.derived:
            if value!=self.path:raise ValueError('controller state must stay adjacent to its component state')
        else:self.container[self.key]=value


def references(data):
    if data['schema']==7:
        pins=data['graph_assets']
        yield Reference('worker',data,'worker',pins['worker']['sha256'],'worker')
        for name,spec in data['graph_sources'].items():
            if 'file' in spec:
                selector='sources.'+name;yield Reference(selector,spec,'file',pins[selector]['sha256'],'audio')
        for node in data['graph']['nodes']:
            if 'mix' in node:continue
            for key in ('plugin','state','notes','automation'):
                if key in node:
                    selector='nodes.'+node['id']+'.'+key
                    yield Reference(selector,node,key,pins[selector]['sha256'],'plugin' if key=='plugin' else key)
            controller='nodes.'+node['id']+'.controller'
            if controller in pins:yield Reference(controller,node,'state',pins[controller]['sha256'],'controller','nodes.'+node['id']+'.state',True)
        if data.get('narration'):yield Reference('narration',data['narration'],'path',pins['narration']['sha256'],'audio')
        return
    for index,asset in enumerate(data['assets']):yield Reference('samples.'+str(index),asset,'path',asset['sha256'],'audio')
    processing=data.get('processing',{})
    for kind in ('worker','plugin','instrument','state','notes','automation','controller_state'):
        if kind not in processing:continue
        asset=processing[kind]
        yield Reference('processing.'+kind,asset,'path',asset['sha256'],'plugin' if kind in ('plugin','instrument') else kind,
                        'processing.state' if kind=='controller_state' else None)
    for part,spec in data.get('instruments',{}).items():
        identity=data['instrument_assets'][part];prefix='instruments.'+part
        yield Reference(prefix+'.plugin',spec,'plugin',identity['plugin_sha256'],'plugin')
        if spec.get('state'):yield Reference(prefix+'.state',spec,'state',identity['state_sha256'],'state')
        if identity.get('controller_sha256'):yield Reference(prefix+'.controller',spec,'state',identity['controller_sha256'],'controller',prefix+'.state',True)
    if data.get('narration'):yield Reference('narration',data['narration'],'path',data['narration']['sha256'],'audio')


def update_graph_pins(data):
    if data['schema']==7:
        for reference in references(data):data['graph_assets'][reference.selector]['path']=reference.path


@contextmanager
def staging(parent):
    from scratch import scratch
    # Reuse marked, live-lock-protected normal scratch recovery. Publication moves
    # only data; owner/lock remain outside it. A later operation retires only marked
    # inactive crash leftovers, leaving active/unrecognized directories untouched.
    with scratch(Path(parent).resolve()) as stage:yield stage


def copy_verified(source,destination,expected):
    if source.is_symlink() or not source.is_file():raise ValueError('portable asset is missing or redirected')
    before=source.stat()
    if before.st_size>MAX_ASSET:raise ValueError('portable asset exceeds512MiB')
    value=hashlib.sha256();total=0
    with source.open('rb') as incoming,destination.open('xb') as outgoing:
        while block:=incoming.read(1024*1024):
            check_canceled()
            total+=len(block)
            if total>MAX_ASSET:raise ValueError('portable asset grew beyond512MiB')
            outgoing.write(block);value.update(block)
        outgoing.flush();os.fsync(outgoing.fileno())
    after=source.stat()
    if total!=before.st_size or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or value.hexdigest()!=expected:raise ValueError('portable asset content changed or does not match project identity')
    return total


def manifest_path(package):
    package=Path(package).absolute()
    if not package.is_dir() or package.is_symlink() or package.is_junction():raise ValueError('portable project requires a regular folder')
    return package/'package.json'


def package(project,destination):
    from project import inspect as inspect_project
    data=deepcopy(inspect_project(project)['project']);destination=Path(destination).resolve()
    if destination.exists():raise ValueError('portable destination must be a new folder')
    data['catalog']=None
    if data['sections'] and data['schema']<5:data['schema']=5
    original=list(references(data))
    if len(original)>MAX_FILES:raise ValueError('portable reference count exceeds64')
    total=0;bindings={};files={};paths={}
    with staging(destination.parent) as stage:
        (stage/'assets').mkdir()
        for reference in original:
            if reference.kind in ('plugin','instrument','worker'):
                bindings[reference.selector]={'external':reference.kind,'sha256':reference.sha256}
                reference.replace('@external/'+reference.selector)
                continue
            source=Path(reference.path)
            # Derived controller paths must be captured before rewriting their
            # parent; original contains mutable references, so recover via pairs.
            if reference.pair and reference.derived:source=Path(paths[reference.pair][0]+'.controller')
            if reference.kind=='audio':
                from catalog import AUDIO
                if source.suffix.lower() not in AUDIO|{'.f32','.wave'}:raise ValueError('portable audio requires a recognized sample format')
            suffix=source.suffix.lower()
            if not re.fullmatch(r'\.[a-z0-9]{1,12}',suffix):suffix='.bin'
            relative=paths[reference.pair][1]+'.controller' if reference.pair else 'assets/'+hashlib.sha256(reference.selector.encode()).hexdigest()[:16]+suffix
            size=source.stat().st_size
            if total+size>MAX_TOTAL:raise ValueError('portable assets exceed1GiB total budget')
            copied=copy_verified(source,stage/relative,reference.sha256);total+=copied
            files[relative]={'bytes':copied,'sha256':reference.sha256}
            bindings[reference.selector]={'file':relative,'sha256':reference.sha256,'kind':reference.kind}
            paths[reference.selector]=(str(source),relative)
            reference.replace('@asset/'+reference.selector if not reference.pair else '@asset/'+reference.pair+'.controller')
        update_graph_pins(data)
        descriptor={'format':'sample-arranger-portable','schema':1,'created_utc':datetime.now(timezone.utc).isoformat(),
                    'project':data,'bindings':bindings,'files':files,'total_bytes':total,
                    'limitations':['No plugin/worker binaries, activation or opaque plugin-internal libraries copied.','Brief/history/opaque plugin state may contain private information. This is a local copy, not publication or rights clearance.']}
        payload=json.dumps(descriptor,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')
        if len(payload)>4_000_000:raise ValueError('portable descriptor exceeds4MB')
        (stage/'package.json').write_bytes(payload)
        if destination.exists():raise FileExistsError('portable destination appeared during copy')
        check_canceled();os.rename(stage,destination)
    return {'package':str(destination),'manifest_sha256':hashlib.sha256(payload).hexdigest(),'files':len(files),'bytes':total,
            'external_assets':{key:value for key,value in bindings.items() if 'external' in value},'warnings':descriptor['limitations']}


def read_package(package):
    path=manifest_path(package)
    if path.is_symlink() or path.stat().st_size>4_000_000:raise ValueError('portable descriptor is redirected or exceeds4MB')
    payload=path.read_bytes()
    if len(payload)>4_000_000:raise ValueError('portable descriptor grew beyond4MB')
    try:data=json.loads(payload)
    except RecursionError as error:raise ValueError('portable descriptor nesting exceeds limits') from error
    if (not isinstance(data,dict) or data.get('format')!='sample-arranger-portable' or type(data.get('schema')) is not int or data['schema']!=1
            or not isinstance(data.get('files'),dict) or len(data['files'])>MAX_FILES or not isinstance(data.get('bindings'),dict) or len(data['bindings'])>MAX_FILES):raise ValueError('unsupported portable descriptor')
    total=0
    for name,record in data['files'].items():
        if not isinstance(name,str) or not re.fullmatch(r'assets/[0-9a-f]{16}\.[a-z0-9]{1,12}(?:\.controller)?',name) or not isinstance(record,dict) or set(record)!={'bytes','sha256'}:raise ValueError('invalid portable relative file')
        if type(record['bytes']) is not int or not 0<=record['bytes']<=MAX_ASSET or not isinstance(record['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',record['sha256']):raise ValueError('invalid portable file identity')
        total+=record['bytes']
    if total>MAX_TOTAL or type(data.get('total_bytes')) is not int or data['total_bytes']!=total:raise ValueError('portable total size exceeds budget or descriptor')
    return {'manifest_sha256':hashlib.sha256(payload).hexdigest(),'files':len(data['files']),'bytes':total,
            'external_assets':{key:value for key,value in data['bindings'].items() if isinstance(value,dict) and 'external' in value},'descriptor':data}


def inspect(package):
    report=read_package(package)
    return {key:value for key,value in report.items() if key!='descriptor'}


def match(package,expected_manifest_sha256,available_assets=None):
    from plugins import fingerprint
    report=inspect(package)
    if report['manifest_sha256']!=expected_manifest_sha256:raise ValueError('portable descriptor changed; inspect again')
    available_assets={} if available_assets is None else available_assets
    if (not isinstance(available_assets,dict) or available_assets.keys()-{'plugin','worker'}
            or any(not isinstance(paths,list) or len(paths)>32 or any(not isinstance(path,str) or not path or len(path)>32768 for path in paths) for paths in available_assets.values())):raise ValueError('invalid bounded external asset candidates')
    choices={};checked={}
    for kind,paths in available_assets.items():
        for name in dict.fromkeys(paths):
            check_canceled();path=Path(name).resolve()
            try:
                if not path.exists():continue
                binaries=[path] if path.is_file() else list((path/'Contents/x86_64-win').glob('*.vst3'))
                if not binaries or sum(p.stat().st_size for p in binaries)>MAX_ASSET:continue
                sha=fingerprint(path) if kind=='plugin' else digest(path)
            except (OSError,ValueError):continue
            checked[(kind,sha)]=str(path)
    for selector,required in report['external_assets'].items():
        if (required['external'],required['sha256']) in checked:choices[selector]=checked[(required['external'],required['sha256'])]
    return {'bindings':choices,'unresolved':sorted(set(report['external_assets'])-set(choices)),
            'basis':'exact content identity only; activation, opaque libraries and compatibility remain separate'}


def materialize(package,destination,expected_manifest_sha256,bindings=None):
    from project import read,inspect_data
    from plugins import fingerprint
    report=read_package(package)
    if report['manifest_sha256']!=expected_manifest_sha256:raise ValueError('portable descriptor changed; inspect it again')
    descriptor=report['descriptor'];data=deepcopy(descriptor['project']);destination=Path(destination).resolve();source=Path(package).resolve()
    if destination.exists():raise ValueError('import destination must be a new folder')
    provided={} if bindings is None else bindings
    if not isinstance(provided,dict) or provided.keys()-report['external_assets'].keys():raise ValueError('unknown external asset bindings')
    refs=list(references(data))
    if {r.selector for r in refs}!=set(descriptor['bindings']):raise ValueError('portable reference map differs from project')
    used=set()
    with staging(destination.parent) as stage:
        (stage/'assets').mkdir()
        for ref in refs:
            binding=descriptor['bindings'][ref.selector]
            if not isinstance(binding,dict) or binding.get('sha256')!=ref.sha256:raise ValueError('portable reference identity mismatch')
            if ref.kind in ('plugin','instrument','worker'):
                if set(binding)!={'external','sha256'} or binding['external']!=ref.kind:raise ValueError('invalid external reference')
                path=provided.get(ref.selector)
                if path is not None:
                    if not isinstance(path,str) or not path:raise ValueError('external binding must be a local path')
                    path=Path(path).resolve();actual=fingerprint(path) if ref.kind in ('plugin','instrument') else digest(path)
                    if actual!=ref.sha256:raise ValueError('external asset binding differs from pinned content; explicit adoption is separate')
                else:path=destination/'required-external'/hashlib.sha256(ref.selector.encode()).hexdigest()[:16]
                ref.replace(str(path));continue
            if set(binding)!={'file','sha256','kind'} or binding['kind']!=ref.kind or binding['file'] not in descriptor['files']:raise ValueError('invalid portable file reference')
            relative=binding['file'];record=descriptor['files'][relative]
            if record['sha256']!=ref.sha256:raise ValueError('portable file identity differs from reference')
            if relative not in used:
                assets=source/'assets'
                if assets.is_symlink() or assets.is_junction():raise ValueError('portable assets folder is redirected')
                copied=copy_verified(source/relative,stage/relative,ref.sha256)
                if copied!=record['bytes']:raise ValueError('portable source size differs from descriptor')
                used.add(relative)
            ref.replace(str(destination/relative))
        if used!=set(descriptor['files']):raise ValueError('unreferenced portable files are not imported')
        update_graph_pins(data)
        data['revision']=1
        data['portable_origin']={'manifest_sha256':expected_manifest_sha256,'imported_utc':datetime.now(timezone.utc).isoformat()}
        (stage/'project.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        read(stage/'project.json') # Structural/music checks without executing plugins.
        inspect_data(data) # Also reject malformed processing before publication;
                           # final owned paths are expected to be missing until rename.
        if digest(source/'package.json')!=expected_manifest_sha256:raise ValueError('portable descriptor changed during import')
        if destination.exists():raise FileExistsError('import destination appeared during copy')
        check_canceled();os.rename(stage,destination)
    return {'project_path':str(destination/'project.json'),**inspect_data(data),'copied_files':len(used),
            'warnings':['External plugins/worker require exact bindings or explicit recovery/adoption. Opaque libraries and activation are not portable.']}

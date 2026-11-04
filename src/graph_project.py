"""Pinned offline routing projects. No plugin binaries or opaque assets are copied.

Schema7 deliberately stores the same graph consumed by graph.render, rather than
flattening sidechains or output buses into a less expressive score project.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from assets import digest
from graph import validate_graph,validate_source_specs
from plugins import fingerprint


def references(data):
    yield 'worker', data['worker'], False
    for name, spec in data['graph_sources'].items():
        if 'file' in spec:yield 'sources.'+name, spec['file'], False
    for node in data['graph']['nodes']:
        if 'mix' in node:continue
        for key in ('plugin','state','notes','automation'):
            if key in node:yield 'nodes.'+node['id']+'.'+key, node[key], key=='plugin'
        if node.get('state') and 'nodes.'+node['id']+'.controller' in data.get('graph_assets',{}):
            yield 'nodes.'+node['id']+'.controller', node['state']+'.controller', False
    if data.get('narration'):yield 'narration',data['narration']['path'],False


def identity(path, bundle=False):
    path=Path(path)
    if not path.exists():return None
    return fingerprint(path) if bundle else digest(path)


def validate(data):
    from narration import settings
    if (data.get('format')!='sample-arranger-project' or data.get('schema')!=7
            or type(data.get('revision')) is not int or data['revision']<1
            or data.get('sections')!=[] or data.get('assets')!=[]):
        raise ValueError('invalid routing project envelope')
    for key in ('seconds','tail_seconds','tempo'):
        value=data.get(key)
        if value is None and key=='tempo':continue
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('invalid routing project timing')
    if not 0<data['seconds']<=240 or not 0<=data['tail_seconds']<=1 or data['seconds']+data['tail_seconds']>240:
        raise ValueError('routing duration/tail exceeds output policy')
    if data.get('tempo') is not None and not 20<=data['tempo']<=400:raise ValueError('invalid routing tempo')
    validate_graph(data['graph'],data['graph_sources'])
    validate_source_specs(data['graph_sources'])
    for spec in data['graph_sources'].values():
        if round(spec.get('offset_seconds',0)*44100)>=round(data['seconds']*44100):raise ValueError('source starts outside the arrangement')
        if 'target_bpm' in spec and data['tempo'] is not None and spec['target_bpm']!=data['tempo']:raise ValueError('source tempo differs from project tempo')
    if data.get('score'):
        from music import validate as validate_score
        validate_score(data['score'])
        if data['score']['duration_frames']!=round(data['seconds']*44100) or data['score']['bpm']!=data['tempo']:
            raise ValueError('routing score timing must match project duration/tempo')
    if any('score_part' in node for node in data['graph']['nodes']) and not data.get('score'):
        raise ValueError('routing score part requires an accepted score')
    if data.get('narration'):
        if set(data['narration'])!={'path','settings'}:raise ValueError('invalid routing narration')
        settings(data['narration']['settings'])
    pins=data.get('graph_assets')
    if not isinstance(pins,dict) or len(pins)>52:raise ValueError('invalid routing asset map')
    refs=list(references(data))
    if set(pins)!={selector for selector,_,_ in refs}:raise ValueError('routing asset map does not match graph')
    for selector,path,_ in refs:
        pin=pins[selector]
        if (not isinstance(path,str) or not path or len(path)>32768 or not isinstance(pin,dict)
                or set(pin)!={'path','sha256'} or pin['path']!=path or not isinstance(pin['sha256'],str)
                or len(pin['sha256'])!=64 or any(c not in '0123456789abcdef' for c in pin['sha256'])):
            raise ValueError('invalid routing asset identity')
    if len(json.dumps(data,allow_nan=False).encode('utf-8'))>2_000_000:raise ValueError('routing project exceeds size cap')


def inspect_data(data):
    validate(data)
    issues=[]
    for selector,path,bundle in references(data):
        checksum=identity(path,bundle)
        if checksum!=data['graph_assets'][selector]['sha256']:
            issues.append({'selector':selector,'path':path,'issue':'missing' if checksum is None else 'changed'})
    return {'project':data,'ready':not issues,'issues':issues,
            'warnings':['Plugin-internal libraries, licenses and opaque state references are not portable assets.']}


def save(project,graph,sources,worker,seconds,*,expected_revision=0,tempo=None,tail_seconds=0,brief=None,voice=None,voice_settings=None,score=None,source_assets=None,released_musical_locks=None):
    from project import read,atomic_write
    from narration import settings
    previous=read(project) if project.exists() else None
    if type(expected_revision) is not int or expected_revision!=(previous or {}).get('revision',0):
        raise ValueError('project revision conflict; reopen before saving')
    if previous and previous['schema']!=7:raise ValueError('use a new path for a routing project')
    # Omitting context in a routing-only edit must not erase accepted intentions or
    # narration. Explicit replacement content is allowed; clearing needs a separate
    # deliberate edit contract rather than an ambiguous omitted optional argument.
    if previous:
        if brief is None:brief=deepcopy(previous.get('brief'))
        if score is None:score=deepcopy(previous.get('score'))
        if voice is None and previous.get('narration'):
            voice=previous['narration']['path']
            if voice_settings is None:voice_settings=previous['narration']['settings']
        from music import preserve_note_locks
        preserve_note_locks(previous.get('score'),score,released_musical_locks=released_musical_locks)
    if brief is not None and (not isinstance(brief,dict) or len(json.dumps(brief))>16000):raise ValueError('invalid brief state')
    data={'format':'sample-arranger-project','schema':7,'revision':expected_revision+1,
          'sections':[],'assets':[],'graph':deepcopy(graph),'graph_sources':deepcopy(sources),
          'worker':str(Path(worker).resolve()),'seconds':seconds,'tempo':tempo,'tail_seconds':tail_seconds,'brief':brief,'graph_assets':{}}
    validate_graph(graph,sources)
    validate_source_specs(sources)
    if source_assets is not None:
        from project import validate_asset
        if not isinstance(source_assets,dict) or not source_assets.keys()<={name for name,spec in sources.items() if 'file' in spec}:raise ValueError('expected source content bindings must reference file sources')
        for name,asset in source_assets.items():
            validate_asset(asset);path=Path(sources[name]['file']).resolve()
            if Path(asset['path']).resolve()!=path or path.stat().st_size!=asset['bytes'] or digest(path)!=asset['sha256']:raise ValueError('proposed source content changed; review the plan before saving')
    if score is not None:data['score']=deepcopy(score)
    for spec in data['graph_sources'].values():
        if 'file' in spec:spec['file']=str(Path(spec['file']).resolve())
    for node in data['graph']['nodes']:
        for key in ('plugin','state','notes','automation'):
            if key in node:node[key]=str(Path(node[key]).resolve())
        if node.get('state') and Path(node['state']+'.controller').is_file():
            data['graph_assets']['nodes.'+node['id']+'.controller']={}
    if voice:data['narration']={'path':str(Path(voice).resolve()),'settings':settings(voice_settings)}
    elif voice_settings:raise ValueError('narration settings require supplied audio')
    pins={}
    for selector,path,bundle in references(data):
        checksum=identity(path,bundle)
        if checksum is None:raise ValueError('missing routing asset: '+selector)
        prior=(previous or {}).get('graph_assets',{}).get(selector)
        if prior and prior['path']==path and prior['sha256']!=checksum:
            raise ValueError('pinned processing/source content changed; review explicitly')
        pins[selector]={'path':path,'sha256':checksum}
    # A disappearing controller must never silently downgrade saved recall.
    for selector,pin in (previous or {}).get('graph_assets',{}).items():
        if selector.endswith('.controller') and selector not in pins:
            state=selector.rsplit('.',1)[0]+'.state'
            if state in pins and pins[state]['path']+'.controller'==pin['path']:
                raise ValueError('pinned controller state is missing')
    data['graph_assets']=pins
    for name,asset in (source_assets or {}).items():
        if pins['sources.'+name]['sha256']!=asset['sha256']:raise ValueError('proposed source content changed while saving')
    for key in ('processing_updates','relocations'):
        if previous and key in previous:data[key]=previous[key]
    validate(data)
    if not inspect_data(data)['ready']:raise ValueError('routing assets changed while saving')
    atomic_write(project,data)
    return inspect_data(data)


def review(data):
    validate(data)
    changes=[]
    for selector,path,bundle in references(data):
        checksum=identity(path,bundle)
        if checksum!=data['graph_assets'][selector]['sha256']:
            changes.append({'selector':selector,'path':path,'previous_sha256':data['graph_assets'][selector]['sha256'],'current_sha256':checksum})
    return {'revision':data['revision'],'changes':changes,'compatibility':'content review only; not plugin compatibility certification'}


def adopt(project,updates,expected_revision):
    from project import read,atomic_write
    data=read(project)
    if type(expected_revision) is not int or data['revision']!=expected_revision:raise ValueError('project revision conflict')
    if not isinstance(updates,dict) or not 1<=len(updates)<=16:raise ValueError('choose one to sixteen processing changes')
    observed={item['selector']:item for item in review(data)['changes']}
    history=data.get('processing_updates',[])
    if not isinstance(history,list) or len(history)+len(updates)>128:raise ValueError('update history exceeds bounds')
    for selector,checksum in updates.items():
        change=observed.get(selector)
        if selector.startswith('sources.') or selector=='narration':raise ValueError('source content replacement requires an explicit new project/source selection')
        if not change or checksum is None or checksum!=change['current_sha256']:raise ValueError('processing update no longer matches reviewed content')
        data['graph_assets'][selector]['sha256']=checksum
        history.append({**change,'utc':datetime.now(timezone.utc).isoformat()})
    data.update(revision=data['revision']+1,processing_updates=history)
    validate(data);atomic_write(project,data)
    return inspect_data(data)


def relink(project,replacements,expected_revision):
    from project import read,atomic_write
    data=read(project)
    if type(expected_revision) is not int or data['revision']!=expected_revision:raise ValueError('project revision conflict')
    if not isinstance(replacements,dict) or not 1<=len(replacements)<=8:raise ValueError('choose one to eight source relocations')
    history=data.get('relocations',[])
    if len(history)+len(replacements)>128:raise ValueError('relocation history exceeds bound')
    for name,path in replacements.items():
        selector='sources.'+name
        if name not in data['graph_sources'] or not isinstance(path,str):raise ValueError('unknown routing source')
        pin=data['graph_assets'][selector];path=str(Path(path).resolve())
        if identity(path)!=pin['sha256']:raise ValueError('replacement must match original source content exactly')
        history.append({'from':pin['path'],'to':path,'sha256':pin['sha256'],'utc':datetime.now(timezone.utc).isoformat()})
        pin['path']=path;data['graph_sources'][name]['file']=path
    data.update(revision=data['revision']+1,relocations=history)
    validate(data);atomic_write(project,data)
    return inspect_data(data)

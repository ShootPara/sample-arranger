"""Bounded local editable-state drafts; no audio, plugin binaries or credentials.

Drafts are not accepted projects. Restoring a draft never authorizes missing or
changed assets: normal project/save/render validation still applies.
"""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import tempfile
import uuid
from itertools import islice

MAX_BYTES=2*1024**2
MAX_DRAFTS=16


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode('utf-8')


def validate(state):
    stack=[(state,0)];visited=0
    while stack:
        value,depth=stack.pop();visited+=1
        if depth>32 or visited>200000:raise ValueError('recovery nesting/node budget exceeded')
        if isinstance(value,dict):stack.extend((v,depth+1) for v in value.values())
        elif isinstance(value,list):stack.extend((v,depth+1) for v in value)
    required={'sections','score','source_assets','voice_asset','paths','project_path','revision','brief','initial',
              'parameters','instruments','expected_processing','expected_instruments','released_note_ids','voice_settings','bpm','root','mode','planning_source','class_id'}
    if not isinstance(state,dict) or not required<=state.keys() or state.keys()-required-{'released_musical_keys'} or len(encode(state))>MAX_BYTES:raise ValueError('invalid or oversized recovery state')
    releases=state.get('released_musical_keys',[])
    if not isinstance(releases,list) or any(not isinstance(v,list) or len(v)!=3 for v in releases):raise ValueError('invalid recovered musical unlock intentions')
    from musical_locks import validate_specs
    validate_specs({'bars':240},[dict(zip(('bar','kind','part'),v)) for v in releases])
    if (not isinstance(state['paths'],dict) or state['paths'].keys()-{'catalog','jobs','voice','worker','plugin','state'}
            or any(not isinstance(v,str) or len(v)>32768 for v in state['paths'].values())):raise ValueError('invalid recovery paths')
    if (type(state['revision']) is not int or state['revision']<0 or state['planning_source'] not in (0,1)
            or type(state['planning_source']) is not int or type(state['root']) is not int or not 0<=state['root']<=11
            or state['mode'] not in ('major','minor') or type(state['bpm']) not in (int,float) or not 40<=state['bpm']<=240):raise ValueError('invalid recovery project controls')
    for field,limit in (('brief',12000),('initial',12000),('project_path',32768),('class_id',32)):
        value=state[field]
        if value is None and field!='brief':continue
        if not isinstance(value,str) or len(value)>limit:raise ValueError('invalid recovery text')
    if state['class_id'] is not None and (len(state['class_id'])!=32 or any(c not in '0123456789ABCDEF' for c in state['class_id'])):raise ValueError('invalid recovered component')
    if not isinstance(state['sections'],list) or len(state['sections'])>16:raise ValueError('invalid recovery sections')
    # Validate musical structure without resolving files or loading plugins.
    from render import resolve_sections
    if state['sections']:resolve_sections(state['sections'],None,resolver=lambda name:Path(name))
    if state['score'] is not None:
        from music import validate as validate_score
        validate_score(state['score'])
    from project import validate_parameters,validate_asset
    validate_parameters(state['parameters'],bool(state['paths'].get('plugin')))
    from compose import validate_instruments
    validate_instruments(state['instruments'])
    if not isinstance(state['source_assets'],dict) or len(state['source_assets'])>16:raise ValueError('invalid recovery source bindings')
    for name,asset in state['source_assets'].items():
        if not isinstance(name,str):raise ValueError('invalid recovered sample name')
        validate_asset(asset)
    if state['voice_asset'] is not None:validate_asset(state['voice_asset'])
    from narration import settings
    settings(state['voice_settings'])
    for field in ('expected_processing','expected_instruments'):
        if not isinstance(state[field],dict) or len(encode(state[field]))>64000:raise ValueError('invalid recovery content pins')
    if (not isinstance(state['released_note_ids'],list) or len(state['released_note_ids'])>8192
            or any(not isinstance(v,list) or len(v)!=5 or v[0] not in ('bass','chords','melody') or any(type(n) is not int for n in v[1:]) for v in state['released_note_ids'])):
        raise ValueError('invalid recovery unlock intentions')
    return state


class Drafts:
    def __init__(self,root):
        self.root=Path(root);self.token=str(uuid.uuid4());self.path=self.root/('draft-'+self.token+'.json')

    def write(self,state):
        validate(state)
        payload=encode({'format':'sample-arranger-workspace-draft','schema':1,'updated_utc':datetime.now(timezone.utc).isoformat(),'state':state})
        if len(payload)>MAX_BYTES:raise ValueError('recovery draft exceeds2MiB')
        self.root.mkdir(parents=True,exist_ok=True)
        if self.root.is_symlink() or self.root.is_junction():raise ValueError('recovery root must not be redirected')
        # Do not delete other sessions' drafts to create space. Explicitly report
        # a full recovery store instead of silently evicting someone's work.
        if not self.path.exists() and sum(1 for _ in islice(self.root.glob('draft-*.json'),MAX_DRAFTS))>=MAX_DRAFTS:raise ValueError('recovery store is full (16 drafts); manage retained drafts before enabling another')
        if sum(1 for _ in islice(self.root.glob('.draft-*.tmp'),MAX_DRAFTS))>=MAX_DRAFTS:raise ValueError('interrupted draft staging is full; manage retained recovery files before enabling another')
        descriptor,name=tempfile.mkstemp(prefix='.draft-',suffix='.tmp',dir=self.root)
        try:
            with os.fdopen(descriptor,'wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
            os.replace(name,self.path)
        finally:Path(name).unlink(missing_ok=True)
        return self.path

    def clear_owned(self):
        if not self.root.is_symlink() and not self.root.is_junction():self.path.unlink(missing_ok=True)

    def read(self,path):
        path=Path(path)
        if self.root.is_symlink() or self.root.is_junction() or path.parent.resolve()!=self.root.resolve() or not path.name.startswith('draft-') or path.suffix!='.json' or path.is_symlink():raise ValueError('not an owned-format recovery draft')
        if path.stat().st_size>MAX_BYTES:raise ValueError('recovery file exceeds2MiB')
        with path.open('rb') as stream:payload=stream.read(MAX_BYTES+1)
        if len(payload)>MAX_BYTES:raise ValueError('recovery file grew beyond2MiB')
        try:document=json.loads(payload)
        except RecursionError as error:raise ValueError('recovery nesting exceeds parser limits') from error
        if (not isinstance(document,dict) or set(document)!={'format','schema','updated_utc','state'} or document['format']!='sample-arranger-workspace-draft'
                or type(document['schema']) is not int or document['schema']!=1 or not isinstance(document['updated_utc'],str)):raise ValueError('unsupported recovery draft')
        return validate(document['state'])

    def available(self):
        if not self.root.exists() or self.root.is_symlink() or self.root.is_junction():return []
        result=[]
        for path in self.root.glob('draft-*.json'):
            if len(result)>=MAX_DRAFTS:break
            try:
                if path!=self.path and not path.is_symlink():result.append((path.stat().st_mtime_ns,path))
            except FileNotFoundError:continue # A different workspace may clear its own draft.
        return [path for _,path in sorted(result,reverse=True)]

"""Local durable admission for pinned-project renders. No listener or credentials.

Control records contain hashes/status, not briefs/audio. Completed job manifests
remain inside user-deletable job folders. Interrupted admission never auto-renders.
"""
from contextvars import ContextVar
from contextlib import contextmanager,ExitStack
from datetime import datetime,timezone
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import tempfile
import uuid

CURRENT_JOB=ContextVar('arranger_current_job',default=None)


def location(jobs,request_id):
    if not isinstance(request_id,str) or str(uuid.UUID(request_id))!=request_id:raise ValueError('request_id must be a canonical UUID')
    root=Path(jobs).resolve();root.mkdir(parents=True,exist_ok=True)
    directory=root/'.control'
    if directory.is_symlink() or directory.is_junction():raise ValueError('control directory cannot be redirected')
    directory.mkdir(exist_ok=True)
    for suffix in ('.json','.lock','.project.json'):
        path=directory/(request_id+suffix)
        if path.is_symlink() or path.is_junction():raise ValueError('control file cannot be redirected')
    return root,directory/request_id


def path_for(base,suffix):return base.with_name(base.name+suffix)


def write(base,record):
    record['updated_utc']=datetime.now(timezone.utc).isoformat()
    descriptor,temporary=tempfile.mkstemp(prefix='.admission-',dir=base.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as output:
            json.dump(record,output,allow_nan=False);output.flush();os.fsync(output.fileno())
        Path(temporary).replace(path_for(base,'.json'))
    finally:Path(temporary).unlink(missing_ok=True)


def read(base):
    path=path_for(base,'.json')
    if not path.exists():return None
    if path.stat().st_size>8192:raise ValueError('admission record exceeds bound')
    record=json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(record,dict) or record.get('schema')!=1 or record.get('request_id')!=base.name
            or record.get('job')!='job-'+base.name or record.get('state') not in ('running','completed','failed','canceled','interrupted')):
        raise ValueError('invalid admission record')
    return record


@contextmanager
def locked(base):
    descriptor=os.open(path_for(base,'.lock'),os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(descriptor,'r+b') as handle:
        if handle.seek(0,os.SEEK_END)==0:handle.seek(0);handle.write(b'0');handle.flush()
        handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as error:raise BlockingIOError('request is already running; inspect jobs.status') from error
        try:yield
        finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def completed_result(root,record):
    folder=root/record['job'];manifest=folder/'manifest.json'
    if folder.is_symlink() or folder.is_junction() or not manifest.is_file() or manifest.stat().st_size>2_000_000:
        raise ValueError('completed artifact is unavailable; no automatic regeneration')
    result=json.loads(manifest.read_text(encoding='utf-8'))
    if result.get('admission')!={'request_id':record['request_id'],'request_sha256':record['request_sha256']}:
        raise ValueError('artifact admission identity mismatch')
    audio=folder/'result.mp3'
    if audio.is_symlink() or not audio.is_file() or Path(result.get('audio','')).resolve()!=audio.resolve():raise ValueError('completed audio was deleted/redirected; no automatic regeneration')
    from assets import digest
    if digest(audio)!=result.get('audio_sha256'):raise ValueError('completed audio changed; no automatic regeneration')
    return result


def reconcile(root,base,record):
    if record['state']!='completed':
        try:completed_result(root,record);record['state']='completed';write(base,record)
        except ValueError:
            if record['state']=='running':record['state']='interrupted';write(base,record)
    return record


def status(jobs,request_id):
    root,base=location(jobs,request_id)
    if not path_for(base,'.json').exists():return {'request_id':request_id,'state':'unknown','active':False,'job':None}
    try:
        with locked(base):
            record=read(base)
            if record:reconcile(root,base,record)
            path_for(base,'.project.json').unlink(missing_ok=True)
    except BlockingIOError:
        record=read(base)
        return {'request_id':request_id,'state':record['state'] if record else 'admitting','active':True}
    available=False
    if record and record['state']=='completed':
        try:completed_result(root,record);available=True
        except ValueError:pass
    return {'request_id':request_id,'state':record['state'] if record else 'unknown','active':False,
            'request_sha256':record['request_sha256'] if record else None,
            'artifact_available':available,'job':str(root/record['job']) if available else None}


def submit(jobs,request_id,project,project_sha256,*,voice=None,voice_sha256=None,voice_settings=None,perform=None):
    for value in (project_sha256,voice_sha256) if voice else (project_sha256,):
        if not isinstance(value,str) or len(value)!=64 or any(ch not in '0123456789abcdef' for ch in value):raise ValueError('pinned source hash must be lowercase SHA256')
    if voice_sha256 and not voice:raise ValueError('voice hash requires narration')
    root,base=location(jobs,request_id)
    payload={'project':str(project),'project_sha256':project_sha256,'voice':str(voice) if voice else None,'voice_sha256':voice_sha256}
    if voice_settings is not None:
        from narration import settings
        payload['voice_settings']=settings(voice_settings)
    checksum=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    with locked(base),ExitStack() as resources:
        record=read(base)
        if record:
            if record['request_sha256']!=checksum:raise ValueError('idempotency conflict: request ID has a different payload')
            reconcile(root,base,record);path_for(base,'.project.json').unlink(missing_ok=True)
            if record['state']=='completed':return completed_result(root,record)
            raise ValueError('previous request is '+record['state']+'; inspect before submitting a new job')
        with Path(project).open('rb') as source:snapshot=source.read(2_000_001)
        if len(snapshot)>2_000_000 or hashlib.sha256(snapshot).hexdigest()!=project_sha256:raise ValueError('project differs from pinned hash')
        if voice:
            from assets import digest
            if digest(voice)!=voice_sha256:raise ValueError('narration differs from pinned hash')
        from engine_slots import slot
        resources.enter_context(slot('render'))
        record={'schema':1,'request_id':request_id,'request_sha256':checksum,'job':'job-'+request_id,'state':'running'}
        write(base,record);copy=path_for(base,'.project.json');copy.write_bytes(snapshot)
        token=CURRENT_JOB.set({'root':root,'job':record['job'],'request_id':request_id,'request_sha256':checksum})
        try:
            if perform is None:
                from commands import execute
                perform=lambda args:execute({'contract':1,'operation':'project.render','arguments':args})['result']
            arguments={'project':str(copy),'jobs':str(root)}
            if voice:arguments['voice']=str(voice)
            if voice_settings is not None:arguments['voice_settings']=payload['voice_settings']
            result=perform(arguments)
            if Path(result['audio']).resolve()!=root/record['job']/'result.mp3':raise ValueError('renderer published outside its admitted job')
            completed_result(root,record);record['state']='completed';write(base,record)
            return result
        except Exception:
            marker=os.environ.get('ARRANGER_CANCEL_FILE')
            record['state']='canceled' if marker and Path(marker).exists() else 'failed';write(base,record)
            raise
        finally:CURRENT_JOB.reset(token);copy.unlink(missing_ok=True)

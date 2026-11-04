"""Explicit local job inventory/deletion; never follows source references or links."""
import json
from pathlib import Path
import uuid
from assets import digest
from scratch import bounded_tree,redirected


def inventory(stage):
    files,folders=bounded_tree(stage)
    if len(files)>256:raise ValueError('job artifact file count exceeds256')
    return {'owned_files':[{'file':path.relative_to(stage).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)}
            for path in sorted(files) if path!=stage/'manifest.json'],
            'owned_directories':[path.relative_to(stage).as_posix() for path in folders if path!=stage]}


def job_path(jobs,job_id):
    if not isinstance(job_id,str) or not job_id.startswith('job-') or str(uuid.UUID(job_id[4:]))!=job_id[4:]:raise ValueError('job_id requires job-<canonical UUID>')
    root=Path(jobs).resolve();folder=root/job_id
    if folder.parent.resolve()!=root or not folder.is_dir() or redirected(folder):raise ValueError('job folder is unavailable or redirected')
    return root,folder


def list_jobs(jobs,limit=50):
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('job list limit must be1 to100')
    root=Path(jobs).resolve()
    if not root.is_dir():return {'jobs':[],'scan_limited':False}
    folders=[];scanned=0
    for folder in root.glob('job-*'):
        scanned+=1
        if scanned>10000:break
        try:
            _,folder=job_path(root,folder.name);folders.append(folder)
        except (ValueError,OSError):continue
    folders.sort(key=lambda folder:folder.stat().st_mtime_ns,reverse=True)
    result=[]
    for folder in folders[:limit]:
        path=folder/'manifest.json'
        try:
            if not path.is_file() or redirected(path) or path.stat().st_size>2_000_000:continue
            manifest=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(manifest,dict):continue
            result.append({'job_id':folder.name,'folder':str(folder),'seconds':manifest.get('requested_seconds'),
                'modified_ns':path.stat().st_mtime_ns,'manifest_sha256':digest(path),
                'managed':manifest.get('format')=='sample-arranger-job' and manifest.get('schema')==1 and isinstance(manifest.get('owned_files'),list)})
        except (ValueError,OSError):continue
    return {'jobs':result,'scan_limited':scanned>10000}


def delete_job(jobs,job_id,expected_manifest_sha256,forget_receipt=False):
    from job_control import location,locked,read,path_for
    if type(forget_receipt) is not bool:raise ValueError('forget_receipt must be boolean')
    root,folder=job_path(jobs,job_id);_,base=location(root,job_id[4:])
    with locked(base):
        manifest=folder/'manifest.json'
        if not manifest.is_file() or redirected(manifest) or manifest.stat().st_size>2_000_000 or digest(manifest)!=expected_manifest_sha256:
            raise ValueError('job manifest differs from reviewed content')
        result=json.loads(manifest.read_text(encoding='utf-8'))
        if not isinstance(result,dict) or result.get('format')!='sample-arranger-job' or result.get('schema')!=1 or not isinstance(result.get('owned_files'),list) or not 1<=len(result['owned_files'])<=256:
            raise ValueError('legacy/unrecognized job ownership; remove manually after review')
        record=read(base)
        if record and result.get('admission')!={'request_id':record['request_id'],'request_sha256':record['request_sha256']}:
            raise ValueError('job and admission identities differ')
        expected={}
        for entry in result['owned_files']:
            if (not isinstance(entry,dict) or set(entry)!={'file','bytes','sha256'} or not isinstance(entry['file'],str)
                    or type(entry['bytes']) is not int or not 0<=entry['bytes']<=4*1024**3 or not isinstance(entry['sha256'],str)
                    or len(entry['sha256'])!=64 or any(ch not in '0123456789abcdef' for ch in entry['sha256'])):raise ValueError('invalid artifact ownership')
            name=entry['file'];relative=Path(name)
            if (name in ('','.','..') or relative.is_absolute() or any(part in ('.','..') for part in relative.parts) or ':' in name or '\\' in name
                    or relative.as_posix()!=name or name=='manifest.json' or name in expected):raise ValueError('invalid owned artifact path')
            expected[name]=entry
        files,directories=bounded_tree(folder)
        allowed_directories=result.get('owned_directories',[])
        if (not isinstance(allowed_directories,list) or len(allowed_directories)>256 or
                any(not isinstance(name,str) or name in ('','.','..') or Path(name).is_absolute() or ':' in name or '\\' in name or '..' in Path(name).parts or Path(name).as_posix()!=name for name in allowed_directories)):
            raise ValueError('invalid owned directory paths')
        if {path.relative_to(folder).as_posix() for path in directories if path!=folder}-set(allowed_directories):
            raise ValueError('job contains unrecognized directories; nothing deleted')
        observed={path.relative_to(folder).as_posix():path for path in files if path!=manifest}
        if observed.keys()-expected.keys():raise ValueError('job contains unrecognized files; nothing deleted')
        for name,path in observed.items():
            entry=expected[name]
            if path.stat().st_size!=entry['bytes'] or digest(path)!=entry['sha256']:raise ValueError('job artifact changed; nothing deleted')
        # Validate every path before mutation. Missing owned files permit explicit
        # retry after interrupted deletion, without trusting manifest source paths.
        for path in observed.values():path.unlink()
        manifest.unlink()
        for directory in reversed(directories):directory.rmdir()
        if forget_receipt:
            path_for(base,'.project.json').unlink(missing_ok=True);path_for(base,'.json').unlink(missing_ok=True)
    return {'job_id':job_id,'deleted':True,'receipt_forgotten':forget_receipt,'source_assets_deleted':False}


def forget_receipt(jobs,request_id,request_sha256):
    from job_control import location,locked,read,path_for
    root,base=location(jobs,request_id)
    with locked(base):
        record=read(base)
        if not record or record['request_sha256']!=request_sha256:raise ValueError('receipt differs from reviewed request')
        if (root/record['job']).exists():raise ValueError('delete the retained job folder before forgetting its duplicate guard')
        path_for(base,'.project.json').unlink(missing_ok=True);path_for(base,'.json').unlink()
    return {'request_id':request_id,'forgotten':True,'uuid_reuse':'caller must deliberately submit a new operation; no automatic regeneration'}

"""Incremental local VST3 inventory with binary-pinned failure quarantine.

Discovery never installs software or accepts plugin agreements. Each inspected
bundle runs in the existing bounded child host; cached inventory is not validator
certification. Quarantined unchanged binaries require explicit reviewed retry.
"""
from contextlib import closing
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from assets import digest
from plugins import inspect,fingerprint
from engine_slots import bounded
from scratch import redirected


def connect(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and redirected(path):raise ValueError('plugin registry cannot be redirected')
    db=sqlite3.connect(path)
    db.execute('''CREATE TABLE IF NOT EXISTS plugin_registry(path TEXT PRIMARY KEY COLLATE NOCASE,
        binary_sha256 TEXT NOT NULL,worker_sha256 TEXT NOT NULL,status TEXT NOT NULL,
        checked_utc TEXT NOT NULL,report TEXT,error TEXT)''')
    db.commit();db.row_factory=sqlite3.Row
    return db


def discover(root):
    root=Path(root)
    if root.exists() and redirected(root):raise ValueError('plugin discovery root cannot be redirected')
    root=root.resolve()
    if not root.exists() or redirected(root):raise ValueError('plugin discovery root is unavailable or redirected')
    found=[];pending=[root];visited=0;limited=False
    while pending:
        path=pending.pop();visited+=1
        if visited>10000:limited=True;break
        if redirected(path):continue
        if path.suffix.lower()=='.vst3':
            found.append(path)
            if len(found)>=256:limited=bool(pending);break
        elif path.is_dir():
            # Never enqueue more than the global visit budget.
            for child in path.iterdir():
                if visited+len(pending)>=10000:limited=True;break
                pending.append(child)
    return sorted(found),limited


def canceled():
    marker=os.environ.get('ARRANGER_CANCEL_FILE')
    return bool(marker and Path(marker).exists())


def inspect_one(db,worker,plugin,*,force=False,expected_sha256=None):
    if canceled():raise ValueError('Plugin scan canceled')
    if not Path(worker).is_file():raise ValueError('native inspection worker is unavailable; plugin status unchanged')
    plugin=Path(plugin).resolve();identity=fingerprint(plugin);worker_identity=digest(worker)
    if expected_sha256 is not None and identity!=expected_sha256:raise ValueError('plugin differs from reviewed binary')
    prior=db.execute('SELECT * FROM plugin_registry WHERE path=?',(str(plugin),)).fetchone()
    if prior and prior['binary_sha256']==identity and not force:
        if prior['status']=='quarantined' or prior['worker_sha256']==worker_identity:
            return {**dict(prior),'report':json.loads(prior['report']) if prior['report'] else None,'cached':True}
    error=None;report=None;status='ready'
    try:
        inventory=inspect(worker,plugin)
        if inventory['plugin_sha256']!=identity:raise ValueError('plugin changed during inspection')
        report={'classes':[{key:item[key] for key in ('class_id','name','vendor','version','audio_inputs','audio_outputs')}
                           |{'parameter_count':len(item['parameters'])} for item in inventory['classes']],
                'compatibility':'inventory only; validator/routing/editor acceptance separate'}
        if not report['classes']:raise ValueError('no supported Windows VST3 components')
    except (ValueError,subprocess.SubprocessError) as failure:
        if canceled():raise ValueError('Plugin scan canceled; cancellation is not a compatibility failure') from failure
        status='quarantined';error=str(failure)[:2000]
    result={'path':str(plugin),'binary_sha256':identity,'worker_sha256':worker_identity,'status':status,
            'checked_utc':datetime.now(timezone.utc).isoformat(),'report':report,'error':error}
    db.execute('INSERT OR REPLACE INTO plugin_registry VALUES (?,?,?,?,?,?,?)',
               tuple(result[key] if key!='report' else json.dumps(report) if report else None for key in ('path','binary_sha256','worker_sha256','status','checked_utc','report','error')))
    db.commit()
    return {**result,'cached':False}


@bounded('plugin-inspect')
def scan(registry,worker,root):
    if not Path(worker).is_file():raise ValueError('native inspection worker is unavailable; plugin status unchanged')
    paths,limited=discover(root);counts={'ready':0,'quarantined':0,'cached':0};failures=[]
    with closing(connect(registry)) as db:
        for path in paths:
            if canceled():raise ValueError('Plugin scan canceled')
            try:result=inspect_one(db,worker,path)
            except (ValueError,OSError) as error:
                if canceled():raise
                failures.append({'path':str(path),'error':str(error)[:512]});continue
            counts[result['status']]+=1;counts['cached']+=result['cached']
    return {**counts,'discovered':len(paths),'discovery_limited':limited,'unreadable':failures}


def list_plugins(registry,limit=50,offset=0):
    if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or not 0<=offset<=100000:raise ValueError('invalid plugin inventory page')
    with closing(connect(registry)) as db:
        rows=db.execute('SELECT * FROM plugin_registry ORDER BY path LIMIT ? OFFSET ?',(limit,offset)).fetchall()
    return [{**dict(row),'report':json.loads(row['report']) if row['report'] else None} for row in rows]


@bounded('plugin-inspect')
def retry(registry,worker,plugin,expected_sha256):
    with closing(connect(registry)) as db:
        prior=db.execute('SELECT status FROM plugin_registry WHERE path=?',(str(Path(plugin).resolve()),)).fetchone()
        if not prior or prior['status']!='quarantined':raise ValueError('only a quarantined registered plugin can be explicitly retried')
        return inspect_one(db,worker,plugin,force=True,expected_sha256=expected_sha256)

"""Explicit, bounded content identity and catalog-only lifecycle operations.

These operations never remove, move or rewrite the user's audio. Hash observations
are historical facts, not guarantees that a mounted file cannot subsequently change.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3

MAX_BYTES=512*1024**2


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS content_identity (path TEXT PRIMARY KEY, bytes INTEGER NOT NULL, modified_ns INTEGER NOT NULL, sha256 TEXT NOT NULL, inspected_utc TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS content_sha256 ON content_identity(sha256,path)')
    db.execute('CREATE TABLE IF NOT EXISTS catalog_location_history (old_path TEXT NOT NULL,new_path TEXT NOT NULL,sha256 TEXT NOT NULL,changed_utc TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS musical_annotation (path TEXT PRIMARY KEY,bytes INTEGER NOT NULL,modified_ns INTEGER NOT NULL,sha256 TEXT NOT NULL,role TEXT,tonic INTEGER,mode TEXT,corrected_utc TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS musical_annotation_history (path TEXT NOT NULL,sha256 TEXT NOT NULL,role TEXT,tonic INTEGER,mode TEXT,corrected_utc TEXT NOT NULL)')


def checksum(path,expected=None):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('identity requires a regular non-symlink audio file')
    before=path.stat()
    if before.st_size>MAX_BYTES:raise ValueError('sample exceeds512MiB content-identity budget')
    if expected is not None and (before.st_size,before.st_mtime_ns)!=expected:raise ValueError('sample changed since scan; rescan before hashing')
    value=hashlib.sha256();total=0
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            total+=len(block)
            if total>MAX_BYTES:raise ValueError('sample grew beyond content-identity budget')
            value.update(block)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or total!=before.st_size:raise ValueError('sample changed during hashing')
    return after,value.hexdigest()


def observed(db,row):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_identity'").fetchone():return None
    record=db.execute('SELECT bytes,modified_ns,sha256,inspected_utc FROM content_identity WHERE path=?',(row['path'],)).fetchone()
    if record is None:return None
    return {'sha256':record[2],'inspected_utc':record[3],
            'matches_catalog_stat':(record[0],record[1])==(row['bytes'],row['modified_ns']),
            'source':'streamed SHA256','live_content_verified':False}


def annotation(db,row):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='musical_annotation'").fetchone():return None
    record=db.execute('SELECT bytes,modified_ns,sha256,role,tonic,mode,corrected_utc FROM musical_annotation WHERE path=?',(row['path'],)).fetchone()
    if record is None:return None
    return {'sha256':record[2],'role':record[3],'root':record[4],'mode':record[5],'corrected_utc':record[6],
            'valid':(record[0],record[1])==(row['bytes'],row['modified_ns']),
            'source':'user_correction','identity':'SHA256 verified at correction; current catalog stat only; not freshly rehashed'}


def execute(catalog,operation,**args):
    with closing(sqlite3.connect(catalog)) as db:
        db.row_factory=sqlite3.Row
        with db:
            initialize(db)
            if operation=='duplicates':
                limit=args.get('limit',20);offset=args.get('offset',0)
                if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or offset<0:raise ValueError('invalid duplicate paging')
                groups=db.execute('''SELECT i.sha256,count(*) FROM content_identity i JOIN sample s ON s.path=i.path AND s.bytes=i.bytes AND s.modified_ns=i.modified_ns
                                     GROUP BY i.sha256 HAVING count(*)>1 ORDER BY i.sha256 LIMIT ? OFFSET ?''',(limit,offset)).fetchall()
                return {'groups':[{'sha256':sha,'count':count,'paths':[r[0] for r in db.execute('''SELECT s.path FROM sample s JOIN content_identity i ON i.path=s.path
                    AND i.bytes=s.bytes AND i.modified_ns=s.modified_ns WHERE i.sha256=? ORDER BY s.path LIMIT 16''',(sha,))],
                    'paths_truncated':count>16} for sha,count in groups],
                    'live_content_verified':False,'basis':'hash observations matching catalog stat; sources are not freshly opened'}
            path=str(Path(args['path']).resolve())
            row=db.execute('SELECT * FROM sample WHERE path=?',(path,)).fetchone()
            if row is None:raise ValueError('scan this sample before managing its identity')
            if operation=='hash':
                stat,sha=checksum(Path(path),(row['bytes'],row['modified_ns']))
                stamp=datetime.now(timezone.utc).isoformat()
                db.execute('INSERT OR REPLACE INTO content_identity VALUES (?,?,?,?,?)',(path,stat.st_size,stat.st_mtime_ns,sha,stamp))
                return {'path':path,'sha256':sha,'bytes':stat.st_size,'modified_ns':stat.st_mtime_ns,'inspected_utc':stamp}
            expected=args['expected_sha256']
            if not isinstance(expected,str) or len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected):raise ValueError('invalid expected content hash')
            identity=observed(db,row)
            if not identity or not identity['matches_catalog_stat'] or identity['sha256']!=expected:raise ValueError('catalog content identity changed or is missing; hash/review before continuing')
            if operation=='annotate':
                role=args.get('role');tonic=args.get('root');mode=args.get('mode')
                clearing=args.get('clear',False)
                if 'clear' in args and (clearing is not True or set(args)&{'role','root','mode'}):raise ValueError('clear requires true and cannot be combined with musical corrections')
                if (not clearing and not set(args)&{'role','root','mode'} or 'role' in args and role not in ('drum','bass','chords','melody','fx','unknown')
                        or ('root' in args)!=('mode' in args) or 'root' in args and (type(tonic) is not int or not 0<=tonic<=11 or mode not in ('major','minor'))):raise ValueError('musical correction needs a role and/or complete key')
                stat,sha=checksum(Path(path),(row['bytes'],row['modified_ns']))
                if sha!=expected:raise ValueError('sample content changed; hash and review before correcting musical tags')
                if clearing:
                    stamp=datetime.now(timezone.utc).isoformat()
                    db.execute('DELETE FROM musical_annotation WHERE path=?',(path,))
                    db.execute('INSERT INTO musical_annotation_history VALUES (?,?,?,?,?,?)',(path,sha,None,None,None,stamp))
                    return {'cleared':True,'sha256':sha,'corrected_utc':stamp,'history_retained':True}
                prior=annotation(db,row)
                if prior and prior['valid'] and prior['sha256']==sha:
                    if 'role' not in args:role=prior['role']
                    if 'root' not in args:tonic,mode=prior['root'],prior['mode']
                stamp=datetime.now(timezone.utc).isoformat()
                db.execute('INSERT OR REPLACE INTO musical_annotation VALUES (?,?,?,?,?,?,?,?)',(path,stat.st_size,stat.st_mtime_ns,sha,role,tonic,mode,stamp))
                db.execute('INSERT INTO musical_annotation_history VALUES (?,?,?,?,?,?)',(path,sha,role,tonic,mode,stamp))
                return annotation(db,row)
            if operation=='forget':
                for table in ('sample','content_identity','tempo_measurement','tempo_correction','metadata_observation','musical_annotation'):
                    db.execute('DELETE FROM '+table+' WHERE path=?',(path,))
                return {'forgotten_path':path,'source_removed':False,'correction_history_retained':True}
            if operation!='relocate':raise ValueError('unsupported identity operation')
            replacement=str(Path(args['replacement']).resolve())
            if replacement==path:raise ValueError('replacement must be a different location')
            if db.execute('SELECT 1 FROM sample WHERE path=?',(replacement,)).fetchone():raise ValueError('replacement already cataloged; keep aliases or explicitly forget an entry')
            stat,sha=checksum(Path(replacement))
            if sha!=expected:raise ValueError('replacement audio is not identical content')
            # Evidence is migrated only when its old stat matched the content pin.
            # Invalid historical corrections remain invalid rather than being blessed.
            for table in ('tempo_measurement','tempo_correction','metadata_observation','musical_annotation'):
                db.execute('UPDATE '+table+' SET path=?,bytes=?,modified_ns=? WHERE path=? AND bytes=? AND modified_ns=?',
                           (replacement,stat.st_size,stat.st_mtime_ns,path,row['bytes'],row['modified_ns']))
            db.execute('UPDATE sample SET path=?,name=?,bytes=?,modified_ns=? WHERE path=?',(replacement,Path(replacement).name,stat.st_size,stat.st_mtime_ns,path))
            stamp=datetime.now(timezone.utc).isoformat()
            db.execute('DELETE FROM content_identity WHERE path=?',(path,))
            db.execute('INSERT INTO content_identity VALUES (?,?,?,?,?)',(replacement,stat.st_size,stat.st_mtime_ns,sha,stamp))
            db.execute('INSERT INTO catalog_location_history VALUES (?,?,?,?)',(path,replacement,sha,stamp))
            return {'old_path':path,'path':replacement,'sha256':sha,'source_moved':False,'projects_changed':False,'verified_utc':stamp}

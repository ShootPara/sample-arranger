"""Owned normal-job scratch recovery, distinct from retained published jobs.

Ownership and a live file lock live outside data so atomic publication can rename
data while the ownership lock remains held. Legacy/unmarked folders are untouched.
"""
from contextlib import contextmanager
import json
import msvcrt
import os
from pathlib import Path
import uuid

OWNER={'owner':'sample-arranger-normal-scratch','schema':1}


def redirected(path):
    return path.is_symlink() or path.is_junction() or bool(path.lstat().st_file_attributes & 0x400)


def bounded_tree(directory):
    files=[];directories=[];size=0
    pending=[directory]
    while pending:
        parent=pending.pop()
        if redirected(parent):raise ValueError('scratch tree contains a redirected directory')
        directories.append(parent)
        for entry in parent.iterdir():
            if redirected(entry):raise ValueError('scratch tree contains redirected content')
            if entry.is_dir():pending.append(entry)
            elif entry.is_file():files.append(entry);size+=entry.stat().st_size
            else:raise ValueError('scratch contains unsupported content')
            if len(files)+len(directories)+len(pending)>8192 or size>4*1024**3:
                raise ValueError('scratch recovery exceeds scan bounds')
    return files,directories


def retire(directory,root):
    # Check resolved absolute scope before recursive deletion. Never follow links.
    if directory.parent.resolve()!=root.resolve() or redirected(directory):raise ValueError('scratch target outside owned root')
    if {entry.name for entry in directory.iterdir()}-{'owner.json','lock','data'}:
        raise ValueError('unknown scratch wrapper content')
    data=directory/'data'
    if data.exists():
        files,folders=bounded_tree(data)
        for path in files:path.unlink()
        for path in reversed(folders):path.rmdir()
    (directory/'lock').unlink();(directory/'owner.json').unlink();directory.rmdir()


def cleanup(jobs):
    root=Path(jobs)/'.scratch'
    if not root.exists():return 0
    if redirected(root):raise ValueError('scratch root cannot be redirected')
    removed=0
    for directory in root.glob('work-*'):
        try:
            if str(uuid.UUID(directory.name[5:]))!=directory.name[5:] or not directory.is_dir() or redirected(directory):continue
            marker=directory/'owner.json';lock=directory/'lock'
            if redirected(marker) or redirected(lock) or marker.stat().st_size>1024 or lock.stat().st_size!=1:continue
            if json.loads(marker.read_text(encoding='utf-8'))!=OWNER:continue
            with lock.open('r+b') as handle:
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                try:
                    if (directory/'data').exists():bounded_tree(directory/'data')
                finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            retire(directory,root);removed+=1
        except (OSError,ValueError):continue
    return removed


@contextmanager
def scratch(jobs):
    jobs=Path(jobs).resolve();jobs.mkdir(parents=True,exist_ok=True)
    root=jobs/'.scratch'
    if root.exists() and redirected(root):raise ValueError('scratch root cannot be redirected')
    root.mkdir(exist_ok=True);cleanup(jobs)
    directory=root/('work-'+str(uuid.uuid4()));directory.mkdir()
    (directory/'owner.json').write_text(json.dumps(OWNER),encoding='utf-8')
    (directory/'lock').write_bytes(b'0');data=directory/'data';data.mkdir()
    try:
        with (directory/'lock').open('r+b') as handle:
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            try:yield data
            finally:
                handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
    finally:
        retire(directory,root)
        try:root.rmdir()
        except OSError:pass

"""Per-user local engine backpressure; locks release on process exit.

One offline render and one disposable session may coexist. This is resource
coordination, not authentication or an OS policy/security change.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import msvcrt
import os
from pathlib import Path

_held=ContextVar('arranger_engine_slots',default=frozenset())


@contextmanager
def slot(kind):
    if kind not in ('render','continuous','plugin-inspect','plugin-editor'):raise ValueError('unknown engine slot')
    if kind in _held.get():yield;return
    root=Path(os.environ['LOCALAPPDATA'],'SampleArranger/runtime-locks')
    if root.is_symlink() or root.is_junction():raise ValueError('engine lock folder is redirected')
    root.mkdir(parents=True,exist_ok=True);path=root/(kind+'.lock')
    if path.is_symlink() or path.is_junction():raise ValueError('engine lock is redirected')
    descriptor=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(descriptor,'r+b') as handle:
        if handle.seek(0,os.SEEK_END)==0:handle.seek(0);handle.write(b'0');handle.flush()
        handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as error:raise BlockingIOError(kind+' engine is busy on this PC; wait or stop the active operation') from error
        token=_held.set(_held.get()|{kind})
        try:yield
        finally:
            _held.reset(token);handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def bounded(kind):
    def decorate(function):
        @wraps(function)
        def invoke(*args,**kwargs):
            with slot(kind):return function(*args,**kwargs)
        return invoke
    return decorate

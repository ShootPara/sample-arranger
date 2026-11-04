"""Owned continuous-session spools with lock-based orphan recovery."""
import contextlib
import json
import msvcrt
import tempfile
from pathlib import Path
from itertools import islice
from scratch import redirected


def cleanup(root: Path):
    if root.exists() and redirected(root):raise ValueError('continuous root cannot be redirected')
    root.mkdir(parents=True, exist_ok=True)
    removed = 0
    for directory in islice(root.glob("session-*"),1000):
        if directory.is_symlink() or not directory.is_dir() or directory.is_junction():
            continue
        marker = directory / "owner.json"
        lock = directory / "lock"
        if not marker.is_file() or marker.is_symlink() or not lock.is_file() or lock.is_symlink():
            continue
        try:
            if marker.stat().st_size>1024 or json.loads(marker.read_text(encoding="utf-8")) != {"owner": "sample-arranger-continuous", "schema": 1}:
                continue
            with lock.open("r+b") as handle:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    chunks=list(islice(directory.glob('chunk-*.wav'),17))
                    if len(chunks)>16:continue
                    for chunk in chunks:
                        if chunk.is_file() and not chunk.is_symlink():
                            chunk.unlink()
                            removed += 1
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            # Retire only our exact, now-empty metadata set. Unknown files remain.
            if {entry.name for entry in directory.iterdir()}=={"owner.json","lock"}:
                lock.unlink();marker.unlink();directory.rmdir()
        except (OSError, ValueError):
            continue
    return removed


def status(root: Path):
    """Noncontent owned-spool accounting; active locks remain protected."""
    result={'active_sessions':0,'inactive_sessions':0,'inactive_audio_bytes':0,'scan_limited':False,'unverified_owned_sessions':0}
    if not root.exists():return result
    if redirected(root):raise ValueError('continuous root cannot be redirected')
    for index,directory in enumerate(root.glob('session-*')):
        if index>=1000:result['scan_limited']=True;break
        owned=False
        try:
            if directory.is_symlink() or directory.is_junction() or not directory.is_dir():continue
            marker=directory/'owner.json';lock=directory/'lock'
            if not marker.is_file() or marker.is_symlink() or lock.is_symlink() or marker.stat().st_size>1024 or json.loads(marker.read_text(encoding='utf-8'))!={'owner':'sample-arranger-continuous','schema':1}:continue
            owned=True
            with lock.open('r+b') as handle:
                try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                except OSError:result['active_sessions']+=1;continue
                try:
                    result['inactive_sessions']+=1
                    for index,chunk in enumerate(directory.glob('chunk-*.wav')):
                        if index>=16:result['scan_limited']=True;break
                        if chunk.is_file() and not chunk.is_symlink():result['inactive_audio_bytes']+=chunk.stat().st_size
                finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        except (OSError,ValueError):
            if owned:result['unverified_owned_sessions']+=1
    return result


@contextlib.contextmanager
def session_spool(root: Path):
    cleanup(root)
    directory = Path(tempfile.mkdtemp(prefix="session-", dir=root))
    (directory / "owner.json").write_text(
        json.dumps({"owner": "sample-arranger-continuous", "schema": 1}), encoding="utf-8")
    lock = directory / "lock"
    lock.write_bytes(b"0")
    with lock.open("r+b") as handle:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield directory
        finally:
            for chunk in directory.glob("chunk-*.wav"):
                if chunk.is_file() and not chunk.is_symlink():
                    chunk.unlink()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    lock.unlink()
    (directory / "owner.json").unlink()
    directory.rmdir()

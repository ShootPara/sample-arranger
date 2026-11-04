"""Pin private packaging to the reviewed installed audio-tool bytes before execution."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def verify(lock_path,selected):
    lock_path=Path(lock_path)
    if lock_path.stat().st_size>64000:raise ValueError('audio-tool lock exceeds bound')
    lock=json.loads(lock_path.read_text(encoding='utf-8'))
    names={'ffmpeg.exe','ffprobe.exe','ffplay.exe'}
    if lock.get('schema')!=1 or not isinstance(lock.get('tools'),list) or len(lock['tools'])!=3 or set(selected)!=names:raise ValueError('invalid audio-tool lock/selection')
    expected={}
    for item in lock['tools']:
        if (not isinstance(item,dict) or set(item)!={'name','bytes','sha256','version_line'} or item['name'] not in names or item['name'] in expected
                or type(item['bytes']) is not int or item['bytes']<1 or not isinstance(item['sha256'],str) or len(item['sha256'])!=64
                or any(ch not in '0123456789abcdef' for ch in item['sha256']) or not isinstance(item['version_line'],str) or not 1<=len(item['version_line'])<=512):raise ValueError('invalid pinned audio-tool identity')
        expected[item['name']]=item
    verified=[]
    for name in sorted(names):
        path=Path(selected[name]).resolve(strict=True);item=expected[name]
        before=path.stat();checksum=hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):checksum.update(block)
        after=path.stat()
        if ((before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns)
                or after.st_size!=item['bytes'] or checksum.hexdigest()!=item['sha256']):
            raise ValueError(name+' differs from the pinned build; review a deliberate tool/lock update before packaging')
        # Only execute after matching exact previously observed bytes.
        result=subprocess.run([str(path),'-version'],capture_output=True,text=True,check=True,timeout=10)
        if not result.stdout or result.stdout.splitlines()[0]!=item['version_line']:raise ValueError(name+' version differs from its recorded identity')
        verified.append({'name':name,'sha256':item['sha256'],'version_line':item['version_line']})
    return {'verified_audio_tools':verified,'upstream_archive_attestation':False,'distribution_cleared':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('lock','ffmpeg','ffprobe','ffplay'):parser.add_argument(key,type=Path)
    args=parser.parse_args()
    try:print(json.dumps(verify(args.lock,{key+'.exe':getattr(args,key) for key in ('ffmpeg','ffprobe','ffplay')})))
    except (ValueError,OSError,subprocess.SubprocessError) as error:print(str(error),file=sys.stderr);raise SystemExit(2)


if __name__=='__main__':main()

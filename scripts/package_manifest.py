"""Record private build inputs/files without collecting user settings or audio."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

source,package=map(lambda value:Path(value).resolve(),sys.argv[1:])
def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()
inputs=[]
for folder in ('src','native','scripts','assets'):
    inputs.extend(path for path in (source/folder).rglob('*') if path.is_file() and path.suffix in ('.py','.cpp','.h','.ps1','.spec','.svg','.txt'))
inputs.extend(source.glob('requirements*.lock'));inputs.append(source/'LICENSE')
inputs.extend(source/'docs'/name for name in ('FFMPEG_WINDOWS.lock.json','PACKAGING_DEPENDENCIES.json'))
source_files=[{'path':path.relative_to(source).as_posix(),'sha256':digest(path)} for path in sorted(set(inputs))]
files=[{'path':path.relative_to(package).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)}
       for path in sorted(package.rglob('*')) if path.is_file() and path.name!='build-manifest.json']
commit=subprocess.run(['git','rev-parse','HEAD'],cwd=source,capture_output=True,text=True,check=True,timeout=10).stdout.strip()
dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=source,capture_output=True,text=True,check=True,timeout=10).stdout.strip())
result={'format':'sample-arranger-private-build','schema':1,'built_utc':datetime.now(timezone.utc).isoformat(),
        'git_commit':commit,'git_dirty':dirty,'source_files':source_files,'files':files,
        'runtime':{name:importlib.metadata.version(name) for name in ('PySide6-Essentials','shiboken6','numpy','PyInstaller','pyinstaller-hooks-contrib')},
        'distribution_cleared':False,'clean_machine_acceptance':False,
        'privacy':'No user plugins/catalog/jobs/settings/model weights or credentials collected.'}
(package/'build-manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'files':len(files),'bytes':sum(item['bytes'] for item in files),'git_dirty':dirty}))

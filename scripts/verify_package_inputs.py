"""Reject dependency discovery outside pinned/runtime/system build inputs."""
import ast
import json
import os
from pathlib import Path
import shutil
import sys


def verify(source,build):
    product=Path(os.environ['LOCALAPPDATA'])/'SampleArranger'
    roots={'package_runtime':Path(sys.prefix).resolve(),'python_runtime':Path(sys.base_prefix).resolve(),
           'windows_system':(Path(os.environ['SystemRoot'])/'System32').resolve(),
           'app_native':(product/'tools/arranger-native').resolve(),'build':build.resolve(),'app_source':source.resolve()}
    selected={Path(os.environ.get('ARRANGER_'+name.upper()) or shutil.which(name)).resolve() for name in ('ffmpeg','ffprobe','ffplay')}
    counts={name:0 for name in roots};counts['selected_ffmpeg']=0
    def inspect(value):
        if isinstance(value,(list,tuple)):
            if len(value)==3 and isinstance(value[0],str) and isinstance(value[1],str) and value[2] in ('BINARY','EXTENSION'):
                path=Path(value[1]).resolve()
                if path in selected:counts['selected_ffmpeg']+=1;return
                for label,root in roots.items():
                    if path.is_relative_to(root):counts[label]+=1;return
                raise ValueError('Unexpected binary dependency outside approved inputs: '+path.name)
            for item in value:inspect(item)
    files=list((build/'work/arranger').glob('Analysis-*.toc'))
    if len(files)!=2:raise ValueError('expected console and GUI dependency analyses')
    for path in files:inspect(ast.literal_eval(path.read_text(encoding='utf-8')))
    result={'source_policy':'pinned runtime/native, selected FFmpeg, Windows system and app build only','binary_origins':counts}
    (build/'input-policy.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':print(json.dumps(verify(*map(Path,sys.argv[1:]))))

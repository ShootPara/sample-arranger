"""Audio-tool input policy: filesystem/pipe media, no implicit URL transport.

Mounted filesystem providers and third-party plugins have independent behavior;
this controls FFmpeg-family command inputs, not OS or plugin security settings.
"""
from pathlib import Path


def file_inputs(command):
    if not command:return command
    name=Path(command[0]).name.casefold().removesuffix('.exe')
    if name not in ('ffmpeg','ffprobe','ffplay'):return command
    arguments=list(map(str,command[1:]))
    if '-protocol_whitelist' in arguments:raise ValueError('audio protocol input policy is app-owned')
    if name in ('ffprobe','ffplay'):return [command[0],'-protocol_whitelist','file,pipe',*arguments]
    result=[command[0]]
    for argument in arguments:
        if argument=='-i':result.extend(('-protocol_whitelist','file,pipe'))
        result.append(argument)
    return result

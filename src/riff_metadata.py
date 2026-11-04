"""Read bounded RIFF headers without decoding PCM or guessing MAGIX formats.

ACID field layout cross-checked against libsndfile src/wav.c (2026-11-04).
No libsndfile code/dependency is included. Duration consistency is evidence, not
proof of an accurate beat grid. Unknown chunks are inventoried, never executed.
"""
import math
from pathlib import Path
import struct


def observe(path):
    path=Path(path);size=path.stat().st_size
    result={'reader':'riff-metadata-1','chunks':[],'warnings':[],'acid':[],'duration_seconds':None}
    with path.open('rb') as source:
        header=source.read(12)
        if len(header)!=12 or header[:4]!=b'RIFF' or header[8:]!=b'WAVE':
            result.update(state='unsupported',warnings=['Only little-endian RIFF/WAVE is parsed; RF64/RIFX/other formats remain separate adapters.']);return result
        end=struct.unpack_from('<I',header,4)[0]+8
        if end>size or end<12:raise ValueError('invalid RIFF declared bounds')
        if end!=size:result['warnings'].append('Trailing bytes outside the declared RIFF are not interpreted.')
        position=12;format=None;data_bytes=0
        while position<end:
            if len(result['chunks'])>=4096:raise ValueError('RIFF chunk count exceeds4096')
            if position+8>end:raise ValueError('truncated RIFF chunk header')
            source.seek(position);kind,length=struct.unpack('<4sI',source.read(8))
            start=position+8
            if length>end-start:raise ValueError('RIFF chunk extends past container')
            result['chunks'].append({'id':kind.decode('ascii',errors='replace'),'bytes':length,'offset':position})
            if kind==b'fmt ' and length>=16:
                if format is not None:result['warnings'].append('Repeated format chunk; duration is not trusted.');format=False
                else:format=struct.unpack('<HHIIHH',source.read(16))
            elif kind==b'data':data_bytes+=length
            elif kind==b'acid':
                if length!=24:result['warnings'].append('Nonstandard ACID size; chunk is not interpreted.')
                else:
                    flags,root,reserved,unused,beats,denominator,numerator,bpm=struct.unpack('<IHHfIHHf',source.read(24))
                    result['acid'].append({'flags':flags,'one_shot':bool(flags&1),'root_midi':root if flags&2 and root<=127 else None,
                        'beats':beats,'meter_fields':[numerator,denominator],
                        'declared_bpm':bpm if math.isfinite(bpm) and 20<=bpm<=400 else None,
                        'provenance':'embedded RIFF acid chunk; field layout reference, not a MAGIX schema'})
            position=start+length+(length&1)
            if position>end:raise ValueError('missing RIFF odd-chunk padding')
        if format and format[0] in (1,3) and format[1]>0 and format[2]>0 and format[4]>0:
            result['duration_seconds']=data_bytes/(format[2]*format[4])
    for item in result['acid']:
        seconds=result['duration_seconds'];derived=60*item['beats']/seconds if seconds and 0<item['beats']<=100000 else None
        bpm=item['declared_bpm'];consistent=bool(bpm and derived and abs(bpm-derived)/bpm<=0.02)
        item.update(duration_derived_bpm=derived,duration_consistent=consistent,
                    recommendation='review_one_shot' if item['one_shot'] else 'duration_consistent_candidate' if consistent else 'review_conflict_or_unknown')
    if len(result['acid'])>1:result['warnings'].append('Multiple ACID observations require explicit review; none is preferred.')
    result['state']='observed'
    return result

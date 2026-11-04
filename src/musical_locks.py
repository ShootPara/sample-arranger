"""Explicit immutable bar/part projections, independent of note array indices.

Section = exact events, form membership and harmony; harmony = accepted harmonic
intention; rhythm = event timing/counts, allowing pitch/velocity changes. These are
score locks, not audio/sample arrangement locks. Hashes are integrity checks, not
authentication or a substitute for persisted previous-state comparison.
"""
from copy import deepcopy
import hashlib
import json


def key(spec):return (spec['bar'],spec['kind'],spec['part'])


def validate_specs(score,specs,*,pinned=False):
    if not isinstance(specs,list) or len(specs)>512:raise ValueError('musical locks require up to512 explicit bar/part selections')
    keys=set()
    for spec in specs:
        if (not isinstance(spec,dict) or set(spec)!=({'bar','kind','part','sha256'} if pinned else {'bar','kind','part'})
                or type(spec['bar']) is not int or not 0<=spec['bar']<score['bars']
                or spec['kind'] not in ('section','harmony','rhythm') or spec['part'] not in ('all','bass','chords','melody')
                or spec['kind']!='rhythm' and spec['part']!='all'
                or pinned and (not isinstance(spec['sha256'],str) or len(spec['sha256'])!=64 or any(c not in '0123456789abcdef' for c in spec['sha256']))):
            raise ValueError('invalid musical lock selection')
        if key(spec) in keys:raise ValueError('duplicate musical lock selection')
        keys.add(key(spec))


def projection(score,spec):
    bar=spec['bar'];kind=spec['kind'];start=bar*3840;end=min(start+3840,score['duration_ticks'])
    context={'bar':bar,'tpq':score['tpq'],'meter':score['meter'],'bpm':score['bpm'],'end':end}
    if kind in ('section','harmony'):
        if not score.get('harmony'):raise ValueError('harmonic/section locks require an accepted harmonic timeline')
        context.update(root=score['root'],mode=score['mode'],harmony=score['harmony'][bar])
    if kind=='section':
        offset=0;membership=None
        for section in score.get('form',[]):
            if offset<=bar<offset+section['bars']:membership={k:v for k,v in section.items() if k!='bars'};break
            offset+=section['bars']
        context['section']=membership
    if kind in ('section','rhythm'):
        notes=[n for n in score['notes'] if n['tick']<end and n['tick']+n['length']>start and (spec['part']=='all' or n['part']==spec['part'])]
        fields=('part','tick','length') if kind=='rhythm' else ('part','tick','length','pitch','velocity')
        context['events']=sorted(tuple(n[f] for f in fields) for n in notes)
    return context


def fingerprint(score,spec):return hashlib.sha256(json.dumps(projection(score,spec),ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode('utf-8')).hexdigest()


def validate(score):
    locks=score.get('musical_locks',[]);validate_specs(score,locks,pinned=True)
    for spec in locks:
        if fingerprint(score,spec)!=spec['sha256']:raise ValueError('protected '+spec['kind']+' changed in bar '+str(spec['bar']+1)+'; unlock explicitly first')


def set_locks(score,selections):
    from music import validate as validate_score
    validate_score(score);validate_specs(score,selections)
    result=deepcopy(score)
    result['musical_locks']=[{**spec,'sha256':fingerprint(score,spec)} for spec in sorted(selections,key=key)]
    revision=result.get('edit_revision',0)
    if type(revision) is not int or not 0<=revision<1_000_000_000:raise ValueError('invalid score edit revision')
    result['edit_revision']=revision+1;validate_score(result);return result


def preserve(previous,replacement,releases=None):
    releases=[] if releases is None else releases
    if previous is None:
        if releases:raise ValueError('cannot release nonexistent saved musical locks')
        return
    validate_specs(previous,releases)
    previous_locks={key(spec):spec for spec in previous.get('musical_locks',[])}
    if not {key(spec) for spec in releases}<=previous_locks.keys():raise ValueError('releases must identify saved musical locks')
    released={key(spec) for spec in releases}
    required={k:spec for k,spec in previous_locks.items() if k not in released}
    if required:
        actual={key(spec):spec for spec in (replacement or {}).get('musical_locks',[])}
        if any(actual.get(k)!=spec for k,spec in required.items()):raise ValueError('saved musical locks cannot be dropped/replaced; unlock saved selections explicitly first')

"""Live local-model proposals through the app broker identity; musical rules stay local."""
from copy import deepcopy
import os
import re
from pathlib import Path
from brief import interpret
from broker_port import BrokerPort
from music import compile_intent


class CancelMarker:
    def is_set(self):
        path=os.environ.get('ARRANGER_CANCEL_FILE');return bool(path and Path(path).exists())


def check_connection():
    value=BrokerPort().request('GET','/api/v1/ai/status',timeout=5)
    return {'reachable':True,'broker_state':value.get('broker_state'),'accepting':value.get('queue',{}).get('accepting'),
            'privacy':'Only compact brief/features cross the verified broker connection. Audio, paths, plugins and catalog stay local.'}


def context(initial,intent,refined):
    parsed=interpret(initial,refined)
    if parsed['state']!='ready':return parsed,None
    accepted=compile_intent(intent)
    if accepted['duration_frames']!=round(parsed['seconds']*44100):raise ValueError('AI intention duration contradicts the effective brief')
    if re.search(r'\bbpm\b',parsed['effective'],re.I) and accepted['bpm']!=parsed['recommended_bpm']:raise ValueError('AI intention tempo contradicts the effective brief')
    if 'root' in parsed['musical'] and (accepted['root'],accepted['mode'])!=(parsed['musical']['root'],parsed['musical']['mode']):raise ValueError('AI intention key contradicts the effective brief')
    if 'bass' in parsed['excluded_roles'] and any(note['part']=='bass' for note in accepted['notes']):raise ValueError('AI intention includes an excluded bass part')
    return parsed,accepted


def score_plan(initial,intent,refined=None,*,port=None):
    parsed,accepted=context(initial,intent,refined)
    if accepted is None:return parsed
    from midi_planning import propose_with_port
    hard={'bpm':accepted['bpm'],'root':accepted['root'],'mode':accepted['mode'],**{key:deepcopy(value) for key,value in intent.items() if key in ('bpm','root','mode','parts','density','seed','progression','previous_chord','melody_pattern')}}
    hard['bars']=min(4,accepted['bars']);hard['resolve']=False
    state={'revision':1,'brief':parsed['effective'],'intent':hard}
    if 'melody_pattern' not in hard:state['grid_steps']=8
    result=propose_with_port(state,port or BrokerPort(),cancel_event=CancelMarker())
    generated=compile_intent({**intent,'progression':result['intent']['progression'],'density':result['intent']['density'],'melody_pattern':result['intent']['melody_pattern']})
    generated['ai_provenance']={'planner':'local-model through dedicated broker identity','phrase_state_sha256':result['state_sha256'],
                                'inference_receipts':result['inference_receipts'],'realization':'deterministic exact-tick compiler; one-bar pattern and progression realized over accepted form'}
    return {**parsed,'score':generated,'ai':generated['ai_provenance']}


def sample_plan(catalog,initial,intent,refined=None,*,port=None):
    parsed,accepted=context(initial,intent,refined)
    if accepted is None:return parsed
    from retrieval import rank
    from catalog_identity import checksum
    from planning_context import resolve_prepared
    from inference_session import propose_with_port
    term=parsed['role'] if parsed['role'] in ('piano','guitar','pad') else ''
    role='chords' if term else parsed['role'] or None
    report=rank(catalog,term=term,role=role,bpm=accepted['bpm'],root=accepted['root'],mode=accepted['mode'],limit=8,excluded_roles=parsed['excluded_roles'])
    candidates=[];total=0;identities=set();details={row['sample']:row for row in report['candidates']}
    for candidate in report['planning_candidates']:
        item=details[candidate['sample']]
        if total+item['bytes']>64*1024**2:continue
        if CancelMarker().is_set():raise InterruptedError('AI retrieval canceled')
        _,sha=checksum(item['path'],(item['bytes'],item['modified_ns']));total+=item['bytes']
        if sha in identities:continue
        identities.add(sha);candidates.append({**candidate,'id':'c_'+sha[:24],'content_sha256':sha})
    if not candidates:raise ValueError('No compatible samples fit the bounded AI shortlist. Review key/role metadata or choose another brief.')
    state={'revision':1,'seconds':parsed['seconds'],'brief':parsed['effective'],'bpm':accepted['bpm'],'root':accepted['root'],'mode':accepted['mode']}
    result=propose_with_port(state,candidates,port or BrokerPort(),cancel_event=CancelMarker())
    by_name={item['sample']:item for item in candidates}
    proposal={'revision':1,'sections':[{'asset_id':by_name[clip['sample']]['id'],'seconds':clip['seconds'],'beat_scale':clip.get('beat_scale',1)} for clip in result['sections']]}
    resolved=resolve_prepared(catalog,state,candidates,{'structured':proposal})
    return {**parsed,**resolved,'ai':{'planner':'local-model through dedicated broker identity','inference_receipts':result['inference_receipts'],
                                   'catalog_rows_considered':report['catalog_rows_considered'],'shortlist':len(candidates),'audio_bytes_hashed':total}}

"""Conservative, reviewable catalog layers with fresh content bindings.

Tonic/mode labels do not establish chord progressions. Default planning combines
percussion with at most one pitched loop; extra pitched layers require an explicit
unverified-harmony choice. This proposes a graph, never publishes audio or calls AI.
"""
import math
from pathlib import Path
from retrieval import rank
from catalog_identity import checksum


def propose(catalog,seconds,*,bpm=120,root=None,mode=None,roles=None,excluded_roles=None,allow_unverified_harmony=False,role_terms=None):
    roles=['drum','chords'] if roles is None else roles
    if (type(seconds) not in (int,float) or not math.isfinite(seconds) or not .1<=seconds<=240
            or type(bpm) not in (int,float) or not math.isfinite(bpm) or not 40<=bpm<=240
            or not isinstance(roles,list) or not 1<=len(roles)<=4 or any(not isinstance(role,str) for role in roles) or len(set(roles))!=len(roles)
            or any(role not in ('drum','bass','chords','melody','fx') for role in roles)
            or type(allow_unverified_harmony) is not bool):raise ValueError('invalid bounded ensemble request')
    role_terms={} if role_terms is None else role_terms
    if not isinstance(role_terms,dict) or role_terms.keys()-set(roles) or any(not isinstance(value,str) or len(value.encode('utf-8'))>128 for value in role_terms.values()):raise ValueError('invalid per-role search terms')
    if sum(role in ('bass','chords','melody') for role in roles)>1 and not allow_unverified_harmony:
        raise ValueError('multiple pitched loops need explicit unverified-harmony review; key labels do not prove matching progressions')
    if any(role!='drum' for role in roles) and (root is None or mode is None):raise ValueError('pitched/texture selection requires an explicit tonic and mode')
    sources={};assets={};routes=[];decisions=[];missing=[];used=set()
    bar_seconds=240/bpm
    for role in roles:
        report=rank(catalog,term=role_terms.get(role,''),bpm=bpm,role=role,root=root,mode=mode,excluded_roles=excluded_roles,limit=24)
        selected=None
        for candidate in report['candidates']:
            if candidate['bpm'] is None or not .5<=bpm/candidate['bpm']<=2:continue
            path=Path(candidate['path']);stat,sha=checksum(path,(candidate['bytes'],candidate['modified_ns']))
            if sha in used:continue
            selected=candidate;used.add(sha);break
        if selected is None:missing.append(role);continue
        name=role;offset=bar_seconds if role!='drum' and seconds>=bar_seconds*3 else 0
        if role=='fx':offset=math.floor(seconds*.75/bar_seconds)*bar_seconds
        if offset>=seconds:offset=0
        sources[name]={'file':str(path),'loop':role!='fx','offset_seconds':offset,
                       'source_bpm':selected['bpm'],'target_bpm':bpm,'beat_scale':1}
        assets[name]={'path':str(path),'bytes':stat.st_size,'sha256':sha}
        gain={'drum':.35,'bass':.30,'chords':.28,'melody':.22,'fx':.15}[role]
        routes.append({'node':name,'bus':0,'gain':gain})
        decisions.append({'role':role,'sample':selected['sample'],'start_bar':round(offset/bar_seconds),
                          'bpm':selected['bpm'],'tempo_source':selected['bpm_source'],'beat_scale':1,
                          'musical_provenance':selected['property_provenance'],'content_sha256':sha})
    if not sources:raise ValueError('no distinct available samples meet the requested role/key/tempo constraints; correct tags or revise the request')
    graph={'nodes':[{'id':'ensemble','mix':routes}],'outputs':[{'node':'ensemble','bus':0,'gain':1}]}
    warnings=['Proposed layers need audition: filename/user key labels are not chord-progressions or downbeat analysis.',
              'Only normal-time interpretation is proposed. Half/double-time remains an explicit source edit.',
              'Loop joins and sample loudness are not normalized or musically certified.']
    if missing:warnings.append('No acceptable source for: '+', '.join(missing)+'. These roles were not silently substituted.')
    return {'planner':'conservative-catalog-ensemble-1','graph':graph,'sources':sources,'source_assets':assets,
            'seconds':seconds,'tempo':bpm,'decisions':decisions,'missing_roles':missing,'warnings':warnings,
            'allow_unverified_harmony':allow_unverified_harmony,'root':root,'mode':mode}

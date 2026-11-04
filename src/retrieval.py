"""Whole-catalog, bounded musical retrieval. Filename features remain labelled hints.

No inferred musical key or genre is presented as measured audio knowledge. A key
lock rejects incompatible/unknown pitched material unless explicitly relaxed.
"""
from contextlib import closing
import heapq
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from catalog import BPM_HINT,describe_sample

ROLES={'drum':r'\b(drums?|percussion|perc|kick|snare|hihat|hi hat|clap|cymbal)\b',
       'bass':r'\b(bass|subbass)\b','chords':r'\b(chords?|piano|keys|guitar|rhodes|organ|pad|pads)\b',
       'melody':r'\b(melody|lead|arp|arpeggio|pluck|flute|violin)\b','fx':r'\b(fx|sfx|impact|riser|sweep|noise)\b'}
KEY=re.compile(r'(?<![A-Za-z0-9])([A-Ga-g])([#b]?)[ _-]*(major|minor|maj|min)(?![A-Za-z])',re.I)


def features(name):
    text=Path(name).stem.replace('_',' ').replace('-',' ')
    roles=[role for role,pattern in ROLES.items() if re.search(pattern,text,re.I)]
    matches=KEY.findall(text);keys=set()
    for letter,accidental,mode in matches:
        keys.add((({'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}[letter.upper()]+(1 if accidental=='#' else -1 if accidental.lower()=='b' else 0))%12,
                  'minor' if mode.lower().startswith('min') else 'major'))
    key=next(iter(keys)) if len(keys)==1 else None
    return {'role':roles[0] if len(roles)==1 else 'unknown','role_candidates':roles,
            'key':{'root':key[0],'mode':key[1]} if key else None,
            'feature_provenance':'filename tokens only; not audio analysis','confidence':'uncalibrated hint',
            'property_provenance':{'role':'filename','key':'filename'}}


def rank(catalog,*,term='',bpm=None,role=None,root=None,mode=None,limit=24,excluded_roles=None,allow_unknown_key=False):
    if (not isinstance(term,str) or len(term.encode('utf-8'))>512 or type(limit) is not int or not 1<=limit<=100
            or role is not None and role not in ROLES or type(allow_unknown_key) is not bool):raise ValueError('invalid bounded retrieval request')
    if bpm is not None and (type(bpm) not in (int,float) or not math.isfinite(bpm) or not 20<=bpm<=400):raise ValueError('invalid retrieval tempo')
    if (root is None)!=(mode is None) or root is not None and (type(root) is not int or not 0<=root<=11 or mode not in ('major','minor')):
        raise ValueError('key lock requires root0..11 and major/minor mode')
    excluded_roles=excluded_roles or []
    if not isinstance(excluded_roles,list) or any(value not in set(ROLES)|{'piano','guitar','pad'} for value in excluded_roles):raise ValueError('invalid excluded roles')
    visited=0
    with closing(sqlite3.connect(Path(catalog).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        annotated=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='musical_annotation'").fetchone())
        annotation_fields='a.role AS user_role,a.tonic AS user_root,a.mode AS user_mode,a.bytes AS annotation_bytes,a.modified_ns AS annotation_modified' if annotated else 'NULL AS user_role,NULL AS user_root,NULL AS user_mode,NULL AS annotation_bytes,NULL AS annotation_modified'
        annotation_join=' LEFT JOIN musical_annotation a ON a.path=s.path ' if annotated else ''
        # The full stored catalog participates before a compact result set is chosen.
        # This avoids the former alphabetical-first256 bias. No audio is opened.
        rows=db.execute('''SELECT s.*,c.bpm AS corrected_bpm,c.bytes AS corrected_bytes,c.modified_ns AS corrected_modified,
                                  m.bpm AS measured_bpm,m.confidence AS measured_confidence,m.bytes AS measured_bytes,m.modified_ns AS measured_modified,
                                  o.payload AS embedded,o.bytes AS embedded_bytes,o.modified_ns AS embedded_modified,'''+annotation_fields+'''
                           FROM sample s JOIN (SELECT name FROM sample GROUP BY name HAVING count(*)=1) u ON s.name=u.name
                           LEFT JOIN tempo_correction c ON c.path=s.path LEFT JOIN tempo_measurement m ON m.path=s.path
                           LEFT JOIN metadata_observation o ON o.path=s.path
                           '''+annotation_join+''' WHERE substr(s.name,1,2)!='._' ''')
        def candidates():
            nonlocal visited
            for row in rows:
                visited+=1
                if visited>100000:raise ValueError('catalog exceeds100000-row retrieval budget; narrow the indexed library')
                name=row['name'];info=features(name);tokens=name.lower().replace('_',' ')
                if (row['annotation_bytes'],row['annotation_modified'])==(row['bytes'],row['modified_ns']):
                    if row['user_role'] is not None:
                        info['role']=row['user_role'];info['role_candidates']=[] if row['user_role']=='unknown' else [row['user_role']];info['property_provenance']['role']='user_correction'
                    if row['user_root'] is not None:
                        info['key']={'root':row['user_root'],'mode':row['user_mode']};info['property_provenance']['key']='user_correction'
                    if 'user_correction' in info['property_provenance'].values():info['feature_provenance']='user-corrected properties (content verified when corrected); remaining properties are filename hints';info['confidence']='user assertion; filename hints remain uncalibrated'
                if term.strip().lower() not in tokens:continue
                if any(value in excluded_roles for value in info['role_candidates']):continue
                if any(re.search(r'\b'+re.escape(value)+r's?\b',tokens) for value in excluded_roles):continue
                if role and role not in info['role_candidates']:continue
                if root is not None and info['role']!='drum':
                    if info['key'] is None and not allow_unknown_key:continue
                    if info['key'] is not None and info['key']!={'root':root,'mode':mode}:continue
                hints={float(value) for value in BPM_HINT.findall(Path(name).stem)}
                tempo=None;source=None;metadata_warning=None;embedded_bpm=None
                if row['embedded'] and (row['embedded_bytes'],row['embedded_modified'])==(row['bytes'],row['modified_ns']):
                    if len(row['embedded'])<=65536:
                        acid=json.loads(row['embedded']).get('acid',[])
                        if len(acid)==1 and acid[0].get('duration_consistent') and not acid[0].get('one_shot'):
                            embedded_bpm=acid[0].get('declared_bpm')
                        elif acid:metadata_warning='Embedded tempo requires review; original observation retained.'
                    else:metadata_warning='Embedded metadata exceeds compact retrieval budget; inspect separately.'
                if row['corrected_bpm'] and (row['corrected_bytes'],row['corrected_modified'])==(row['bytes'],row['modified_ns']):tempo=row['corrected_bpm'];source='user correction (stat-pinned)'
                elif embedded_bpm and (not hints or all(abs(hint-embedded_bpm)/embedded_bpm<=.02 for hint in hints)):
                    tempo=embedded_bpm;source='embedded RIFF ACID duration-consistent candidate'
                elif embedded_bpm:metadata_warning='Embedded and filename tempo conflict; no tempo preferred until review.'
                elif row['measured_bpm'] and (row['measured_bytes'],row['measured_modified'])==(row['bytes'],row['modified_ns']) and row['measured_confidence']>=.6:tempo=row['measured_bpm'];source='audio analysis (heuristic confidence)'
                elif len(hints)==1 and 20<=next(iter(hints))<=400:tempo=next(iter(hints));source='filename hint'
                distance=abs(math.log2(bpm/tempo)) if bpm and tempo else 1.5 if bpm else 0
                score=distance+(1 if info['role']=='unknown' else 0)+(.8 if info['role']=='fx' and role!='fx' else 0)
                reasons=[info['feature_provenance']]
                if metadata_warning:reasons.append(metadata_warning)
                if tempo:reasons.append(f'{tempo:g} BPM from {source}')
                if root is not None:reasons.append('percussion key-independent' if info['role']=='drum' else 'explicit '+info['property_provenance']['key']+' key match' if info['key'] else 'unknown key explicitly allowed')
                yield (score,name,row['path'],dict(row),info,tempo,source,reasons)
        shortlisted=heapq.nsmallest(100,candidates(),key=lambda item:(item[0],item[1].casefold(),item[2]))
    result=[]
    for score,name,path,row,info,tempo,source,reasons in shortlisted:
        try:stat=Path(path).stat()
        except OSError:continue
        if not Path(path).is_file() or (stat.st_size,stat.st_mtime_ns)!=(row['bytes'],row['modified_ns']):continue
        options=[{'beat_scale':scale,'rate':bpm/(tempo*scale)} for scale in (1,.5,2) if .5<=bpm/(tempo*scale)<=2] if tempo and bpm else []
        result.append({'id':hashlib.sha256(path.encode('utf-8')).hexdigest()[:16],
                       'sample':name,'path':path,'bytes':row['bytes'],'modified_ns':row['modified_ns'],
                       **info,'bpm':tempo,'bpm_source':source,'tempo_options':options,'rank_cost':round(score,6),'reasons':reasons})
        if len(result)==limit:break
    # Return the original observations separately so desktop inspection never
    # relabels a correction/analysis estimate as a filename hint.
    with closing(sqlite3.connect(Path(catalog).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        for candidate in result:
            observation=db.execute('SELECT * FROM sample WHERE path=?',(candidate['path'],)).fetchone()
            if observation is None or (observation['bytes'],observation['modified_ns'])!=(candidate['bytes'],candidate['modified_ns']):raise ValueError('catalog changed during retrieval; retry the query')
            candidate['catalog_observation']=describe_sample(observation,db)
            identity=candidate['catalog_observation'].get('content_identity')
            if identity and identity['matches_catalog_stat']:
                candidate['id']='c_'+identity['sha256'][:24];candidate['content_sha256']=identity['sha256']
                candidate['identity_basis']='historical content hash; resolve before accepting a plan'
            else:candidate['identity_basis']='path-derived provisional ID; hash before resolving a plan'
            embedded=candidate['catalog_observation'].get('embedded_metadata')
            if embedded:embedded.pop('chunks',None) # Compact shortlist; full chunk inventory remains catalog.metadata.
    # Identical hashed aliases share a musical asset ID. Keep the highest-ranked
    # representative rather than sending duplicate IDs into compact planning.
    unique={}
    for candidate in result:unique.setdefault(candidate['id'],candidate)
    result=list(unique.values());planning=[]
    for candidate in result:
        compact={'id':candidate['id'],'sample':candidate['sample'],'role':'texture' if candidate['role']=='fx' else candidate['role'],
                 'provenance':{'role':candidate['property_provenance']['role']}}
        if candidate['key']:compact.update(candidate['key']);compact['provenance']['key']=candidate['property_provenance']['key']
        if candidate.get('content_sha256'):compact['content_sha256']=candidate['content_sha256']
        if candidate['bpm'] is not None:
            compact['bpm']=candidate['bpm'];source=candidate['bpm_source']
            compact['provenance']['bpm']='user_correction' if source.startswith('user') else 'embedded_duration_candidate' if source.startswith('embedded') else 'audio_heuristic' if source.startswith('audio') else 'filename'
        planning.append(compact)
    return {'candidates':result,'planning_candidates':planning,'catalog_rows_considered':visited,'candidate_limit':limit,
            'availability_window':100,'warnings':['Only the best100 stored matches are checked for current file availability. Rescan stale entries before retrying.','Role/key properties distinguish user corrections from filename hints. Stored identity does not mean freshly verified live content. No automatic transposition or half/double-time choice.']}

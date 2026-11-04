"""Deterministic bounded musical intentions -> exact-tick voiced note events.

The model may propose these intentions, but never supplies executable code. This
compiler is also the local fallback. Style rules are explicit preferences, not a
claim that every valid result sounds good.
"""
from fractions import Fraction
import itertools
import math

TPQ=960
SCALES={"major":(0,2,4,5,7,9,11),"minor":(0,2,3,5,7,8,10)}
PARTS={"bass":(36,59),"chords":(48,76),"melody":(60,84)}
NOTE_FIELDS=('part','tick','length','pitch','velocity')


def note_identity(note):return tuple(note[key] for key in NOTE_FIELDS)


def chord_label(score,chord):
    scale=SCALES[score['mode']];degree=chord['degree']-1;root=(score['root']+scale[degree])%12
    third=(scale[(degree+2)%7]-scale[degree])%12;fifth=(scale[(degree+4)%7]-scale[degree])%12
    return ('C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B')[root]+('dim' if fifth==6 else 'm' if third==3 else '')


def render_without_parts(score,parts):
    """Internal audio subset only; canonical project/locks remain untouched."""
    from copy import deepcopy
    result=deepcopy(score);result['notes']=[note for note in result['notes'] if note['part'] not in parts]
    if 'note_locks' in result:result['note_locks']=[note for note in result['note_locks'] if note['part'] not in parts]
    result.pop('musical_locks',None) # Internal render subset only; canonical locks remain intact.
    return result


def realize_form(value,bars,density,parts):
    if value is None:return [{'bars':bars,'role':'main','density':density,'parts':parts}]
    if value=='bed':
        if bars<4:return [{'bars':bars,'role':'outro','density':'sparse','parts':parts}]
        edge=max(1,min(4,bars//8));middle=bars-2*edge;lift=max(1,middle//3)
        value=[{'bars':edge,'role':'intro','density':'sparse','parts':[part for part in parts if part!='melody'] or parts[:1]},
               {'bars':middle-lift,'role':'main','density':density,'parts':parts},
               {'bars':lift,'role':'lift','density':'medium' if density=='sparse' else 'busy','parts':parts},
               {'bars':edge,'role':'outro','density':'sparse','parts':[part for part in parts if part!='melody'] or parts[:1]}]
    if not isinstance(value,list) or not 1<=len(value)<=8:raise ValueError('form requires one to eight sections')
    result=[]
    for section in value:
        if (not isinstance(section,dict) or not {'bars','role'}<=section.keys() or section.keys()-{'bars','role','density','parts'}
                or type(section['bars']) is not int or section['bars']<1 or section['role'] not in ('intro','main','lift','break','outro')):
            raise ValueError('invalid musical form section')
        selection=section.get('parts',parts);rhythm=section.get('density',density)
        if (not isinstance(selection,list) or not selection or any(part not in parts for part in selection)
                or len(selection)!=len(set(selection)) or rhythm not in ('sparse','medium','busy')):
            raise ValueError('form contradicts part selection or density')
        result.append({**section,'parts':selection,'density':rhythm})
    if sum(section['bars'] for section in result)!=bars:raise ValueError('form bars must match the requested duration')
    return result


def validate_melody_pattern(pattern):
    """One bar of relative triad tones/rests; deterministic realization owns pitches."""
    if not isinstance(pattern,list) or not 1<=len(pattern)<=16:raise ValueError('melody pattern requires one to16 cells')
    for cell in pattern:
        if (not isinstance(cell,dict) or set(cell)!={'tone','ticks','velocity'}
                or type(cell['tone']) is not int or cell['tone'] not in (-1,0,1,2)
                or type(cell['ticks']) is not int or not 120<=cell['ticks']<=3840 or cell['ticks']%120
                or type(cell['velocity']) is not int or not (cell['velocity']==0 if cell['tone']==-1 else 1<=cell['velocity']<=121)):
            raise ValueError('invalid relative melody tone, rhythm or velocity')
    if sum(cell['ticks'] for cell in pattern)!=3840:raise ValueError('melody pattern must fill one four-beat bar')
    if all(cell['tone']==-1 for cell in pattern):raise ValueError('melody pattern requires an audible note')
    if sum(cell['tone']>=0 for cell in pattern)>8:raise ValueError('melody pattern exceeds eight sounding notes per bar')
    return pattern


def compile_intent(intent):
    if (not isinstance(intent,dict) or set(intent)-{"bpm","root","mode","bars","progression","density","seed","resolve","bar_offset","previous_chord","seconds","parts","form","melody_pattern"}):
        raise ValueError("unsupported musical intention fields")
    bpm=intent.get("bpm",120)
    if type(bpm) not in (int,float) or not math.isfinite(bpm) or not 40<=bpm<=240:raise ValueError("invalid tempo")
    tempo=Fraction(str(bpm))
    bars=intent.get("bars",8)
    root=intent.get("root",0)
    mode=intent.get("mode","major")
    density=intent.get("density","medium")
    seed=intent.get("seed",0)
    progression=intent.get("progression",[1,6,4,5])
    resolve=intent.get("resolve",True)
    offset=intent.get("bar_offset",0)
    previous=intent.get("previous_chord",[60,64,67])
    seconds=intent.get("seconds")
    parts=intent.get("parts",list(PARTS))
    if (not isinstance(parts,list) or not parts or any(not isinstance(part,str) or part not in PARTS for part in parts)
            or len(parts)!=len(set(parts))):raise ValueError("invalid musical part selection")
    if seconds is not None:
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0.1<=seconds<=240:
            raise ValueError("duration must be 0.1 to240 seconds")
        derived=math.ceil(Fraction(str(seconds))*tempo/240)
        if "bars" in intent and bars!=derived:raise ValueError("bars contradict requested duration")
        bars=derived
    if (type(bars) is not int or not 1<=bars<=240
            or type(root) is not int or not 0<=root<=11 or not isinstance(mode,str) or mode not in SCALES
            or density not in ("sparse","medium","busy") or type(seed) is not int
            or not isinstance(progression,list) or not 1<=len(progression)<=16
            or any(type(degree) is not int or not 1<=degree<=7 for degree in progression)):
        raise ValueError("invalid tempo, form, key, density or progression")
    if (type(resolve) is not bool or type(offset) is not int or not 0<=offset<=1_000_000_000
            or not isinstance(previous,list) or len(previous)!=3
            or any(type(pitch) is not int or not 48<=pitch<=76 for pitch in previous)
            or previous!=sorted(set(previous))):
        raise ValueError("invalid compact musical boundary state")
    duration=Fraction(str(seconds)) if seconds is not None else Fraction(bars*4*60)/tempo
    if duration>240:
        raise ValueError("musical form exceeds four minutes")
    form=realize_form(intent.get('form'),bars,density,parts)
    pattern=intent.get('melody_pattern')
    if 'melody_pattern' in intent:validate_melody_pattern(pattern)
    per_bar=[section for section in form for _ in range(section['bars'])]
    scale=SCALES[mode]
    notes=[]
    harmony=[]
    previous=tuple(previous)
    motif=(0,2,1,2,0,1,2,1)

    def add(part,tick,length,pitch,velocity):
        if part in active_parts:notes.append({"part":part,"tick":tick,"length":length,"pitch":pitch,"velocity":max(1,velocity+energy)})

    for bar in range(bars):
        section=per_bar[bar];active_parts=section['parts'];bar_density=section['density']
        energy={'intro':-12,'main':0,'lift':6,'break':-16,'outro':-14}[section['role']]
        # Resolve the last bar to tonic. Narrative gaps come from sparse rhythm.
        degree=(1 if resolve and bar==bars-1 else progression[(bar+offset)%len(progression)])-1
        pitch_classes=tuple((root+scale[(degree+offset)%7])%12 for offset in (0,2,4))
        choices=[]
        for inversion in itertools.product(*(range(pc+48,77,12) for pc in pitch_classes)):
            voiced=tuple(sorted(inversion))
            if len(set(voiced))==3 and voiced[-1]-voiced[0]<=16:
                choices.append(voiced)
        chord=min(choices,key=lambda pitches:(sum(abs(a-b) for a,b in zip(pitches,previous)),pitches))
        previous=chord
        start=bar*4*TPQ
        harmony.append({"bar":bar,"degree":degree+1,"pitches":list(chord)})
        for pitch in chord:add("chords",start,4*TPQ-60,pitch,60 if bar==0 else 66)
        bass=36+pitch_classes[0]
        for beat in (0,2):add("bass",start+beat*TPQ,TPQ*3//2,bass,78 if beat==0 else 68)
        positions=(0,2) if bar_density=="sparse" else (0,1,2,3) if bar_density=="medium" else tuple(Fraction(i,2) for i in range(8))
        for index,beat in enumerate(positions if pattern is None else ()):
            if bar==bars-1 and beat>2:continue
            pitch=chord[motif[(index+bar+offset+seed)%len(motif)]]+12
            while pitch>84:pitch-=12
            length=TPQ//3 if bar_density=="busy" else TPQ*3//4
            add("melody",start+int(beat*TPQ),length,pitch,72+(index%2)*6)
        if pattern is not None:
            cursor=start
            for cell in pattern:
                if cell['tone']>=0:
                    pitch=chord[cell['tone']]+12
                    while pitch>84:pitch-=12
                    add('melody',cursor,cell['ticks'],pitch,cell['velocity'])
                cursor+=cell['ticks']
    end=round(duration*tempo*TPQ/60)
    notes=[{**note,"length":min(note["length"],end-note["tick"])} for note in notes if note["tick"]<end]
    result={"schema":1,"generator":"intent-compiler-2","form":form,"tpq":TPQ,"bpm":bpm,"meter":[4,4],
            "root":root,"mode":mode,"bars":bars,"duration_ticks":end,
            "duration_frames":round(duration*44100),
            "seed":seed,"harmony":harmony,"notes":sorted(notes,key=lambda n:(n["tick"],n["part"],n["pitch"])),
            "ending_state":{"next_bar":offset+bars,"previous_chord":list(previous),"seed":seed}}
    if pattern is not None:
        from copy import deepcopy
        result.update(generator='intent-compiler-3',melody_pattern=deepcopy(pattern))
    validate(result)
    return result


def validate(score):
    if not isinstance(score,dict) or score.get("tpq")!=TPQ or score.get("meter")!=[4,4]:
        raise ValueError("unsupported score timing")
    if 'melody_pattern' in score:validate_melody_pattern(score['melody_pattern'])
    if 'melody_patterns' in score:
        patterns=score['melody_patterns']
        if (not isinstance(patterns,dict) or len(patterns)>240 or any(not isinstance(key,str) or not key.isascii() or not key.isdigit()
                or str(int(key))!=key or not 0<=int(key)<score.get('bars',0) for key in patterns)):raise ValueError('invalid saved melody pattern bars')
        for pattern in patterns.values():validate_melody_pattern(pattern)
    if (type(score.get('root')) is not int or not 0<=score['root']<=11 or not isinstance(score.get('mode'),str) or score['mode'] not in SCALES
            or type(score.get('bars')) is not int or not 1<=score['bars']<=240):raise ValueError('invalid score key or form')
    if 'form' in score:realize_form(score['form'],score['bars'],'medium',list(PARTS))
    if 'harmony' in score:
        harmony=score['harmony']
        if not isinstance(harmony,list) or len(harmony)!=score['bars']:raise ValueError('invalid harmonic intention timeline')
        for index,chord in enumerate(harmony):
            if (not isinstance(chord,dict) or set(chord)!={'bar','degree','pitches'} or type(chord['bar']) is not int or chord['bar']!=index
                    or type(chord['degree']) is not int or not 1<=chord['degree']<=7 or not isinstance(chord['pitches'],list)
                    or len(chord['pitches'])!=3 or any(type(pitch) is not int or not 48<=pitch<=76 for pitch in chord['pitches'])
                    or chord['pitches']!=sorted(set(chord['pitches'])) or chord['pitches'][-1]-chord['pitches'][0]>16):
                raise ValueError('invalid harmonic intention voicing')
            pcs={(score['root']+SCALES[score['mode']][(chord['degree']-1+offset)%7])%12 for offset in (0,2,4)}
            if {pitch%12 for pitch in chord['pitches']}!=pcs:raise ValueError('harmonic voicing contradicts the accepted key/degree')
    bpm=score.get("bpm")
    if type(bpm) not in (int,float) or not math.isfinite(bpm) or not 40<=bpm<=240:
        raise ValueError("invalid score tempo")
    tempo=Fraction(str(bpm))
    end=score.get("duration_ticks")
    if type(end) is not int or end<=0 or Fraction(end*60,TPQ)/tempo>240+Fraction(60,TPQ)/tempo:
        raise ValueError("invalid score duration")
    notes=score.get("notes")
    frames=score.get("duration_frames",round(Fraction(end*60*44100,TPQ)/tempo))
    if (type(frames) is not int or not 1<=frames<=240*44100 or
            abs(frames-round(Fraction(end*60*44100,TPQ)/tempo))>math.ceil(60*44100/(TPQ*bpm))):
        raise ValueError("invalid score sample duration")
    if not isinstance(notes,list) or not 1<=len(notes)<=8192:
        raise ValueError("score note count exceeds bounds")
    if any(not isinstance(note,dict) or type(note.get("tick")) is not int for note in notes):
        raise ValueError("invalid score note")
    active={}
    for note in sorted(notes,key=lambda n:n.get("tick",-1)):
        if not isinstance(note,dict) or set(note)!={"part","tick","length","pitch","velocity"}:
            raise ValueError("invalid note fields")
        part=note["part"]
        if not isinstance(part,str) or part not in PARTS or any(type(note[field]) is not int for field in ("tick","length","pitch","velocity")):
            raise ValueError("invalid note type/part")
        tick,length,pitch,velocity=(note[field] for field in ("tick","length","pitch","velocity"))
        low,high=PARTS[part]
        if not (0<=tick<end and 0<length<=end-tick and low<=pitch<=high and 1<=velocity<=127):
            raise ValueError("note exceeds timing/register/velocity bounds")
        key=(part,pitch)
        if active.get(key,-1)>tick:raise ValueError("overlapping same-pitch note in part")
        active[key]=tick+length
    locks=score.get('note_locks',[])
    if (not isinstance(locks,list) or len(locks)>8192 or any(not isinstance(note,dict) or set(note)!=set(NOTE_FIELDS)
            or not isinstance(note['part'],str) or any(type(note[key]) is not int for key in NOTE_FIELDS[1:]) for note in locks)):
        raise ValueError('invalid locked note identities')
    locked={note_identity(note) for note in locks};known={note_identity(note) for note in notes}
    if len(locked)!=len(locks) or not locked<=known:
        raise ValueError('a locked note was changed or removed; unlock it explicitly before editing')
    from musical_locks import validate as validate_musical_locks
    validate_musical_locks(score)
    return score


def set_note_locks(score,indices):
    """Lock exact accepted event values, not unstable array indices across edits."""
    from copy import deepcopy
    validate(score)
    if (not isinstance(indices,list) or len(indices)>8192 or any(type(index) is not int or not 0<=index<len(score['notes']) for index in indices)
            or len(indices)!=len(set(indices))):raise ValueError('invalid selected note indices')
    result=deepcopy(score);result['note_locks']=[deepcopy(score['notes'][index]) for index in sorted(indices)]
    revision=result.get('edit_revision',0)
    if type(revision) is not int or not 0<=revision<1_000_000_000:raise ValueError('invalid score edit revision')
    result['edit_revision']=revision+1
    validate(result)
    return result


def preserve_note_locks(previous,replacement,released_note_indices=None,released_musical_locks=None):
    """Replacing a saved score cannot implicitly erase event locks or retime them."""
    from musical_locks import preserve
    preserve(previous,replacement,released_musical_locks)
    releases=[] if released_note_indices is None else released_note_indices
    if not isinstance(releases,list) or len(releases)>8192 or any(type(index) is not int or not previous or not 0<=index<len(previous['notes']) for index in releases) or len(set(releases))!=len(releases):raise ValueError('invalid explicitly released saved note indices')
    if not previous or not previous.get('note_locks'):return
    locked={note_identity(note) for note in previous['note_locks']}
    released={note_identity(previous['notes'][index]) for index in releases}
    if not released<=locked:raise ValueError('released indices must identify saved locked notes')
    required=locked-released
    if required and (not replacement or replacement.get('bpm')!=previous['bpm'] or replacement.get('tpq')!=previous['tpq']
            or replacement.get('meter')!=previous['meter']
            or not required<=
                   {note_identity(note) for note in replacement.get('note_locks',[])}):
        raise ValueError('saved note locks/timing cannot be replaced; unlock saved notes explicitly first')


def edit_harmony(score,changes):
    """Revoice selected diatonic bars, preserving rhythm and unrelated/locked events.

    This edits explicit intentions, not arbitrary audio harmony. Crossing notes or
    non-triad manual chord textures require deliberate note editing instead.
    """
    from copy import deepcopy
    validate(score)
    if not score.get('harmony'):raise ValueError('score has no accepted harmonic intention timeline')
    if not isinstance(changes,list) or not 1<=len(changes)<=16:raise ValueError('provide one to sixteen harmonic edits')
    selected={}
    for change in changes:
        if (not isinstance(change,dict) or set(change)!={'bar','degree'} or type(change['bar']) is not int
                or not 0<=change['bar']<score['bars'] or type(change['degree']) is not int or not 1<=change['degree']<=7
                or change['bar'] in selected):raise ValueError('invalid or duplicate harmonic bar edit')
        selected[change['bar']]=change['degree']
    result=deepcopy(score);locked={note_identity(note) for note in score.get('note_locks',[])};changed=False
    for bar,degree in sorted(selected.items()):
        if result['harmony'][bar]['degree']==degree:continue
        start=bar*4*TPQ;end=min((bar+1)*4*TPQ,result['duration_ticks'])
        notes=[note for note in result['notes'] if note['tick']<end and note['tick']+note['length']>start]
        if any(note['tick']<start or note['tick']+note['length']>end for note in notes):raise ValueError('a note crosses the harmonic boundary; split/shorten it explicitly first')
        pcs=tuple((score['root']+SCALES[score['mode']][(degree-1+offset)%7])%12 for offset in (0,2,4))
        if any(note_identity(note) in locked and note['pitch']%12 not in pcs for note in notes):raise ValueError('harmonic change conflicts with a locked note; unlock it explicitly first')
        voices=sorted({note['pitch'] for note in notes if note['part']=='chords'})
        if len(voices)>3:raise ValueError('automatic revoicing supports at most three distinct chord voices per bar')
        locked_voices={note['pitch'] for note in notes if note['part']=='chords' and note_identity(note) in locked}
        previous=result['harmony'][max(0,bar-1)]['pitches'];following=result['harmony'][min(score['bars']-1,bar+1)]['pitches']
        choices=[]
        for inversion in itertools.product(*(range(pc+48,77,12) for pc in pcs)):
            voiced=tuple(sorted(inversion))
            if len(set(voiced))!=3 or voiced[-1]-voiced[0]>16:continue
            for assignment in itertools.permutations(voiced,len(voices)):
                mapping=dict(zip(voices,assignment))
                if any(mapping[pitch]!=pitch for pitch in locked_voices):continue
                cost=sum(abs(a-b) for a,b in zip(voiced,previous))+sum(abs(a-b) for a,b in zip(voiced,following))+sum(abs(a-b) for a,b in mapping.items())
                choices.append((cost,voiced,assignment))
        if not choices:raise ValueError('no supported voicing preserves the selected note locks')
        _,voiced,assignment=min(choices);mapping=dict(zip(voices,assignment))
        for note in notes:
            if note_identity(note) in locked:continue
            if note['part']=='chords':note['pitch']=mapping[note['pitch']]
            else:
                low,high=PARTS[note['part']];allowed={pcs[0]} if note['part']=='bass' else set(pcs)
                note['pitch']=min((pitch for pitch in range(low,high+1) if pitch%12 in allowed),key=lambda pitch:(abs(pitch-note['pitch']),pitch))
        result['harmony'][bar]={'bar':bar,'degree':degree,'pitches':list(voiced)};changed=True
    if not changed:return result
    revision=result.get('edit_revision',0)
    if type(revision) is not int or not 0<=revision<1_000_000_000:raise ValueError('invalid score edit revision')
    result.update(edit_revision=revision+1,harmonic_editor='deterministic-diatonic-revoicing-1')
    if isinstance(result.get('ending_state'),dict):result['ending_state']['previous_chord']=result['harmony'][-1]['pitches'][:]
    validate(result)
    return result


def apply_melody_pattern(score,bars,pattern):
    """Replace selected melody bars only; unrelated/manual/locked events survive."""
    from copy import deepcopy
    validate(score);validate_melody_pattern(pattern)
    if (not score.get('harmony') or not isinstance(bars,list) or not 1<=len(bars)<=240
            or any(type(bar) is not int or not 0<=bar<score['bars'] for bar in bars) or len(set(bars))!=len(bars)):
        raise ValueError('select valid distinct harmonic bars for melody rhythm')
    selected=set(bars);result=deepcopy(score);kept=[];end=score['duration_ticks']
    for note in result['notes']:
        intersects=note['part']=='melody' and any(note['tick']<(bar+1)*3840 and note['tick']+note['length']>bar*3840 for bar in selected)
        if not intersects:kept.append(note);continue
        if note['tick']//3840 not in selected or (note['tick']+note['length']-1)//3840!=note['tick']//3840:
            raise ValueError('melody crosses a selected bar boundary; split/shorten it explicitly first')
    for bar in sorted(selected):
        cursor=bar*3840;chord=score['harmony'][bar]['pitches']
        for cell in pattern:
            if cursor<end and cell['tone']>=0:
                pitch=chord[cell['tone']]+12
                while pitch>84:pitch-=12
                kept.append({'part':'melody','tick':cursor,'length':min(cell['ticks'],end-cursor),'pitch':pitch,'velocity':cell['velocity']})
            cursor+=cell['ticks']
    result['notes']=sorted(kept,key=lambda note:(note['tick'],note['part'],note['pitch']))
    revision=result.get('edit_revision',0)
    if type(revision) is not int or not 0<=revision<1_000_000_000:raise ValueError('invalid score edit revision')
    result.update(edit_revision=revision+1,rhythm_editor='relative-triad-pattern-1')
    # Bar patterns are edit provenance. Accepted note events remain authoritative.
    patterns=result.setdefault('melody_patterns',{})
    if not isinstance(patterns,dict) or len(patterns)>240:raise ValueError('invalid saved melody patterns')
    for bar in selected:patterns[str(bar)]=deepcopy(pattern)
    validate(result)
    return result


def native_notes(score,part):
    validate(score)
    if part not in PARTS:raise ValueError("unknown part")
    def frame(tick):return round(Fraction(tick*60*44100,TPQ)/Fraction(str(score["bpm"])))
    return "".join(f"{frame(note['tick'])} {frame(note['tick']+note['length'])} {note['pitch']} {note['velocity']}\n"
                   for note in score["notes"] if note["part"]==part)


def edit_score(score,changes):
    """Ordered atomic note edits; preserve every unaffected accepted event."""
    from copy import deepcopy
    validate(score)
    if not isinstance(changes,list) or not 1<=len(changes)<=256:raise ValueError('provide one to256 note changes')
    candidate=deepcopy(score)
    for change in changes:
        if not isinstance(change,dict):raise ValueError('invalid note change')
        action=change.get('action')
        if action=='add' and set(change)=={'action','note'}:candidate['notes'].append(deepcopy(change['note']));continue
        if (action not in ('set','remove') or set(change)!=({'action','index','field','value'} if action=='set' else {'action','index'})
                or type(change['index']) is not int or not 0<=change['index']<len(candidate['notes'])):raise ValueError('invalid note change or index')
        if action=='remove':candidate['notes'].pop(change['index'])
        else:
            if change['field'] not in ('part','tick','length','pitch','velocity'):raise ValueError('unknown note field')
            candidate['notes'][change['index']][change['field']]=change['value']
    validate(candidate)
    revision=candidate.get('edit_revision',0)
    if type(revision) is not int or not 0<=revision<1_000_000_000:raise ValueError('invalid score edit revision')
    candidate['edit_revision']=revision+1
    return candidate

"""Versioned local projects: exact source identities, revisions and missing-asset checks."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from render import resolve_sections
from assets import digest


def validate_parameters(parameters,has_plugin):
    import math
    if not isinstance(parameters,dict) or len(parameters)>128 or (parameters and not has_plugin):
        raise ValueError("generic parameter edits require an effect and at most128 values")
    for key,value in parameters.items():
        if (not isinstance(key,str) or not key.isascii() or not key.isdigit() or not 0<=int(key)<=2**32-1
                or type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1):
            raise ValueError("invalid generic project parameter")


def processing_pins(project):
    result={'processing':project.get('processing',{}),'instruments':{}}
    for part,spec in project.get('instruments',{}).items():
        identities=project['instrument_assets'][part];pins={}
        for key in ('plugin','state'):
            if spec.get(key):pins[key]={'path':spec[key],'sha256':identities[key+'_sha256']}
        if identities.get('controller_sha256'):pins['controller_state']={'path':spec['state']+'.controller','sha256':identities['controller_sha256']}
        result['instruments'][part]=pins
    return result


def check_processing_pin(expected,path,checksum):
    if expected is None:return
    if (not isinstance(expected,dict) or set(expected)!={'path','sha256'} or
            not isinstance(expected['path'],str) or not isinstance(expected['sha256'],str) or len(expected['sha256'])!=64):
        raise ValueError('invalid expected processing asset')
    if Path(expected['path']).resolve()==path.resolve() and expected['sha256']!=checksum:
        raise ValueError('pinned processing content changed; review and adopt the update explicitly')


def save(path, sections, catalog=None, *, expected_revision=0, brief=None,processing=None,score=None,parameters=None,instruments=None,source_assets=None,voice=None,voice_settings=None,voice_asset=None,expected_processing=None,expected_instruments=None,released_note_indices=None,released_musical_locks=None):
    if voice_asset is not None:validate_asset(voice_asset)
    if source_assets is not None:
        if not isinstance(source_assets,dict) or len(source_assets)>16:raise ValueError('invalid pinned source map')
        for name,asset in source_assets.items():
            validate_asset(asset)
            if not isinstance(name,str) or not name:raise ValueError('invalid pinned source name')
            source=Path(asset['path'])
            if not source.is_file() or source.stat().st_size!=asset['bytes'] or digest(source)!=asset['sha256']:
                raise ValueError('pinned sample is missing or changed; relink identical content explicitly')
    def resolve(name):
        if source_assets and name in source_assets:return Path(source_assets[name]['path'])
        from render import catalog_music
        if catalog is None:raise ValueError('sample source is not pinned and catalog is unavailable')
        return catalog_music(catalog,name)
    if score is not None:
        from music import validate
        validate(score)
        if sections:
            resolved=resolve_sections(sections,catalog,resolver=resolve)
            if abs(round(sum(length for _,length,_ in resolved)*44100)-score["duration_frames"])>1:
                raise ValueError("sample plan and composed score must have matching duration")
        else:resolved=[]
    else:
        resolved = resolve_sections(sections, catalog,resolver=resolve)
    previous = read(path) if path.exists() else None
    if previous and previous['schema']==7:raise ValueError('routing projects must be saved with project.graph.save')
    from music import preserve_note_locks
    preserve_note_locks((previous or {}).get('score'),score,released_note_indices,released_musical_locks)
    prior=processing_pins(previous) if previous else {'processing':{},'instruments':{}}
    expected_processing=prior['processing'] if expected_processing is None else expected_processing
    expected_instruments=prior['instruments'] if expected_instruments is None else expected_instruments
    if (not isinstance(expected_processing,dict) or not isinstance(expected_instruments,dict) or
            len(json.dumps([expected_processing,expected_instruments]))>64000):raise ValueError('invalid expected processing pins')
    revision = previous["revision"] if previous else 0
    if type(expected_revision) is not int or revision != expected_revision:
        raise ValueError("project revision conflict; reopen before saving")
    if brief is not None and (not isinstance(brief, dict) or len(json.dumps(brief)) > 16000):
        raise ValueError("invalid brief state")
    assets = []
    for source, _, _ in resolved:
        if not source.is_file():
            raise ValueError(f"missing asset: {source}")
        before=source.stat()
        checksum=digest(source)
        after=source.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError("asset changed while saving project")
        assets.append({"path": str(source.resolve()), "sha256": checksum, "bytes": after.st_size})
    processing=processing or {}
    if not isinstance(processing,dict) or processing.keys()-{"worker","plugin","state","instrument","notes","automation","class_id"}:
        raise ValueError("invalid project processing fields")
    saved_processing={}
    from plugins import fingerprint
    for kind,value in processing.items():
        if kind=="class_id":
            if not isinstance(value,str) or len(value)!=32 or any(ch not in "0123456789ABCDEF" for ch in value):
                raise ValueError("invalid plugin class ID")
            saved_processing[kind]=value
            continue
        source=Path(value).resolve()
        if not source.exists():raise ValueError(f"missing processing asset: {kind}")
        checksum=fingerprint(source) if kind in ("plugin","instrument") else digest(source)
        check_processing_pin(expected_processing.get(kind),source,checksum)
        saved_processing[kind]={"path":str(source),"sha256":checksum}
        if kind=="state":
            controller=Path(str(source)+".controller")
            if controller.exists():
                checksum=digest(controller);check_processing_pin(expected_processing.get('controller_state'),controller,checksum)
                saved_processing["controller_state"]={"path":str(controller),"sha256":checksum}
            elif expected_processing.get('state',{}).get('path')==str(source) and expected_processing.get('controller_state'):
                raise ValueError('pinned controller state is missing')
    result = {"format": "sample-arranger-project", "schema": 5 if sections and source_assets is not None else 4 if score is not None and sections else 2 if score is not None else 1, "revision": revision + 1,
              "catalog": str(catalog.resolve()) if catalog else None, "sections": sections, "assets": assets, "brief": brief,
              "processing":saved_processing}
    if score is not None:result["score"]=score
    if instruments:
        if score is None:raise ValueError("part assignments require an accepted score")
        from compose import validate_instruments
        from copy import deepcopy
        instruments=deepcopy(validate_instruments(instruments))
        identities={}
        for part,spec in instruments.items():
            source=Path(spec["plugin"]).resolve();spec["plugin"]=str(source)
            identity={"plugin_sha256":fingerprint(source)}
            expected=expected_instruments.get(part,{})
            if not isinstance(expected,dict):raise ValueError('invalid expected instrument pins')
            check_processing_pin(expected.get('plugin'),source,identity['plugin_sha256'])
            if spec.get("state"):
                source=Path(spec["state"]).resolve();spec["state"]=str(source)
                identity["state_sha256"]=digest(source)
                check_processing_pin(expected.get('state'),source,identity['state_sha256'])
                controller=Path(str(source)+".controller")
                if controller.is_file():
                    identity["controller_sha256"]=digest(controller)
                    check_processing_pin(expected.get('controller_state'),controller,identity['controller_sha256'])
                elif expected.get('state',{}).get('path')==str(source) and expected.get('controller_state'):
                    raise ValueError('pinned instrument controller state is missing')
            identities[part]=identity
        result.update(schema=5 if sections and source_assets is not None else 4 if sections else 3,instruments=instruments,instrument_assets=identities)
    if parameters:
        validate_parameters(parameters,"plugin" in saved_processing)
        result["parameters"]=parameters
    if voice:
        from narration import settings
        voice=Path(voice).resolve();before=voice.stat();checksum=digest(voice);after=voice.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('narration changed while saving')
        expected=voice_asset or (previous or {}).get('narration')
        if expected and Path(expected['path']).resolve()==voice and checksum!=expected['sha256']:
            raise ValueError('pinned narration changed; select replacement content explicitly')
        result.update(schema=6,narration={'path':str(voice),'bytes':after.st_size,'sha256':checksum,'settings':settings(voice_settings)})
    elif voice_settings or voice_asset:raise ValueError('narration settings/identity require supplied audio')
    if previous and previous.get('relocations'):result['relocations']=previous['relocations']
    if previous and previous.get('processing_updates'):result['processing_updates']=previous['processing_updates']
    atomic_write(path,result)
    return result


def validate_asset(asset):
    if (not isinstance(asset,dict) or set(asset)!={'path','sha256','bytes'} or not isinstance(asset['path'],str)
            or type(asset['bytes']) is not int or asset['bytes']<0 or not isinstance(asset['sha256'],str)
            or len(asset['sha256'])!=64 or any(ch not in '0123456789abcdef' for ch in asset['sha256'])):
        raise ValueError('invalid project source identity')


def atomic_write(path,result):
    # Atomic replacement preserves the previous project on interruption. Single local owner only.
    descriptor, temporary = tempfile.mkstemp(prefix=".project-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read(path):
    if path.stat().st_size > 2_000_000:
        raise ValueError("project exceeds size cap")
    result = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(result,dict) and result.get('schema')==7:
        from graph_project import validate
        validate(result)
        return result
    if (not isinstance(result, dict) or result.get("format") != "sample-arranger-project"
            or type(result.get("schema")) is not int or result.get("schema") not in (1,2,3,4,5,6) or type(result.get("revision")) is not int
            or result["revision"] < 1 or not isinstance(result.get("sections"), list)
            or not isinstance(result.get("assets"), list)
            or not (0 if result.get("schema")>=2 else 1) <= len(result["sections"]) <= 16
            or len(result["assets"]) != len(result["sections"])):
        raise ValueError("unsupported or malformed project")
    if result['schema'] in (2,3,4) or 'score' in result:
        from music import validate
        validate(result.get("score"))
        if result["sections"] and result["schema"] not in (4,5,6):raise ValueError("unsupported mixed project schema")
        if result["schema"]==4 and not result["sections"]:raise ValueError("hybrid project requires sample sections")
    if result['schema']==5 and not result['sections']:raise ValueError('pinned source project requires sample sections')
    if result['schema']==6:
        narration=result.get('narration')
        if (not isinstance(narration,dict) or set(narration)!={'path','bytes','sha256','settings'}
                or (not result['sections'] and 'score' not in result)):raise ValueError('invalid narration project')
        validate_asset({key:narration[key] for key in ('path','bytes','sha256')})
        from narration import settings
        settings(narration['settings'])
    elif 'narration' in result:raise ValueError('narration requires project schema6')
    for asset in result['assets']:validate_asset(asset)
    if result.get('instruments') and 'score' not in result:raise ValueError('instrument assignments require accepted score')
    if result["schema"]==3 or result.get("instruments"):
        from compose import validate_instruments
        validate_instruments(result.get("instruments"))
        if not isinstance(result.get("instrument_assets"),dict) or result["instrument_assets"].keys()!=result["instruments"].keys():
            raise ValueError("invalid pinned instrument assets")
        for part,identity in result["instrument_assets"].items():
            required={"plugin_sha256"}|({"state_sha256"} if result["instruments"][part].get("state") else set())
            if (not isinstance(identity,dict) or not required<=identity.keys()
                    or identity.keys()-required-{"controller_sha256"}
                    or any(not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value)
                           for value in identity.values())):
                raise ValueError("invalid instrument identity hashes")
    validate_parameters(result.get("parameters",{}),"plugin" in result.get("processing",{}))
    return result


def inspect(path):
    return inspect_data(read(path))


def inspect_data(result):
    if result.get('schema')==7:
        from graph_project import inspect_data as inspect_graph
        return inspect_graph(result)
    issues = []
    warnings=[]
    for index, asset in enumerate(result["assets"]):
        if (not isinstance(asset, dict) or set(asset) != {"path", "sha256", "bytes"}
                or not isinstance(asset["path"], str)):
            raise ValueError("invalid project asset")
        source = Path(asset["path"])
        if not source.is_file():
            issues.append({"section": index, "issue": "missing", "path": str(source)})
        elif source.stat().st_size != asset["bytes"] or digest(source) != asset["sha256"]:
            issues.append({"section": index, "issue": "changed", "path": str(source)})
    from plugins import fingerprint
    if result.get('narration'):
        asset=result['narration'];source=Path(asset['path'])
        if not source.is_file():issues.append({'kind':'narration','issue':'missing','path':str(source)})
        elif source.stat().st_size!=asset['bytes'] or digest(source)!=asset['sha256']:
            issues.append({'kind':'narration','issue':'changed','path':str(source)})
    processing=result.get("processing",{})
    if not isinstance(processing,dict) or processing.keys()-{"worker","plugin","state","controller_state","instrument","notes","automation","class_id"}:
        raise ValueError("invalid processing assets")
    for kind,asset in processing.items():
        if kind=="class_id":continue
        if not isinstance(asset,dict) or set(asset)!={"path","sha256"}:raise ValueError("invalid processing asset")
        source=Path(asset["path"])
        if not source.exists():issues.append({"kind":kind,"issue":"missing","path":str(source)})
        elif (fingerprint(source) if kind in ("plugin","instrument") else digest(source))!=asset["sha256"]:
            issues.append({"kind":kind,"issue":"changed","path":str(source)})
    for part,spec in result.get("instruments",{}).items():
        identity=result["instrument_assets"][part]
        source=Path(spec["plugin"])
        if not source.exists():issues.append({"part":part,"issue":"missing_plugin","path":str(source)})
        elif fingerprint(source)!=identity.get("plugin_sha256"):issues.append({"part":part,"issue":"changed_plugin","path":str(source)})
        if spec.get("state"):
            state=Path(spec["state"])
            if not state.is_file() or digest(state)!=identity.get("state_sha256"):
                issues.append({"part":part,"issue":"missing_or_changed_state","path":str(state)})
            controller=Path(str(state)+".controller")
            if identity.get("controller_sha256") and (not controller.is_file() or digest(controller)!=identity["controller_sha256"]):
                issues.append({"part":part,"issue":"missing_or_changed_controller","path":str(controller)})
    return {"project": result, "issues": issues,"warnings":warnings, "ready": not issues}


def pinned_sections(path):
    report=inspect(path)
    if not report["ready"]:raise ValueError("project has missing or changed assets; recover it before rendering")
    project=report["project"]
    if report["warnings"]:project["runtime_warnings"]=report["warnings"]
    if not project["sections"]:return project,[]
    if project['schema'] in (5,6):
        assets=iter(project['assets'])
        sections=resolve_sections(project['sections'],None,resolver=lambda name:Path(next(assets)['path']))
    else:sections=resolve_sections(project["sections"],Path(project["catalog"]))
    for resolved,asset in zip(sections,project["assets"]):
        if resolved[0].resolve()!=Path(asset["path"]).resolve():
            raise ValueError("catalog source differs from pinned project asset; recover it explicitly")
    return project,sections


def relink(path,replacements,expected_revision):
    from copy import deepcopy
    from datetime import datetime,timezone
    result=deepcopy(inspect(path)['project'])
    if type(expected_revision) is not int or result['revision']!=expected_revision:raise ValueError('project revision conflict')
    if (not isinstance(replacements,dict) or not 1<=len(replacements)<=16 or
            any(not isinstance(key,str) or not key.isascii() or not key.isdigit() or int(key)>=len(result['assets']) for key in replacements)):
        raise ValueError('replacements require existing zero-based section indices')
    history=result.get('relocations',[])
    if not isinstance(history,list) or len(history)+len(replacements)>128:raise ValueError('project relocation history exceeds bound')
    for key,value in replacements.items():
        if not isinstance(value,str) or not value:raise ValueError('replacement must be a local path')
        source=Path(value).resolve();asset=result['assets'][int(key)]
        if not source.is_file() or source.stat().st_size!=asset['bytes'] or digest(source)!=asset['sha256']:
            raise ValueError('replacement must match original sample content exactly')
        previous=asset['path']
        for shared in result['assets']:
            if shared['path']==previous and shared['sha256']==asset['sha256']:shared['path']=str(source)
        history.append({'from':previous,'to':str(source),'sha256':asset['sha256'],'utc':datetime.now(timezone.utc).isoformat()})
    result.update(schema=6 if 'narration' in result else 5,revision=result['revision']+1,relocations=history)
    atomic_write(path,result)
    return inspect(path)


def processing_updates(path):
    project=read(path);pins=processing_pins(project);changes=[]
    if project['schema']==7:
        from graph_project import review
        return review(project)
    from plugins import fingerprint
    def compare(selector,kind,asset):
        if kind=='class_id':return
        source=Path(asset['path'])
        checksum=(fingerprint(source) if kind in ('plugin','instrument') else digest(source)) if source.exists() else None
        if checksum!=asset['sha256']:changes.append({'selector':selector,'path':str(source),'previous_sha256':asset['sha256'],'current_sha256':checksum})
    for kind,asset in pins['processing'].items():compare('processing.'+kind,kind,asset)
    for part,assets in pins['instruments'].items():
        for kind,asset in assets.items():compare('instruments.'+part+'.'+kind,kind,asset)
    return {'revision':project['revision'],'changes':changes,'compatibility':'hash review only; not a plugin compatibility certification'}


def edit_notes(path,changes,expected_revision):
    from music import edit_score
    result=read(path)
    if type(expected_revision) is not int or expected_revision!=result['revision']:raise ValueError('project revision conflict')
    if 'score' not in result:raise ValueError('project has no accepted MIDI score')
    result['score']=edit_score(result['score'],changes);result['revision']+=1
    atomic_write(path,result)
    return inspect(path)


def lock_notes(path,indices,expected_revision):
    from music import set_note_locks
    result=read(path)
    if type(expected_revision) is not int or expected_revision!=result['revision']:raise ValueError('project revision conflict')
    if 'score' not in result:raise ValueError('project has no accepted score')
    result['score']=set_note_locks(result['score'],indices);result['revision']+=1
    atomic_write(path,result)
    return inspect(path)


def edit_harmonic_intentions(path,changes,expected_revision):
    from music import edit_harmony
    result=read(path)
    if type(expected_revision) is not int or expected_revision!=result['revision']:raise ValueError('project revision conflict')
    if 'score' not in result:raise ValueError('project has no accepted score')
    result['score']=edit_harmony(result['score'],changes);result['revision']+=1
    atomic_write(path,result)
    return inspect(path)


def adopt_processing(path,updates,expected_revision):
    from datetime import datetime,timezone
    result=read(path)
    if result['schema']==7:
        from graph_project import adopt
        return adopt(path,updates,expected_revision)
    if type(expected_revision) is not int or expected_revision!=result['revision']:raise ValueError('project revision conflict')
    if not isinstance(updates,dict) or not 1<=len(updates)<=16:raise ValueError('choose one to sixteen processing changes')
    observed={change['selector']:change for change in processing_updates(path)['changes']}
    history=result.get('processing_updates',[])
    if not isinstance(history,list) or len(history)+len(updates)>128:raise ValueError('processing update history exceeds bounds')
    for selector,checksum in updates.items():
        change=observed.get(selector)
        if not change or checksum is None or change['current_sha256']!=checksum:raise ValueError('processing update no longer matches reviewed content')
        fields=selector.split('.')
        if fields[0]=='processing':result['processing'][fields[1]]['sha256']=checksum
        else:
            key={'plugin':'plugin_sha256','state':'state_sha256','controller_state':'controller_sha256'}[fields[2]]
            result['instrument_assets'][fields[1]][key]=checksum
        history.append({**change,'utc':datetime.now(timezone.utc).isoformat()})
    result.update(revision=result['revision']+1,processing_updates=history)
    atomic_write(path,result)
    return inspect(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("save", "inspect"))
    parser.add_argument("project", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--expected-revision", type=int, default=0)
    args = parser.parse_args()
    try:
        if args.operation == "inspect":
            result = inspect(args.project)
        else:
            if not args.plan or not args.catalog:
                parser.error("save requires --plan and --catalog")
            result = save(args.project, json.loads(args.plan.read_text(encoding="utf-8-sig")),
                          args.catalog, expected_revision=args.expected_revision)
        print(json.dumps(result))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()

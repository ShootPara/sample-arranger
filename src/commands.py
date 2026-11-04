"""Local bounded JSON command interface shared by automation and desktop.

No listener, shell execution, credentials or remote path/upload interpretation.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import os
import time
from runtime import module_command

OPERATIONS={
    "capabilities":(set(),set()),
    "contracts.schema":(set(),{'operation'}),
    "ai.status":(set(),set()),
    "ai.connection.check":(set(),set()),
    "ai.score.plan":({'initial','intent'},{'refined'}),
    "ai.samples.plan":({'catalog','initial','intent'},{'refined'}),
    "brief.plan":({"catalog","initial"},{"refined"}),
    "planning.prepare":({"musical_state","candidates"},{"context","output_limit"}),
    "planning.validate":({"musical_state","candidates","response"},{"context","output_limit"}),
    "planning.resolve":({"catalog","musical_state","candidates","response"},{"context","output_limit"}),
    "planning.current":({"musical_state","response"},set()),
    "midi.planning.prepare":({"musical_state"},{"context","output_limit"}),
    "midi.planning.validate":({"musical_state","response"},{"context","output_limit"}),
    "midi.planning.current":({"musical_state","response"},set()),
    "score.compile":({"intent"},set()),
    "score.edit":({"score","changes"},set()),
    "score.locks.set":({"score","indices"},set()),
    "score.harmony.edit":({"score","changes"},set()),
    "score.pattern.apply":({"score","bars","pattern"},set()),
    "score.musical.locks.set":({"score","selections"},set()),
    "compose.render":({"intent","jobs"},{"voice","worker","plugin","instruments","voice_settings"}),
    "arrangement.validate":({"catalog","sections"},set()),
    "arrangement.ensemble":({"catalog","seconds"},{"bpm","root","mode","roles","role_terms","excluded_roles","allow_unverified_harmony"}),
    "arrangement.render":({"catalog","sections","jobs"},{"voice","worker","plugin","state","automation","class_id","tail_seconds","instrument","notes","voice_settings"}),
    "project.inspect":({"project"},set()),
    "project.bundle.export":({"project","destination"},set()),
    "project.bundle.inspect":({"package"},set()),
    "project.bundle.match":({"package","expected_manifest_sha256"},{"available_assets"}),
    "project.bundle.import":({"package","destination","expected_manifest_sha256"},{"bindings"}),
    "project.notes.edit":({"project","changes","expected_revision"},set()),
    "project.notes.lock":({"project","indices","expected_revision"},set()),
    "project.harmony.edit":({"project","changes","expected_revision"},set()),
    "project.save":({"project","sections"},{"catalog","expected_revision","brief","processing","score","parameters","instruments","source_assets","voice","voice_settings","voice_asset","expected_processing","expected_instruments","released_note_indices","released_musical_locks"}),
    "project.graph.save":({"project","graph","sources","worker","seconds"},{"expected_revision","tempo","tail_seconds","brief","voice","voice_settings","score","source_assets","released_musical_locks"}),
    "project.graph.relink":({"project","replacements","expected_revision"},set()),
    "project.relink":({"project","replacements","expected_revision"},set()),
    "project.processing.review":({"project"},set()),
    "project.processing.adopt":({"project","updates","expected_revision"},set()),
    "project.render":({"project","jobs"},{"voice","worker","plugin","state","voice_settings"}),
    "jobs.submit":({"jobs","request_id","project","project_sha256"},{"voice","voice_sha256","voice_settings"}),
    "jobs.status":({"jobs","request_id"},set()),
    "jobs.list":({"jobs"},{"limit"}),
    "jobs.delete":({"jobs","job_id","expected_manifest_sha256"},{"forget_receipt"}),
    "jobs.forget":({"jobs","request_id","request_sha256"},set()),
    "jobs.temporary":({"project","project_sha256","ack_file"},{"timeout_seconds"}),
    "jobs.temporary.cleanup":(set(),set()),
    "plugins.inspect":({"worker","plugin"},{"state","class_id"}),
    "plugins.parameter.convert":({"worker","plugin","class_id","parameter_id"},{"state","display","normalized"}),
    "plugins.scan":({"registry","worker","root"},set()),
    "plugins.list":({"registry"},{"limit","offset"}),
    "plugins.retry":({"registry","worker","plugin","expected_sha256"},set()),
    "plugins.edit":({"worker","plugin","class_id","presets"},{"state","parameters"}),
    "plugins.state.save":({"worker","plugin","class_id","presets"},{"state","parameters"}),
    "plugins.preset.import":({"worker","plugin","preset","presets"},set()),
    "plugins.preset.export":({"worker","plugin","state","destination"},{"class_id"}),
    "graph.render":({"graph","sources","worker","seconds","jobs"},{"voice","tempo","tail_seconds","voice_settings","score"}),
    "catalog.search":({"catalog"},{"term","limit","offset"}),
    "catalog.rank":({"catalog"},{"term","bpm","role","root","mode","limit","excluded_roles","allow_unknown_key"}),
    "catalog.scan":({"catalog","root"},{"metadata_only"}),
    "catalog.measure":({"catalog","path"},set()),
    "catalog.metadata":({"catalog","path"},set()),
    "catalog.correct":({"catalog","path","bpm"},set()),
    "catalog.hash":({"catalog","path"},set()),
    "catalog.annotate":({"catalog","path","expected_sha256"},{"role","root","mode","clear"}),
    "catalog.duplicates":({"catalog"},{"limit","offset"}),
    "catalog.relocate":({"catalog","path","replacement","expected_sha256"},set()),
    "catalog.forget":({"catalog","path","expected_sha256"},set()),
    "assets.waveform":({"path"},set()),
    "audio.inspect":({"path"},set()),
    "narration.inspect":({"voice","seconds"},{"voice_settings"}),
    "continuous.play":(set(),{"builtin","catalog","sample","bpm","chunks","worker","plugin","evolve","state","class_id","instruments","intent","effect_output_bus"}),
    "continuous.cleanup":(set(),set()),
}
PATHS={"catalog","jobs","voice","worker","plugin","state","automation","instrument","notes","project","presets","root","path","sink","preset","destination","registry","ack_file","replacement","package"}


def execute(request):
    if not isinstance(request,dict) or set(request)!={"contract","operation","arguments"} or type(request["contract"]) is not int or request["contract"]!=1:
        raise ValueError("request requires contract=1, operation and arguments only")
    operation=request["operation"]
    if not isinstance(operation,str) or operation not in OPERATIONS:
        raise ValueError("unknown operation; use capabilities")
    arguments=request["arguments"]
    required,optional=OPERATIONS[operation]
    if not isinstance(arguments,dict) or not required<=arguments.keys() or arguments.keys()-required-optional:
        raise ValueError(f"invalid arguments for {operation}; required={sorted(required)}, optional={sorted(optional)}")
    args=dict(arguments)
    path_keys=PATHS-{'root'} if operation in ('catalog.rank','catalog.annotate','arrangement.ensemble') else PATHS
    for key in path_keys & args.keys():
        if not isinstance(args[key],str) or not args[key] or len(args[key])>32768:
            raise ValueError(f"{key} must be a local path string")
        args[key]=Path(args[key]).resolve()
    if operation=="capabilities":
        from resources import command_memory_bytes,plugin_memory_bytes
        result={"contract":1,"deployment":"local process only","max_request_bytes":256000,
                'resources':{'command_tree_memory_bytes':command_memory_bytes(),'default_plugin_tree_memory_bytes':plugin_memory_bytes(),
                             'shared_cap_across_concurrent_commands':False,'activity_slots':'one each: render, continuous, inspect, editor'},
                "output":{"format":"mp3","bitrate_kbps":192,"max_seconds":240},
                "live_inference":__import__('broker_port').status(),
                "operations":{name:{"required":sorted(req),"optional":sorted(opt)} for name,(req,opt) in OPERATIONS.items()}}
    elif operation=='contracts.schema':
        from contract_schema import request_schema
        result=request_schema(**args)
    elif operation=='ai.status':
        from broker_port import status
        result=status()
    elif operation=='ai.connection.check':
        from ai_planning import check_connection
        result=check_connection()
    elif operation in ('ai.score.plan','ai.samples.plan'):
        from ai_planning import score_plan,sample_plan
        result=(score_plan if operation=='ai.score.plan' else sample_plan)(**args)
    elif operation.startswith('midi.planning.'):
        from midi_planning import prepare,validate_proposal,current
        args['state']=args.pop('musical_state')
        result={'midi.planning.prepare':prepare,'midi.planning.validate':validate_proposal,'midi.planning.current':current}[operation](**args)
    elif operation in ('planning.prepare','planning.validate','planning.resolve','planning.current'):
        from planning_context import prepare_request,validate_prepared,resolve_prepared,require_current
        args['state']=args.pop('musical_state')
        result={'planning.prepare':prepare_request,'planning.validate':validate_prepared,'planning.resolve':resolve_prepared,'planning.current':require_current}[operation](**args)
    elif operation=='audio.inspect':
        from audio_measurements import measure
        result=measure(args['path'])
    elif operation=='catalog.rank':
        from retrieval import rank
        result=rank(**args)
    elif operation=='arrangement.ensemble':
        from ensemble import propose
        result=propose(**args)
    elif operation=="score.edit":
        from music import edit_score
        result=edit_score(**args)
    elif operation=='score.pattern.apply':
        from music import apply_melody_pattern
        result=apply_melody_pattern(**args)
    elif operation=='score.musical.locks.set':
        from musical_locks import set_locks
        result=set_locks(**args)
    elif operation=='score.locks.set':
        from music import set_note_locks
        result=set_note_locks(**args)
    elif operation=='score.harmony.edit':
        from music import edit_harmony
        result=edit_harmony(**args)
    elif operation=='project.harmony.edit':
        from project import edit_harmonic_intentions
        result=edit_harmonic_intentions(args.pop('project'),**args)
    elif operation=='project.notes.lock':
        from project import lock_notes
        result=lock_notes(args.pop('project'),**args)
    elif operation=="project.notes.edit":
        from project import edit_notes
        result=edit_notes(args.pop('project'),**args)
    elif operation=="narration.inspect":
        from narration import inspect_placement
        result=inspect_placement(**args)
    elif operation=="assets.waveform":
        from waveforms import preview
        result=preview(args["path"])
    elif operation in ('catalog.hash','catalog.duplicates','catalog.relocate','catalog.forget','catalog.annotate'):
        from catalog_identity import execute as identity_operation
        result=identity_operation(args.pop('catalog'),operation.split('.')[1],**args)
    elif operation.startswith("catalog."):
        from process import run
        command=module_command('catalog','--db',str(args.pop('catalog')))
        if operation=="catalog.search":
            term=args.get("term","")
            limit=args.get("limit",50);offset=args.get("offset",0)
            if not isinstance(term,str) or len(term)>512 or type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or not 0<=offset<=1_000_000:
                raise ValueError("invalid catalog page request")
            command.extend(("search",term,"--limit",str(limit),"--offset",str(offset)))
        elif operation=="catalog.scan":
            if type(args.get("metadata_only",True)) is not bool:raise ValueError("metadata_only must be boolean")
            command.extend(("scan",str(args["root"])))
            if args.get("metadata_only",True):command.append("--metadata-only")
        elif operation in ("catalog.measure","catalog.metadata"):command.extend(("measure" if operation.endswith('measure') else 'metadata',str(args["path"])))
        else:
            bpm=args["bpm"]
            if type(bpm) not in (int,float) or not 20<=bpm<=400:raise ValueError("corrected BPM must be20 to400")
            command.extend(("correct-tempo",str(args["path"]),str(bpm)))
        completed=run(command,capture_output=True,text=True,timeout=1800 if operation=="catalog.scan" else 120)
        if completed.returncode:raise ValueError(completed.stderr.strip())
        result=json.loads(completed.stdout)
    elif operation=='continuous.cleanup':
        from spool import cleanup,status
        root=Path(os.environ['LOCALAPPDATA'],'SampleArranger/continuous')
        result={'removed_chunks':cleanup(root),**status(root)}
    elif operation=="continuous.play":
        from continuous import play
        from render import catalog_music
        from planner import local_sections
        builtin=args.pop("builtin",False);evolve=args.pop("evolve",False)
        if type(builtin) is not bool or type(evolve) is not bool:raise ValueError("continuous mode flags must be boolean")
        catalog=args.pop("catalog",None);sample=args.pop("sample",None)
        if builtin:
            if sample or catalog or evolve:raise ValueError("built-in mode does not use a sample catalog/rotation")
            source=None;sources=None
        else:
            if catalog is None or not isinstance(sample,str) or not sample:raise ValueError("sample playback requires catalog and sample")
            sections=local_sections(catalog,sample,60,args.get("bpm",120)) if evolve else []
            sources=[catalog_music(catalog,section["sample"]) for section in sections]
            source=sources[0] if sources else catalog_music(catalog,sample)
        try:os.set_blocking(sys.stderr.fileno(),False);nonblocking=True
        except (OSError,ValueError):nonblocking=False
        def report(event):
            try:os.write(sys.stderr.fileno(),(json.dumps({"continuous":event})+"\n").encode("utf-8"))
            except BlockingIOError:pass # Health events cannot stall the audio consumer.
        result=play(source,sources=sources,builtin=builtin,on_event=report if nonblocking else None,**args)
    elif operation=="brief.plan":
        from brief import plan
        for name in ("initial","refined"):
            if name in args and (not isinstance(args[name],str) or len(args[name].encode("utf-8"))>12000):
                raise ValueError("brief must be bounded text")
        result=plan(args.pop("catalog"),**args)
    elif operation=="score.compile":
        from music import compile_intent
        result=compile_intent(args["intent"])
    elif operation=="compose.render":
        from compose import compose
        result=compose(**args)
    elif operation=="graph.render":
        from graph_jobs import render_music_graph
        result=render_music_graph(**args)
    elif operation.startswith("arrangement."):
        from render import resolve_sections,render
        sections=resolve_sections(args.pop("sections"),args.pop("catalog"))
        duration=sum(length for _,length,_ in sections)
        if duration>240:raise ValueError("arrangement exceeds four minutes")
        if operation=="arrangement.validate":
            missing=[str(path) for path,_,_ in sections if not path.is_file()]
            result={"ready":not missing,"missing":missing,"seconds":duration,"sections":len(sections)}
        else:result=render(sections[0][0],args.pop("voice",None),duration,args.pop("jobs"),sections=sections,**args)
    elif operation=='jobs.temporary':
        from temporary_jobs import deliver
        result=deliver(**args)
    elif operation=='jobs.temporary.cleanup':
        from temporary_jobs import recover
        result=recover()
    elif operation in ('jobs.list','jobs.delete','jobs.forget'):
        from artifacts import list_jobs,delete_job,forget_receipt
        result={'jobs.list':list_jobs,'jobs.delete':delete_job,'jobs.forget':forget_receipt}[operation](**args)
    elif operation.startswith('jobs.'):
        from job_control import submit,status
        result=(submit if operation=='jobs.submit' else status)(**args)
    elif operation=="project.processing.review":
        from project import processing_updates
        result=processing_updates(args['project'])
    elif operation=="project.processing.adopt":
        from project import adopt_processing
        result=adopt_processing(**{('path' if key=='project' else key):value for key,value in args.items()})
    elif operation.startswith('project.bundle.'):
        from project_bundle import package,inspect,materialize,match
        result={'project.bundle.export':package,'project.bundle.inspect':inspect,'project.bundle.import':materialize,'project.bundle.match':match}[operation](**args)
    elif operation=="project.inspect":
        from project import inspect
        result=inspect(args["project"])
    elif operation=="project.graph.save":
        from graph_project import save
        result=save(**args)
    elif operation=="project.graph.relink":
        from graph_project import relink
        result=relink(**args)
    elif operation=="project.save":
        from project import save
        result=save(args.pop("project"),**args)
    elif operation=='project.relink':
        from project import relink
        result=relink(args.pop('project'),**args)
    elif operation=="project.render":
        from project import pinned_sections,digest
        from render import render
        path=args.pop("project")
        project,sections=pinned_sections(path)
        if project.get('narration'):
            args.setdefault('voice',Path(project['narration']['path']))
            args.setdefault('voice_settings',project['narration']['settings'])
        for key,value in project.get("processing",{}).items():
            if key=="controller_state":continue
            if key not in args:args[key]=value if key=="class_id" else Path(value["path"])
        def perform():
            provenance={"project_sha256":digest(path),"project_revision":project["revision"],"project":project}
            if project['schema']==7:
                from graph_jobs import render_music_graph
                if set(args)-{'jobs','voice','voice_settings'}:raise ValueError('routing project processing overrides require an explicit saved revision')
                return render_music_graph(project['graph'],project['graph_sources'],Path(project['worker']),
                                          project['seconds'],tempo=project['tempo'],tail_seconds=project['tail_seconds'],
                                          score=project.get('score'),provenance=provenance,**args)
            if 'score' in project:
                from compose import render_score_job
                return render_score_job(project["score"],provenance=provenance,instruments=project.get("instruments"),sections=sections or None,**args)
            return render(sections[0][0],args.pop("voice",None),sum(length for _,length,_ in sections),
                          args.pop("jobs"),sections=sections,provenance=provenance,**args)
        if project.get("parameters"):
            from scratch import scratch
            with scratch(args['jobs']) as directory:
                automation=Path(directory)/"initial.txt"
                automation.write_text("".join(f"0 {key} {value}\n" for key,value in project["parameters"].items()),encoding="utf-8")
                args["automation"]=automation
                result=perform()
        else:result=perform()
    elif operation in ('plugins.scan','plugins.list','plugins.retry'):
        from plugin_registry import scan,list_plugins,retry
        result={'plugins.scan':scan,'plugins.list':list_plugins,'plugins.retry':retry}[operation](**args)
    elif operation.startswith("plugins.preset."):
        from preset_files import import_preset,export_preset
        result=(import_preset if operation.endswith("import") else export_preset)(**args)
    else:
        from plugins import inspect,edit,capture_state,convert_parameter
        result={"plugins.inspect":inspect,"plugins.edit":edit,"plugins.state.save":capture_state,'plugins.parameter.convert':convert_parameter}[operation](**args)
    return {"contract":1,"operation":operation,"result":result}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request",type=Path,help="UTF-8 JSON file; omit for stdin")
    parser.add_argument("--cancel-file",type=Path,help="Stop when this caller-owned control marker exists; never use a source asset")
    parser.add_argument('--events',action='store_true',help='Emit schema1 lifecycle/stage JSON on stderr; stdout remains one terminal result')
    args=parser.parse_args()
    if args.cancel_file:os.environ["ARRANGER_CANCEL_FILE"]=str(args.cancel_file.resolve())
    if args.events:os.environ['ARRANGER_EVENT_STREAM']='1'
    from events import emit
    started=time.monotonic();operation=None
    try:
        from process_group import own_process_tree
        own_process_tree()
        if os.name=='nt':
            from command_guard import current_identity
            pid,creation=current_identity();print(f'command_ready {pid} {creation}',file=sys.stderr,flush=True)
        if args.request:
            with args.request.open("rb") as source:data=source.read(256001)
        else:data=sys.stdin.buffer.read(256001)
        if len(data)>256000:raise ValueError("request exceeds 256000-byte cap")
        request=json.loads(data.decode('utf-8-sig'))
        if isinstance(request,dict) and isinstance(request.get('operation'),str) and request['operation'] in OPERATIONS:operation=request['operation']
        emit('started',operation=operation)
        result=execute(request)
        emit('completed',operation=operation,elapsed_seconds=round(time.monotonic()-started,3))
        print(json.dumps(result,allow_nan=False))
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,sqlite3.Error,subprocess.SubprocessError) as error:
        from command_errors import describe
        marker=os.environ.get('ARRANGER_CANCEL_FILE')
        report=describe(error,canceled=bool(marker and Path(marker).exists()))
        emit('failed',operation=operation,code=report['code'],elapsed_seconds=round(time.monotonic()-started,3))
        print(json.dumps({"contract":1,"error":report}))
        raise SystemExit(2)


if __name__=="__main__":main()

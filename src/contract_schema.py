"""Machine-readable structural requests generated from the shared operation registry.

Cross-field music/state/identity validation remains authoritative in commands.
Schema export performs no audio, plugin, catalog or AI execution.
"""
from copy import deepcopy


def graph_contracts():
    text={'type':'string','minLength':1,'maxLength':32768}
    name={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_]{0,31}$'}
    reference={'type':'object','required':['node','bus'],'properties':{'node':name,'bus':{'type':'integer','minimum':0,'maximum':7}},'additionalProperties':False}
    gain=deepcopy(reference);gain['properties']['gain']={'type':'number','minimum':-4,'maximum':4}
    point={'type':'object','required':['frame','id','value'],'additionalProperties':False,'properties':{
        'frame':{'type':'integer','minimum':0,'maximum':242*44100},'id':{'type':'integer','minimum':0,'maximum':2**32-1},'value':{'type':'number','minimum':0,'maximum':1}}}
    processor={'type':'object','required':['id','plugin','class_id','input'],'additionalProperties':False,
               'properties':{'id':name,'plugin':text,'class_id':{'type':'string','pattern':'^[0-9A-F]{32}$'},'input':reference,'sidechain':reference,
                             'state':text,'notes':text,'automation':text,'score_part':{'enum':['bass','chords','melody']},
                             'automation_points':{'type':'array','maxItems':8192,'items':point}},
               'allOf':[{'not':{'required':['automation','automation_points']}},{'not':{'required':['notes','score_part']}}]}
    mixer={'type':'object','required':['id','mix'],'additionalProperties':False,'properties':{'id':name,'mix':{'type':'array','minItems':1,'maxItems':16,'items':gain}}}
    graph={'type':'object','required':['nodes','outputs'],'additionalProperties':False,'properties':{
        'nodes':{'type':'array','minItems':1,'maxItems':8,'items':{'oneOf':[processor,mixer]}},
        'outputs':{'type':'array','minItems':1,'maxItems':16,'items':gain}}}
    source={'type':'object','required':['file'],'additionalProperties':False,'properties':{
        'file':text,'loop':{'type':'boolean'},'offset_seconds':{'type':'number','minimum':0,'exclusiveMaximum':240},
        'source_bpm':{'type':'number','minimum':20,'maximum':400},'target_bpm':{'type':'number','minimum':20,'maximum':400},'beat_scale':{'enum':[.5,1,2]}},
        'dependentRequired':{'source_bpm':['target_bpm','beat_scale'],'target_bpm':['source_bpm','beat_scale'],'beat_scale':['source_bpm','target_bpm']}}
    silence={'type':'object','required':['silence'],'properties':{'silence':{'const':True}},'additionalProperties':False}
    sources={'type':'object','minProperties':1,'maxProperties':8,'propertyNames':name,'additionalProperties':{'oneOf':[source,silence]}}
    return graph,sources


def request_schema(operation=None):
    from commands import OPERATIONS,PATHS
    text={'type':'string','minLength':1,'maxLength':32768}
    objects=('intent','musical_state','response','processing','score','instruments','source_assets','voice_asset',
             'expected_processing','expected_instruments','sources','graph','brief')
    fields={key:{'type':'object'} for key in objects}
    fields.update({key:deepcopy(text) for key in PATHS|{'sample','initial','refined','term','operation'}})
    fields['initial']={'type':'string','maxLength':12000};fields['refined']=deepcopy(fields['initial'])
    fields.update({key:{'type':'string','pattern':'^[0-9a-f]{64}$'} for key in ('expected_sha256','project_sha256','voice_sha256','expected_manifest_sha256','request_sha256')})
    fields['class_id']={'type':'string','pattern':'^[0-9A-F]{32}$'}
    fields['parameter_id']={'type':'integer','minimum':0,'maximum':2**32-1}
    fields['effect_output_bus']={'type':'integer','minimum':0,'maximum':7}
    fields['display']={'type':'string','minLength':1,'maxLength':127}
    fields['normalized']={'type':'number','minimum':0,'maximum':1}
    fields['request_id']={'type':'string','format':'uuid'}
    fields['job_id']={'type':'string','pattern':'^job-[0-9a-f-]{36}$'}
    for key in ('metadata_only','builtin','evolve','forget_receipt','allow_unknown_key','clear','allow_unverified_harmony'):fields[key]={'type':'boolean'}
    for key,minimum,maximum in (('expected_revision',0,2**53-1),('context',512,4096),('output_limit',1,1024),('limit',1,100),('offset',0,2**53-1),('chunks',1,1000000),('root',0,11)):
        fields[key]={'type':'integer','minimum':minimum,'maximum':maximum}
    for key,low,high in (('seconds',0,240),('bpm',20,400),('tempo',20,400),('tail_seconds',0,1),('timeout_seconds',1,3600)):
        fields[key]={'type':'number','minimum':low,'maximum':high}
    fields['seconds']={'type':'number','exclusiveMinimum':0,'maximum':240}
    fields['mode']={'enum':['major','minor']};fields['role']={'enum':['drum','bass','chords','melody','fx']}
    fields['excluded_roles']={'type':'array','maxItems':8,'items':{'enum':['drum','bass','chords','melody','fx','piano','guitar','pad']}}
    fields['roles']={'type':'array','minItems':1,'maxItems':4,'uniqueItems':True,'items':{'enum':['drum','bass','chords','melody','fx']}}
    fields['role_terms']={'type':'object','maxProperties':4,'propertyNames':{'enum':['drum','bass','chords','melody','fx']},'additionalProperties':{'type':'string','maxLength':128}}
    for key,maximum in (('sections',16),('changes',256),('candidates',100)):
        fields[key]={'type':'array','maxItems':maximum,'items':{'type':'object'}}
    fields['indices']={'type':'array','maxItems':8192,'uniqueItems':True,'items':{'type':'integer','minimum':0,'maximum':8191}}
    fields['bars']={'type':'array','minItems':1,'maxItems':240,'uniqueItems':True,'items':{'type':'integer','minimum':0,'maximum':239}}
    fields['pattern']={'type':'array','minItems':1,'maxItems':16,'items':{'type':'object','required':['tone','ticks','velocity'],'additionalProperties':False,'properties':{
        'tone':{'type':'integer','enum':[-1,0,1,2]},'ticks':{'type':'integer','minimum':120,'maximum':3840,'multipleOf':120},'velocity':{'type':'integer','minimum':0,'maximum':121}}}}
    fields['released_note_indices']=deepcopy(fields['indices'])
    fields['selections']={'type':'array','maxItems':512,'items':{'type':'object','required':['bar','kind','part'],'additionalProperties':False,'properties':{
        'bar':{'type':'integer','minimum':0,'maximum':239},'kind':{'enum':['section','harmony','rhythm']},'part':{'enum':['all','bass','chords','melody']}}}}
    fields['released_musical_locks']=deepcopy(fields['selections'])
    fields['parameters']={'type':'object','maxProperties':128,'patternProperties':{'^[0-9]+$':{'type':'number','minimum':0,'maximum':1}},'additionalProperties':False}
    fields['updates']={'type':'object','minProperties':1,'maxProperties':16,'additionalProperties':{'type':'string','pattern':'^[0-9a-f]{64}$'}}
    fields['replacements']={'type':'object','minProperties':1,'maxProperties':16,'additionalProperties':deepcopy(text)}
    fields['bindings']={'type':'object','maxProperties':64,'additionalProperties':deepcopy(text)}
    fields['available_assets']={'type':'object','additionalProperties':False,'properties':{key:{'type':'array','maxItems':32,'items':deepcopy(text)} for key in ('worker','plugin')}}
    fields['voice_settings']={'type':'object','properties':{
        'offset_seconds':{'type':'number','minimum':0,'maximum':240},'voice_gain_db':{'type':'number','minimum':-24,'maximum':12},
        'music_gain_db':{'type':'number','minimum':-60,'maximum':0},'ducking':{'type':'boolean'}},'additionalProperties':False}
    fields['graph'],fields['sources']=graph_contracts()
    if operation is not None and operation not in OPERATIONS:raise ValueError('unknown operation for schema')
    variants=[]
    for name,(required,optional) in OPERATIONS.items():
        if operation is not None and operation!=name:continue
        arguments={key:deepcopy(fields[key]) for key in sorted(required|optional)}
        if name in ('score.harmony.edit','project.harmony.edit'):
            arguments['changes']={'type':'array','minItems':1,'maxItems':16,'items':{'type':'object','required':['bar','degree'],'additionalProperties':False,
                'properties':{'bar':{'type':'integer','minimum':0,'maximum':239},'degree':{'type':'integer','minimum':1,'maximum':7}}}}
        if 'root' in arguments and name not in ('catalog.rank','catalog.annotate','arrangement.ensemble'):arguments['root']=deepcopy(text)
        if name=='catalog.annotate':arguments['role']={'enum':['drum','bass','chords','melody','fx','unknown']}
        # schema operation's selector is text, not a file-system path.
        if name=='contracts.schema':arguments={'operation':{'type':'string','enum':sorted(OPERATIONS)}}
        argument_schema={'type':'object','required':sorted(required),'properties':arguments,'additionalProperties':False}
        if name=='plugins.parameter.convert':argument_schema['oneOf']=[{'required':['display']},{'required':['normalized']}]
        variants.append({'type':'object','required':['contract','operation','arguments'],'additionalProperties':False,
                         'properties':{'contract':{'const':1},'operation':{'const':name},
                         'arguments':argument_schema}})
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','title':'Sample Arranger contract1 local request',
            'description':'Structural schema only. Runtime validates UTF-8 byte limits, musical constraints, local content pins, plugin capabilities and lifecycle. No network transport is enabled.',
            'oneOf':variants}

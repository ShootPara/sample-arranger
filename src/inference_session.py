"""Bounded orchestration over an injected normalized inference port.

This is NOT an HTTP client, wire-contract claim, endpoint, model selector or
credential provider. The finished app still has no authorized live adapter. A future
adapter must map its approved principal's real contract and honor every supplied
timeout; Python cannot forcibly interrupt a noncompliant synchronous callback.
"""
import hashlib
import json
import re
import time
import uuid
from copy import deepcopy


class AdmissionUncertain(TimeoutError):
    def __init__(self,request_id,request_sha256):
        super().__init__('inference admission outcome is unknown; reconcile before submitting again')
        self.request_id=request_id;self.request_sha256=request_sha256;self.execution_stopped=None


class AdmissionRejected(RuntimeError):
    def __init__(self,reason):
        if reason not in ('busy','unavailable','quarantined'):raise ValueError('unknown normalized admission rejection')
        super().__init__('inference admission rejected: '+reason);self.reason=reason


class GenerationInterrupted(InterruptedError):
    def __init__(self,reason,job_id,execution_stopped):
        super().__init__(reason);self.job_id=job_id;self.execution_stopped=execution_stopped


def serialized(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode('utf-8')


def validate_request(prompt,context,output_limit,schema):
    if (not isinstance(prompt,str) or type(context) is not int or not 512<=context<=4096
            or type(output_limit) is not int or not 1<=output_limit<=1024
            or len(prompt.encode('utf-8'))+256+12+output_limit>context):raise ValueError('inference exceeds verified conservative UTF8/context/output bounds')
    if not isinstance(schema,dict):raise ValueError('inline inference schema must be an object')
    pending=[(schema,1)];nodes=0
    while pending:
        value,depth=pending.pop();nodes+=1
        if depth>16 or nodes>16000:raise ValueError('inline inference schema exceeds nesting/node limits')
        if isinstance(value,dict):
            if '$ref' in value or '$dynamicRef' in value:raise ValueError('inline inference schemas cannot use references')
            pending.extend((item,depth+1) for item in value.values() if isinstance(item,(dict,list)))
        elif isinstance(value,list):pending.extend((item,depth+1) for item in value if isinstance(item,(dict,list)))
    if len(serialized(schema))>16000:raise ValueError('inline inference schema exceeds16kB')


class InferenceSession:
    """Port: admit(request,timeout), poll(job_id,timeout), cancel(job_id,timeout).

    admit/poll return normalized dicts {id,state,result?}; state is queued/running/
    completed/failed/canceled/expired. cancel returns True only on confirmed stop,
    False for known running refusal, None if unknown. These are internal names, not
    undocumented Trifecta JSON fields. No transport retry or raw/cloud fallback.
    """
    def __init__(self,port,*,cancel_event=None,clock=time.monotonic,sleep=time.sleep):
        self.port=port;self.cancel_event=cancel_event;self.clock=clock;self.sleep=sleep
        self.deadline=clock()+240;self.attempts=0;self.last_job=None;self.last_result=None;self.receipts=[]

    def _canceled(self):return self.cancel_event is not None and self.cancel_event.is_set()

    def _stop(self,job_id):
        try:
            stopped=self.port.cancel(job_id,timeout=1)
            return stopped if type(stopped) is bool else None
        except Exception:return None # Best-effort cancellation cannot prove stop.

    def generate(self,prompt,context,output_limit,schema):
        validate_request(prompt,context,output_limit,schema)
        if self._canceled():raise GenerationInterrupted('inference canceled before admission',None,True)
        if self.attempts>=2 or self.clock()>=self.deadline:raise TimeoutError('logical inference session exhausted two attempts or240 seconds')
        if self.attempts and self.last_result is None:raise RuntimeError('previous transport attempt did not return a completed result; no transport retry')
        self.attempts+=1
        self.last_result=None
        request_id=str(uuid.uuid4())
        # Only compact text and a schema cross this interface: no audio, paths,
        # endpoint/model overrides, shell/tools or credentials are introduced.
        request={'request_id':request_id,'prompt':prompt,'context':context,'output_limit':output_limit,
                 'schema':deepcopy(schema),'queue_timeout_seconds':30,'execution_timeout_seconds':120}
        sha=hashlib.sha256(serialized(request)).hexdigest();receipt={'request_id':request_id,'request_sha256':sha,'job_id':None,'state':'admitting'}
        self.receipts.append(receipt)
        try:response=self.port.admit(request,timeout=min(5,self.deadline-self.clock()))
        except AdmissionRejected as error:
            receipt['state']='rejected_'+error.reason;raise
        except Exception as error:
            receipt['state']='admission_unknown';raise AdmissionUncertain(request_id,sha) from error
        job_id=response.get('id') if isinstance(response,dict) else None
        if not isinstance(job_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',job_id):raise RuntimeError('invalid normalized admission identity; no retry')
        receipt['job_id']=job_id;self.last_job=job_id
        queued_until=min(self.deadline,self.clock()+30);running_until=None;running_seen=False
        for _ in range(256):
            if not isinstance(response,dict) or response.get('id')!=job_id:
                self._stop(job_id);raise RuntimeError('inference returned another job identity; proposal rejected')
            state=response.get('state');receipt['state']=state
            current_deadline=running_until if running_seen else queued_until
            if self._canceled() or self.clock()>=current_deadline:
                stopped=True if state in ('completed','failed','canceled','expired') else self._stop(job_id);receipt['execution_stopped']=stopped
                raise GenerationInterrupted('inference canceled' if self._canceled() else 'inference queue/execution deadline exceeded',job_id,stopped)
            if state=='completed':
                result=response.get('result')
                try:bounded=isinstance(result,dict) and len(serialized(result))<=64000
                except (ValueError,TypeError,RecursionError):bounded=False
                if not bounded or result.get('limited') or result.get('error'):raise RuntimeError('inference result is invalid, failed or truncated; no fallback')
                self.last_result=result;return result
            if state in ('failed','canceled','expired'):raise RuntimeError('inference ended '+state+'; no retry/fallback')
            if state not in ('queued','running') or running_seen and state=='queued':
                self._stop(job_id);raise RuntimeError('inference state regressed or is unknown')
            if state=='running' and not running_seen:running_seen=True;running_until=min(self.deadline,self.clock()+120)
            deadline=running_until if running_seen else queued_until
            if self._canceled() or self.clock()>=deadline:
                stopped=self._stop(job_id);receipt['execution_stopped']=stopped
                raise GenerationInterrupted('inference canceled' if self._canceled() else 'inference queue/execution deadline exceeded',job_id,stopped)
            self.sleep(min(1,max(0,deadline-self.clock())))
            if self._canceled():continue # Reconcile cancellation before another poll.
            try:response=self.port.poll(job_id,timeout=min(5,max(.001,deadline-self.clock())))
            except Exception as error:
                receipt['execution_stopped']=self._stop(job_id);receipt['state']='poll_failed'
                raise RuntimeError('inference polling failed; reconcile the admitted job before resubmitting') from error
        receipt['execution_stopped']=self._stop(job_id)
        raise RuntimeError('inference polling exceeded bounded iteration count')


def propose_with_port(state,candidates,port,*,cancel_event=None,context=4096,output_limit=1024,clock=time.monotonic,sleep=time.sleep):
    from planning_context import propose
    session=InferenceSession(port,cancel_event=cancel_event,clock=clock,sleep=sleep)
    result=propose(deepcopy(state),deepcopy(candidates),session.generate,context=context,output_limit=output_limit)
    return {**result,'inference_receipts':session.receipts,'transport_kind':'injected normalized port; this module supplies no network adapter'}

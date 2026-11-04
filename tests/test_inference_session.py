"""Normalized-port fixtures only: no network, server, credentials or model call."""
from copy import deepcopy
import sys
from pathlib import Path
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from inference_session import InferenceSession,GenerationInterrupted,AdmissionUncertain,AdmissionRejected,propose_with_port


SCHEMA={'type':'object','properties':{'value':{'type':'integer'}},'additionalProperties':False}


class Clock:
    def __init__(self):self.now=0;self.on_sleep=None
    def __call__(self):return self.now
    def sleep(self,seconds):
        self.now+=seconds
        if self.on_sleep:self.on_sleep()


class Port:
    def __init__(self,responses,admission='queued',cancel_result=True):
        self.responses=list(responses);self.admission=admission;self.cancel_result=cancel_result;self.requests=[];self.polls=[];self.cancels=[]
    def admit(self,request,timeout):
        self.requests.append(deepcopy(request))
        if isinstance(self.admission,Exception):raise self.admission
        return {'id':'owned-job-'+str(len(self.requests)),'state':self.admission}
    def poll(self,job_id,timeout):
        self.polls.append((job_id,timeout));response=self.responses.pop(0) if len(self.responses)>1 else self.responses[0]
        if isinstance(response,Exception):raise response
        return {'id':job_id,**deepcopy(response)}
    def cancel(self,job_id,timeout):self.cancels.append((job_id,timeout));return self.cancel_result


class InferenceSessionTests(unittest.TestCase):
    def session(self,port,clock=None,**kwargs):
        clock=clock or Clock();return InferenceSession(port,clock=clock,sleep=clock.sleep,**kwargs)
    def test_owned_queue_running_complete_and_canonical_request_bounds(self):
        port=Port([{'state':'running'},{'state':'completed','result':{'structured':{'value':4}}}]);session=self.session(port)
        result=session.generate('Compact data',4096,1024,SCHEMA)
        self.assertEqual(result['structured'],{'value':4});self.assertEqual(len(port.requests),1)
        self.assertEqual(set(port.requests[0]),{'request_id','prompt','context','output_limit','schema','queue_timeout_seconds','execution_timeout_seconds'})
        self.assertTrue(all(job=='owned-job-1' for job,_ in port.polls));self.assertEqual(port.cancels,[]);self.assertEqual(len(session.receipts[0]['request_sha256']),64)
        for prompt,schema in (('x'*2805,SCHEMA),('x',{'$ref':'https://not-requested.invalid/schema'}),('x',{'description':'x'*16001})):
            with self.assertRaises(ValueError):self.session(port).generate(prompt,4096,1024,schema)
        self.assertEqual(len(port.requests),1,'invalid inputs cannot reach transport')

    def test_cancellation_waiting_running_refusal_and_queue_deadline_are_distinct(self):
        for running,expected in ((False,True),(True,False)):
            event=threading.Event();clock=Clock();clock.on_sleep=event.set;port=Port([{'state':'running' if running else 'queued'}],admission='running' if running else 'queued',cancel_result=not running)
            with self.assertRaises(GenerationInterrupted) as caught:self.session(port,clock,cancel_event=event).generate('x',4096,1024,SCHEMA)
            self.assertEqual(caught.exception.execution_stopped,expected);self.assertEqual(caught.exception.job_id,'owned-job-1');self.assertEqual(len(port.cancels),1);self.assertEqual(port.polls,[])
        clock=Clock();port=Port([{'state':'queued'}]);session=self.session(port,clock)
        with self.assertRaises(GenerationInterrupted) as caught:session.generate('x',4096,1024,SCHEMA)
        self.assertEqual(clock.now,30);self.assertTrue(caught.exception.execution_stopped);self.assertEqual(len(port.cancels),1)
        event=threading.Event();port=Port([{'state':'completed','result':{'structured':{'value':1}}}]);original=port.poll
        def complete_during_cancel(*args,**kwargs):event.set();return original(*args,**kwargs)
        port.poll=complete_during_cancel
        with self.assertRaises(GenerationInterrupted) as caught:self.session(port,cancel_event=event).generate('x',4096,1024,SCHEMA)
        self.assertTrue(caught.exception.execution_stopped);self.assertEqual(port.cancels,[],'completed work needs no DELETE, but must not apply after caller cancellation')

    def test_admission_uncertainty_capacity_and_failed_truncated_or_spoofed_poll_never_retry(self):
        for rejection,expected in ((TimeoutError('lost reply'),AdmissionUncertain),(AdmissionRejected('busy'),AdmissionRejected),(AdmissionRejected('quarantined'),AdmissionRejected)):
            port=Port([],admission=rejection);session=self.session(port)
            with self.assertRaises(expected):session.generate('x',4096,1024,SCHEMA)
            self.assertEqual(len(port.requests),1);self.assertEqual(port.polls,[])
            with self.assertRaisesRegex(RuntimeError,'no transport retry'):session.generate('x',4096,1024,SCHEMA)
        for response in ({'state':'failed','result':{'structured':{'value':1}}},{'state':'completed','result':{'structured':{},'limited':True}},{'id':'someone-elses-job','state':'completed','result':{'structured':{}}},ConnectionError('lost polling reply')):
            port=Port([response]);session=self.session(port)
            with self.assertRaises(RuntimeError):session.generate('x',4096,1024,SCHEMA)
            self.assertEqual(len(port.requests),1)
            self.assertTrue(all(job=='owned-job-1' for job,_ in port.polls+port.cancels))

    def test_one_semantic_repair_and_total_session_ceiling_preserve_state_and_bound_requests(self):
        state={'revision':4,'seconds':4,'brief':'a four second bed','bpm':120};candidates=[{'id':'known','sample':'not-sent.wav','role':'drum','bpm':120}]
        invalid={'revision':4,'sections':[{'asset_id':'known','seconds':3,'beat_scale':1}]};valid={**invalid,'sections':[{'asset_id':'known','seconds':4,'beat_scale':1}]}
        port=Port([{'state':'completed','result':{'structured':invalid}},{'state':'completed','result':{'structured':valid}}]);clock=Clock()
        result=propose_with_port(state,candidates,port,clock=clock,sleep=clock.sleep)
        self.assertEqual(result['attempts'],2);self.assertEqual(len(port.requests),2);self.assertIn('Repair the proposal once',port.requests[1]['prompt']);self.assertNotIn('not-sent.wav',port.requests[0]['prompt'])
        self.assertNotEqual(port.requests[0]['request_id'],port.requests[1]['request_id'])
        for request in port.requests:self.assertLessEqual(len(request['prompt'].encode('utf-8'))+256+12+request['output_limit'],request['context'])
        session=self.session(Port([{'state':'completed','result':{'structured':{}}}]));session.generate('x',4096,1024,SCHEMA);session.generate('x',4096,1024,SCHEMA)
        with self.assertRaises(TimeoutError):session.generate('x',4096,1024,SCHEMA)
        clock=Clock();session=self.session(Port([{'state':'running'}],admission='running'),clock);clock.now=239
        with self.assertRaises(GenerationInterrupted):session.generate('x',4096,1024,SCHEMA)
        self.assertEqual(clock.now,240)

    def test_refinement_mutation_cannot_rewrite_inflight_snapshot_and_current_guard_rejects_it(self):
        from planning_context import require_current
        state={'revision':1,'seconds':4,'brief':'first effective request'};candidates=[{'id':'known','sample':'private.wav','role':'drum'}]
        response={'structured':{'revision':1,'sections':[{'asset_id':'known','seconds':4,'beat_scale':1}]}}
        port=Port([{'state':'completed','result':response}]);original=port.admit
        def mutate(*args,**kwargs):
            state.update(revision=2,brief='authoritative refinement');candidates[0]['id']='changed';return original(*args,**kwargs)
        port.admit=mutate;clock=Clock();result=propose_with_port(state,candidates,port,clock=clock,sleep=clock.sleep)
        self.assertEqual(result['revision'],1)
        with self.assertRaisesRegex(ValueError,'context changed'):require_current(state,result)


if __name__=='__main__':unittest.main()

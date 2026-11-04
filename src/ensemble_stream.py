"""Bounded persistent serial accumulator for up to three MIDI instrument parts.

Each worker delays incoming dry audio by its own latency. Delaying its MIDI by
the sum of upstream latencies aligns every part and the built-in bed. Bridges
hold at most one 512-frame block; no audio files or unbounded queues are used.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from event_stream import EventPackets
from process_group import popen
from plugins import resolve_state
from resources import plugin_memory_bytes


class EnsembleStream:
    def __init__(self,worker,instruments,bpm,*,cancel_event=None):
        if not 1<=len(instruments)<=3:raise ValueError('ensemble requires one to three parts')
        self.processes=[];self.packets=[];self.offsets=[];self.threads=[];self.errors=[]
        self.latency=0;self.submitted=0;self.tail=0;self.tail_clamped=False
        try:
            for part,spec in instruments.items():
                import math
                outputs=spec.get('outputs',[{'bus':0,'gain':1}])
                if not isinstance(outputs,list) or len(outputs)!=1 or not isinstance(outputs[0],dict) or type(outputs[0].get('bus')) is not int or not 0<=outputs[0]['bus']<=7 or outputs[0].keys()-{'bus','gain'}:
                    raise ValueError('continuous ensemble requires one explicit output bus; simultaneous multi-output mixing remains unfinished')
                gain=outputs[0].get('gain',1)
                if type(gain) not in (int,float) or not math.isfinite(gain) or not -4<=gain<=4:raise ValueError('invalid continuous instrument route gain')
                source=Path(spec['plugin']);state=Path(spec['state']) if spec.get('state') else None
                chosen=resolve_state(source,state,spec['class_id'])
                environment=dict(os.environ,ARRANGER_STREAM_EVENTS='1',ARRANGER_STREAM_READY='1',ARRANGER_TEMPO=str(bpm),ARRANGER_STREAM_GAIN=str(gain),ARRANGER_STREAM_OUTPUT_BUS=str(outputs[0]['bus']))
                process=popen([str(worker),str(source),'-','-',str(state) if state else '-','-','-','-',chosen],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment,
                    creationflags=subprocess.CREATE_NO_WINDOW,max_job_bytes=plugin_memory_bytes())
                self.processes.append(process)
                ready=queue.Queue(maxsize=1)
                def diagnostics(child=process,channel=ready):
                    try:
                        line=child.stderr.readline(4097)
                        channel.put_nowait(line)
                        while child.stderr.read(4096):pass
                    except (OSError,ValueError):pass
                thread=threading.Thread(target=diagnostics,daemon=True);thread.start();self.threads.append(thread)
                deadline=time.monotonic()+30
                while True:
                    if cancel_event is not None and cancel_event.is_set():raise InterruptedError('instrument startup canceled')
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('instrument startup exceeded30 seconds')
                    try:line=ready.get(timeout=min(.1,remaining));break
                    except queue.Empty:continue
                try:report=json.loads(line)
                except (ValueError,UnicodeError):raise ValueError('instrument startup did not return a bounded ready report')
                latency=report.get('latency_samples')
                tail=report.get('tail_samples',0)
                if type(tail) is not int or not 0<=tail<=2**32-1:raise ValueError('invalid instrument tail handshake')
                self.tail=max(self.tail,min(tail,44100));self.tail_clamped=self.tail_clamped or tail>44100
                if report.get('ready') is not True or type(latency) is not int or not 0<=latency<=88200:
                    raise ValueError('invalid instrument latency handshake')
                self.offsets.append(self.latency);self.latency+=latency
                if self.latency>88200:raise ValueError('aggregate continuous instrument latency exceeds two seconds')
                self.packets.append(EventPackets(part))
            for index in range(1,len(self.processes)):
                thread=threading.Thread(target=self._bridge,args=(index,),daemon=True)
                thread.start();self.threads.append(thread)
            self.output=self.processes[-1].stdout
        except Exception:
            self.close();raise

    def _bridge(self,index):
        upstream=self.processes[index-1].stdout;target=self.processes[index].stdin
        try:
            while True:
                block=upstream.read(512*8)
                if not block:break
                target.write(self.packets[index].encode(block));target.flush()
            target.close()
        except (OSError,ValueError) as error:
            self.errors.append(str(error))
            for process in self.processes:
                if process.poll() is None:process.kill()

    def add_score(self,score,frames):
        for packet,offset in zip(self.packets,self.offsets):
            packet.add_score(score,frames,start=self.submitted+offset)
        self.submitted+=frames

    def write(self,data):
        for offset in range(0,len(data),512*8):
            self.processes[0].stdin.write(self.packets[0].encode(data[offset:offset+512*8]))
        return len(data)

    def flush(self):self.processes[0].stdin.flush()

    def finish_input(self):self.processes[0].stdin.close()

    def close(self):
        for process in reversed(self.processes):
            if process.poll() is None:process.kill()
            process.wait(timeout=5)
        for process in self.processes:
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream:
                    try:stream.close()
                    except (OSError,ValueError):pass
        for thread in self.threads:thread.join(timeout=1)

    def __enter__(self):return self
    def __exit__(self,*args):self.close()

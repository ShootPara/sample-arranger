"""Persistent VST3-to-waveOut stream with consumption acknowledgments."""
import subprocess
import threading
import time
import wave
import os
import json
import queue
from array import array
from process_group import popen
from resources import plugin_memory_bytes


class DeviceStream:
    def __init__(self, sink, worker=None, plugin=None,*,bpm=None,state=None,class_id=None,on_progress=None,instrument=None,instruments=None,effect_output_bus=0,on_failure=None,cancel_event=None):
        if type(effect_output_bus) is not int or not 0<=effect_output_bus<=7 or effect_output_bus and not plugin:raise ValueError('effect output bus requires a plugin and index0..7')
        if cancel_event is not None and cancel_event.is_set():raise InterruptedError('audio startup canceled before creating processes')
        self.processes = []
        self.frames_sent = 0
        self.frames_heard = 0
        self.condition = threading.Condition()
        self.closed = False
        self.active_stop = None
        self.last_progress = time.monotonic()
        self.last_feed=self.last_progress;self.failure=None;self.on_failure=on_failure;self.cancel_event=cancel_event
        self.draining = False
        self.on_progress=on_progress
        self.last_event=0.0
        upstream = None
        self.packets=None
        self.ensemble=None
        self.diagnostic_threads=[];self.instrument_latency=0;self.instrument_tail=0;self.effect_latency=0;self.effect_tail=0;self.tail_clamped=False
        try:
            if instrument and instruments:raise ValueError("choose one instrument stream interface")
            if instruments:
                from ensemble_stream import EnsembleStream
                self.ensemble=EnsembleStream(worker,instruments,bpm,cancel_event=cancel_event)
                self.processes.extend(self.ensemble.processes);self.input=self.ensemble;upstream=self.ensemble.output
            if instrument:
                from plugins import resolve_state
                from event_stream import EventPackets
                from pathlib import Path
                source=Path(instrument["plugin"]);saved=Path(instrument["state"]) if instrument.get("state") else None
                chosen=resolve_state(source,saved,instrument["class_id"])
                environment=dict(os.environ,ARRANGER_STREAM_EVENTS="1",ARRANGER_STREAM_READY='1',ARRANGER_TEMPO=str(bpm),ARRANGER_STREAM_OUTPUT_BUS='0')
                command=[str(worker),str(source),"-","-",str(saved) if saved else "-","-","-","-",chosen]
                synth=popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                            env=environment,creationflags=subprocess.CREATE_NO_WINDOW,max_job_bytes=plugin_memory_bytes())
                self.processes.append(synth);self.input=synth.stdin;upstream=synth.stdout
                report=self._startup(synth);self.instrument_latency=report['latency_samples'];self.instrument_tail=min(report['tail_samples'],44100);self.tail_clamped=report['tail_samples']>44100
                self.packets=EventPackets(instrument["part"])
            if worker:
                if not plugin and not instrument and not instruments:raise ValueError("native worker requires plugin")
            if plugin:
                from plugins import resolve_state
                class_id=resolve_state(plugin,state,class_id)
                environment=dict(os.environ)
                environment['ARRANGER_STREAM_OUTPUT_BUS']=str(effect_output_bus)
                environment['ARRANGER_STREAM_READY']='1'
                environment.pop("ARRANGER_TEMPO",None)
                environment.pop("ARRANGER_STREAM_EVENTS",None)
                if bpm is not None:environment["ARRANGER_TEMPO"]=str(bpm)
                command=[str(worker),str(plugin),"-","-",str(state) if state else "-","-"]
                if class_id:command.extend(("-","-",class_id))
                dsp = popen(command,
                                       stdin=upstream or subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,env=environment,
                                       creationflags=subprocess.CREATE_NO_WINDOW,max_job_bytes=plugin_memory_bytes())
                self.processes.append(dsp)
                report=self._startup(dsp);self.effect_latency=report['latency_samples'];self.effect_tail=min(report['tail_samples'],44100);self.tail_clamped=self.tail_clamped or report['tail_samples']>44100
                if upstream:upstream.close()
                else:self.input = dsp.stdin
                upstream = dsp.stdout
            player = popen([str(sink)], stdin=upstream or subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            self.processes.append(player)
            if upstream:
                upstream.close()
            else:
                self.input = player.stdin
            self.player = player
            self.last_progress=time.monotonic()
            self.reader = threading.Thread(target=self._acknowledge, daemon=True)
            self.reader.start()
            self.watchdog_stop = threading.Event()
            self.watchdog = threading.Thread(target=self._watch, daemon=True)
            self.watchdog.start()
        except Exception:
            self.close()
            raise

    def _startup(self,process):
        ready=queue.Queue(maxsize=1)
        def diagnostics():
            try:
                ready.put_nowait(process.stderr.readline(4097))
                while process.stderr.read(4096):pass
            except (OSError,ValueError):pass
        thread=threading.Thread(target=diagnostics,daemon=True);thread.start();self.diagnostic_threads.append(thread)
        deadline=time.monotonic()+30
        try:
            while True:
                if self.cancel_event is not None and self.cancel_event.is_set():raise InterruptedError('plugin streaming startup canceled')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('plugin streaming startup exceeded30 seconds')
                try:report=json.loads(ready.get(timeout=min(.1,remaining)));break
                except queue.Empty:continue
        except (ValueError,UnicodeError):raise ValueError('plugin returned no bounded streaming handshake')
        if (not isinstance(report,dict) or report.get('ready') is not True or type(report.get('latency_samples')) is not int or not 0<=report['latency_samples']<=88200
                or type(report.get('tail_samples')) is not int or not 0<=report['tail_samples']<=2**32-1):raise ValueError('plugin streaming latency/tail exceeds supported bounds')
        return report

    def _watch(self):
        while not self.watchdog_stop.wait(0.05):
            canceled = self.active_stop is not None and self.active_stop.is_set() or self.cancel_event is not None and self.cancel_event.is_set()
            stalled = (self.active_stop is not None or self.frames_sent > self.frames_heard) and time.monotonic() - self.last_progress > 15
            if canceled:
                for process in self.processes:
                    if process.poll() is None:
                        process.kill()
                return
            if getattr(self, "draining", False):
                continue
            underrun=(self.frames_sent>0 and self.frames_heard>=self.frames_sent and time.monotonic()-self.last_feed>.35 and time.monotonic()-self.last_progress>.25)
            disconnected=any(process.poll() is not None for process in self.processes)
            if stalled or underrun or disconnected:
                error=TimeoutError('audio buffer underrun; playback stopped instead of resuming across a gap') if underrun else TimeoutError('audio device/plugin stopped acknowledging output') if stalled else ConnectionError('audio device or plugin worker disconnected')
                self.failure=error
                for process in self.processes:
                    if process.poll() is None:
                        process.kill()
                if self.on_failure:self.on_failure(error)
                with self.condition:self.closed=True;self.condition.notify_all()
                return

    def _acknowledge(self):
        try:
            for line in self.player.stdout:
                with self.condition:
                    self.frames_heard = int(line)
                    self.last_progress = time.monotonic()
                    self.condition.notify_all()
                if self.on_progress and time.monotonic()-self.last_event>=1:
                    self.last_event=time.monotonic()
                    self.on_progress({"frames_submitted":self.frames_sent,"frames_acknowledged":self.frames_heard})
        finally:
            with self.condition:
                self.closed = True
                self.condition.notify_all()

    def consume(self, path, stop,score=None):
        if self.failure:raise self.failure
        if self.closed:raise ConnectionError('audio stream is already closed; start a new disposable session')
        self.active_stop = stop
        with wave.open(str(path)) as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (44100, 2, 2):
                raise ValueError("device requires stereo 44.1 kHz PCM16 chunks")
            frames = audio.getnframes()
            if self.packets:
                if score is None:raise ValueError("instrument stream requires its accepted score")
                self.packets.add_score(score,frames)
            if self.ensemble:
                if score is None:raise ValueError("instrument ensemble requires its accepted score")
                self.ensemble.add_score(score,frames)
            while not stop.is_set():
                data = audio.readframes(4096)
                if not data:
                    break
                integers = array("h", data)
                floats = array("f", (value / 32768 for value in integers))
                data=floats.tobytes()
                if self.packets:
                    for offset in range(0,len(data),512*8):self.input.write(self.packets.encode(data[offset:offset+512*8]))
                else:self.input.write(data)
                self.frames_sent+=len(data)//8;self.last_feed=time.monotonic()
            self.input.flush()
        deadline = time.monotonic() + frames / 44100 + 10
        with self.condition:
            while self.frames_heard < max(0, self.frames_sent - 8820) and not stop.is_set():
                if self.closed or any(process.poll() is not None for process in self.processes):
                    raise self.failure or ConnectionError("audio device or plugin worker disconnected")
                if time.monotonic() > deadline:
                    raise TimeoutError("audio device did not acknowledge consumption")
                self.condition.wait(0.05)
        self.active_stop = None

    def drain(self):
        self.active_stop = None
        self.draining = True
        remaining=self.effect_latency+self.effect_tail
        if self.ensemble:remaining+=self.ensemble.latency+self.ensemble.tail+512
        elif self.packets:remaining+=self.instrument_latency+self.instrument_tail+512
        while remaining:
            frames=min(512,remaining);audio=bytes(frames*8)
            self.input.write(self.packets.encode(audio) if self.packets else audio);remaining-=frames;self.frames_sent+=frames
        self.input.flush()
        if self.ensemble:self.ensemble.finish_input()
        else:self.input.close()
        deadline = time.monotonic() + 10
        with self.condition:
            while self.frames_heard < self.frames_sent:
                if self.closed or time.monotonic() > deadline:
                    raise TimeoutError("device drain failed")
                self.condition.wait(0.05)
        # Completion acknowledgments can precede endpoint presentation. Let the
        # native sink finish its bounded presentation wait before close kills it.
        for process in self.processes:
            if process.wait(timeout=10):
                raise ConnectionError("audio process failed during final drain")

    def processing_policy(self):
        synth_latency=self.ensemble.latency if self.ensemble else self.instrument_latency
        synth_tail=self.ensemble.tail if self.ensemble else self.instrument_tail
        return {'latency_samples':synth_latency+self.effect_latency,'effect_latency_samples':self.effect_latency,
                'instrument_tail_frames':synth_tail,'effect_tail_frames':self.effect_tail,'tail_cap_per_stage_frames':44100,
                'tail_clamped':self.tail_clamped or bool(self.ensemble and self.ensemble.tail_clamped),
                'completion_padding_frames':synth_latency+synth_tail+self.effect_latency+self.effect_tail+(512 if self.packets or self.ensemble else 0),
                'cancellation':'immediate owned process stop; completion padding only on natural completion'}

    def close(self):
        if hasattr(self, "watchdog_stop"):
            self.watchdog_stop.set()
        for process in reversed(self.processes):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        for process in self.processes:
            for stream in (process.stdin, process.stdout,process.stderr):
                if stream:
                    stream.close()
        if self.ensemble:self.ensemble.close()
        for thread in self.diagnostic_threads:thread.join(timeout=1)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

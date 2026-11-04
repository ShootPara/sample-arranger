import os
import subprocess
import tempfile
import unittest
import sys
from array import array
from pathlib import Path

BUILD = Path(os.environ["LOCALAPPDATA"], "SampleArranger/tools/arranger-native")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))


@unittest.skipUnless((BUILD / "arranger-vst3.exe").exists(), "native build required")
class StreamTests(unittest.TestCase):
    def test_stream_multi_output_selection_never_creates_auxiliary_audio_files(self):
        import json
        signal=array('f',[0])*2048;signal[200]=signal[201]=.5
        command=[str(BUILD/'arranger-vst3.exe'),str(BUILD/'arranger-delay-fixture.vst3'),'-','-','-','-','-','-','6623100414424231A562100212142801']
        with tempfile.TemporaryDirectory() as directory:
            results=[]
            for bus in (0,1):
                child=subprocess.run(command,input=signal.tobytes(),capture_output=True,cwd=directory,env=dict(os.environ,ARRANGER_STREAM_OUTPUT_BUS=str(bus)),timeout=10)
                self.assertEqual(child.returncode,0,child.stderr);self.assertEqual(len(child.stdout),len(signal)*4)
                self.assertEqual(json.loads(child.stderr)['stream_output_bus'],bus)
                values=array('f');values.frombytes(child.stdout);results.append(values)
                self.assertEqual(list(Path(directory).iterdir()),[],'disposable processing must not create -.bus1 or any state/audio file')
            self.assertEqual(results[0][228*2],.5);self.assertEqual(results[1][228*2],.5)
            self.assertEqual(results[0][356*2],.25);self.assertEqual(results[1][356*2],0,'selected secondary bus must be genuine independent signal')
            child=subprocess.run(command,input=signal.tobytes(),capture_output=True,cwd=directory,env=dict(os.environ,ARRANGER_STREAM_OUTPUT_BUS='2'),timeout=10)
            self.assertNotEqual(child.returncode,0);self.assertEqual(list(Path(directory).iterdir()),[])
    def test_actual_plugin_abort_is_contained_in_persistent_ensemble(self):
        from unittest.mock import patch
        from ensemble_stream import EnsembleStream
        from music import compile_intent
        plugin=str(BUILD/'arranger-delay-fixture.vst3')
        instruments={part:{'plugin':plugin,'class_id':'6623100314424231A562100212142801'} for part in ('chords','bass')}
        with patch.dict(os.environ,{'ARRANGER_FIXTURE_CRASH':'1'}):
            ensemble=EnsembleStream(BUILD/'arranger-vst3.exe',instruments,120)
        try:
            ensemble.add_score(compile_intent({'seconds':0.1}),4410)
            ensemble.write(bytes(512*8));ensemble.flush()
            self.assertNotEqual(ensemble.processes[0].wait(timeout=10),0,'fixture must actually abort in plugin process')
            ensemble.processes[1].wait(timeout=10)
            self.assertEqual(ensemble.output.read(),b'')
        finally:ensemble.close()
        self.assertTrue(all(process.poll() is not None for process in ensemble.processes))

    def test_three_persistent_parts_align_latency_and_boundary_note_ids(self):
        self.check_ensemble((1,1,1))

    def test_individual_instrument_route_gains_leave_dry_bed_unchanged(self):
        self.check_ensemble((0,0.5,1))

    def check_ensemble(self,gains):
        import threading
        from ensemble_stream import EnsembleStream
        from music import compile_intent
        plugin=str(BUILD/'arranger-delay-fixture.vst3')
        instruments={part:{'plugin':plugin,'class_id':'6623100314424231A562100212142801','outputs':[{'bus':0,'gain':gain}]} for part,gain in zip(('bass','chords','melody'),gains)}
        score=compile_intent({'seconds':0.5,'bpm':120})
        score['notes']=[{'part':part,'tick':0,'length':960,'pitch':pitch,'velocity':100}
                        for part,pitch in (('bass',48),('chords',60),('melody',72))]
        ensemble=EnsembleStream(BUILD/'arranger-vst3.exe',instruments,120)
        output=[]
        reader=threading.Thread(target=lambda:output.append(ensemble.output.read()),daemon=True);reader.start()
        try:
            identities=[process.pid for process in ensemble.processes]
            self.assertEqual(ensemble.latency,384)
            signal=array('f',[0.1])*(22050*2)
            for _ in range(2):
                ensemble.add_score(score,22050);ensemble.write(signal.tobytes());ensemble.flush()
                self.assertEqual([process.pid for process in ensemble.processes],identities)
            ensemble.write(bytes((ensemble.latency+512)*8));ensemble.flush();ensemble.finish_input()
            reader.join(timeout=10);self.assertFalse(reader.is_alive())
            for process in ensemble.processes:self.assertEqual(process.wait(timeout=5),0)
            self.assertEqual(ensemble.errors,[])
            values=array('f');values.frombytes(output[0])
            self.assertEqual(len(values)//2,44100+384+512)
            self.assertTrue(all(value==0 for value in values[:384*2]))
            self.assertAlmostEqual(values[384*2],0.1+0.25*sum(gains),places=5)
            self.assertAlmostEqual(values[512*2],0.1+0.375*sum(gains),places=5)
            for frame in range(22050+380,22050+390):
                self.assertAlmostEqual(values[frame*2],0.1+0.375*sum(gains),places=5)
        finally:ensemble.close();reader.join(timeout=1)

    def test_instrument_packets_hold_voice_and_mix_aligned_dry_across_packets(self):
        import struct
        from event_stream import EventPackets
        packets=EventPackets("chords")
        # A held note crosses two packet boundaries. Dry impulse shares PDC.
        packets.events=[(100,1,60,100,1),(1100,0,60,0,1)]
        signal=array("f",[0])*4096;signal[100*2]=signal[100*2+1]=0.5
        payload=b"".join(packets.encode(signal[offset*2:(offset+512)*2].tobytes()) for offset in range(0,2048,512))
        environment=dict(os.environ,ARRANGER_STREAM_EVENTS="1",ARRANGER_TEMPO="137.25")
        command=[str(BUILD/"arranger-vst3.exe"),str(BUILD/"arranger-delay-fixture.vst3"),"-","-","-","-","-","-","6623100314424231A562100212142801"]
        result=subprocess.run(command,input=payload,capture_output=True,env=environment,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        values=array("f");values.frombytes(result.stdout)
        self.assertEqual(len(values),len(signal))
        self.assertEqual(values[228*2],0.75)
        self.assertEqual(values[700*2],0.375) # held voice plus its delayed echo
        self.assertEqual(values[1228*2],0.125) # matching note-off, remaining echo
        self.assertEqual(values[1356*2],0)
        mono_command=command[:-1]+['6623100614424231A562100212142801']
        mono=subprocess.run(mono_command,input=payload,capture_output=True,env=environment,timeout=10)
        self.assertEqual(mono.returncode,0,mono.stderr)
        self.assertEqual(mono.stdout,result.stdout,'mono instrument must duplicate correctly before aligned dry mixing')
        malformed=struct.pack("<III",0x31565241,513,0)
        result=subprocess.run(command,input=malformed,capture_output=True,env=environment,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b"bounded event packet header",result.stderr)

    def test_persistent_dsp_across_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            signal = array("f", [0.0]) * 2048
            signal[510 * 2] = signal[510 * 2 + 1] = 0.5
            command = [str(BUILD / "arranger-vst3.exe"), str(BUILD / "arranger-delay-fixture.vst3"),
                       "-", "-", "-", "-"]
            with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE) as worker:
                worker.stdin.write(signal[:1024].tobytes())
                worker.stdin.flush()
                output, report = worker.communicate(signal[1024:].tobytes(), timeout=10)
                self.assertEqual(worker.returncode, 0, report)
            samples = array("f")
            samples.frombytes(output)
            self.assertEqual(len(samples), len(signal))
            self.assertEqual(samples[638 * 2], 0.5)
            self.assertEqual(samples[766 * 2], 0.25)
            self.assertEqual(sum(value != 0 for value in samples), 4)

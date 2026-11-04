"""Pre-device sink fixture: exact completion signal/tails; no hardware capture."""
from array import array
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from device import DeviceStream
from process_group import popen

BUILD=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')


@unittest.skipUnless((BUILD/'arranger-vst3.exe').is_file(),'pinned native worker required')
class DeviceStreamTests(unittest.TestCase):
    def test_delayed_generation_reports_underflow_and_clears_owned_chunks_without_resuming(self):
        self.check_failed_transport(False)

    def test_actual_sink_process_disconnect_cancels_waiting_generator_and_cleans_chunks(self):
        self.check_failed_transport(True)

    def check_failed_transport(self,disconnect):
        from session import ContinuousSession
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            program='''import sys
total=0
while True:
    block=sys.stdin.buffer.read(4096)
    if not block:break
    if sys.argv[1]=='disconnect':sys.exit(7)
    total+=len(block)//8;print(total,flush=True)
'''
            def launch(command,**kwargs):return popen([sys.executable,'-u','-c',program,'disconnect' if disconnect else 'acknowledge'],**kwargs)
            def generate(index,path,stop):
                if index:stop.wait(5);return
                with wave.open(str(path),'wb') as output:output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(bytes(1024*4))
            session=ContinuousSession(root,generate,None,wait_seconds=5)
            with patch('device.popen',side_effect=launch):
                device=DeviceStream('fixture-sink',on_failure=session.fail)
                try:
                    session.consume=device.consume;started=time.monotonic()
                    with self.assertRaisesRegex(ConnectionError if disconnect else TimeoutError,'disconnected' if disconnect else 'underrun'):session.run(2)
                    self.assertLess(time.monotonic()-started,2,'transport failure must interrupt the5s generator wait')
                    self.assertEqual(list(root.glob('chunk-*.wav')),[]);self.assertIsNotNone(device.failure)
                    with self.assertRaises(type(device.failure)):device.consume(root/'not-read.wav',threading.Event())
                finally:device.close()
                self.assertTrue(all(child.poll() is not None for child in device.processes))

    def test_initial_cancellation_creates_no_audio_process(self):
        canceled=threading.Event();canceled.set()
        with patch('device.popen') as launch:
            with self.assertRaisesRegex(InterruptedError,'before creating'):DeviceStream('not-started',cancel_event=canceled)
            launch.assert_not_called()
    def test_effect_handshake_and_bounded_completion_preserve_last_impulse_and_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'known.wav';signal=array('h',[0])*2048;signal[-2]=signal[-1]=16384
            with wave.open(str(source),'wb') as output:output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(signal.tobytes())
            # Test-only sink records generated known PCM before any device. The app
            # sink has no recording option. This file is removed with this fixture.
            capture=root/'pre-device.f32'
            program='''import sys
total=0
with open(sys.argv[1],'wb') as output:
    while True:
        block=sys.stdin.buffer.read(4096)
        if not block:break
        output.write(block);total+=len(block)//8;print(total,flush=True)
'''
            def launch(command,**kwargs):return popen([sys.executable,'-u','-c',program,str(capture)] if command==['known-sink'] else command,**kwargs)
            with patch('device.popen',side_effect=launch):
                device=DeviceStream('known-sink',BUILD/'arranger-vst3.exe',BUILD/'arranger-delay-fixture.vst3',class_id='6623100114424231A562100212142801')
                try:
                    self.assertEqual((device.effect_latency,device.effect_tail),(128,256));device.consume(source,threading.Event());device.drain()
                    self.assertEqual(device.processing_policy()['completion_padding_frames'],384);self.assertFalse(device.processing_policy()['tail_clamped'])
                    self.assertEqual(device.frames_sent,1024+128+256);self.assertEqual(device.frames_heard,device.frames_sent)
                    samples=array('f');samples.frombytes(capture.read_bytes());self.assertEqual(len(samples)//2,1408)
                    self.assertEqual(samples[(1023+128)*2],.5);self.assertEqual(samples[(1023+256)*2],.25)
                finally:device.close()
                self.assertTrue(all(process.poll() is not None for process in device.processes))
            self.assertEqual(sorted(p.name for p in root.iterdir()),['known.wav','pre-device.f32'])

    def test_unsupported_selected_effect_bus_fails_before_player_and_cleans_worker(self):
        children=[]
        def launch(*args,**kwargs):
            child=popen(*args,**kwargs);children.append(child);return child
        with patch('device.popen',side_effect=launch):
            with self.assertRaisesRegex(ValueError,'handshake'):
                DeviceStream('unused-player',BUILD/'arranger-vst3.exe',BUILD/'arranger-delay-fixture.vst3',class_id='6623100114424231A562100212142801',effect_output_bus=1)
        self.assertEqual(len(children),1);self.assertTrue(all(child.poll() is not None for child in children))


if __name__=='__main__':unittest.main()

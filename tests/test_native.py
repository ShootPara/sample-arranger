import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vst3_render import render_plugin
from plugins import edit

BUILD = Path(os.environ.get("ARRANGER_NATIVE_BUILD",
             str(Path(os.environ["LOCALAPPDATA"], "SampleArranger/tools/arranger-native"))))


@unittest.skipUnless((BUILD / "arranger-delay-fixture.vst3").exists(), "build native fixture first")
class NativeFixtureTests(unittest.TestCase):
    def test_fixed_mono_effect_negotiation_downmix_and_dual_mono_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'stereo.f32'
            values=array('f',[0])*2048;values[200]=0.5;values[201]=0.1;source.write_bytes(values.tobytes())
            result=render_plugin(BUILD/'arranger-vst3.exe',BUILD/'arranger-delay-fixture.vst3',source,root,
                                 class_id='6623100514424231A562100212142801')
            self.assertEqual(result['input_channels'],[1]);self.assertEqual(result['output_channels'],[1])
            audio=array('f');audio.frombytes(Path(result['audio']).read_bytes())
            self.assertAlmostEqual(audio[228*2],0.3);self.assertEqual(audio[228*2],audio[228*2+1])
            self.assertAlmostEqual(audio[356*2],0.15)

    def test_overlapping_notes_release_only_their_own_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"silence.f32";source.write_bytes(bytes(4096*8))
            notes=root/"notes.txt";notes.write_text("50 100 60 100\n75 125 64 100\n",encoding="utf-8")
            result=render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",source,root,notes=notes)
            values=array("f");values.frombytes(Path(result["audio"]).read_bytes())
            values=values[128*2:]
            self.assertEqual(values[50*2],0.25);self.assertEqual(values[75*2],0.5)
            self.assertEqual(values[100*2],0.25);self.assertEqual(values[125*2],0)
    def test_sidechain_and_independent_output_bus_signals(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            main=root/"main.f32";side=root/"side.f32"
            signal=array("f",[0])*2048
            signal[100*2]=signal[100*2+1]=0.5
            main.write_bytes(signal.tobytes())
            signal=array("f",[0])*2048
            signal[200*2]=signal[200*2+1]=0.8
            side.write_bytes(signal.tobytes())
            result=render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",main,root,
                                 sidechain=side,class_id="6623100414424231A562100212142801")
            self.assertEqual(result["output_buses"],2)
            self.assertTrue(result["sidechain_active"])
            first=array("f");first.frombytes(Path(result["buses"][0]).read_bytes())
            second=array("f");second.frombytes(Path(result["buses"][1]).read_bytes())
            self.assertEqual(first[228*2],0.5)
            self.assertAlmostEqual(first[328*2],0.2)
            self.assertEqual(first[356*2],0.25)
            self.assertEqual(second[228*2],0.5)
            self.assertAlmostEqual(second[328*2],-0.8)
            self.assertEqual(second[356*2],0)
            side.write_bytes(bytes(16))
            with self.assertRaisesRegex(ValueError,"frame count differs"):
                render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",main,root,
                              sidechain=side,class_id="6623100414424231A562100212142801")
    def test_preset_wrapper_applies_pending_parameters_and_publishes_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.dict(os.environ,{"ARRANGER_FIXTURE_EDITOR_AUTOCLOSE":"1"}):
                result=edit(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",
                            "6623100114424231A562100212142801",root,parameters={"1":0})
            # The editor sees the pending mute and its Restore button returns gain to1.
            self.assertEqual(result["parameter_values"]["1"],1)
            self.assertEqual(len(result["plugin_sha256"]),64)
            self.assertEqual(len(list(root.iterdir())),1)
            self.assertTrue((Path(result["preset"])/"manifest.json").exists())
    def test_explicit_transport_tempo_and_monotonic_sample_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/"source.f32"
            source.write_bytes(bytes(8192))
            with patch.dict(os.environ,{"ARRANGER_FIXTURE_CHECK_CONTEXT":"1"}):
                result=render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",source,root,tempo=137)
                self.assertEqual(result["tempo_bpm"],137)
                with self.assertRaisesRegex(ValueError,"process failed"):
                    render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",source,root)
    def test_native_editor_commits_processor_and_controller(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            saved=root/"edited-state.bin"
            command=[str(BUILD/"arranger-vst3.exe"),"--editor",str(BUILD/"arranger-delay-fixture.vst3"),
                     "6623100114424231A562100212142801","-",str(saved)]
            process=subprocess.run(command,capture_output=True,text=True,timeout=10,
                                   env=dict(os.environ,ARRANGER_FIXTURE_EDITOR_AUTOCLOSE="1"))
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertTrue(saved.is_file())
            self.assertTrue(Path(str(saved)+".controller").is_file())
            source=root/"input.f32"
            source.write_bytes(array("f",[0.5])*2048)
            result=render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",
                                 source,root,state=saved)
            self.assertFalse(any(Path(result["audio"]).read_bytes()))

    def test_parameter_automation_offsets_and_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.f32"
            source.write_bytes(array("f",[0.5])*2048)
            changes = root / "automation.txt"
            changes.write_text("0 1 0.5\n256 1 0\n",encoding="utf-8")
            result = render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",
                                   source,root,automation=changes)
            audio=array("f")
            audio.frombytes(Path(result["audio"]).read_bytes())
            self.assertEqual(audio[128*2],0.25)
            self.assertEqual(audio[255*2],0.25)
            self.assertEqual(audio[383*2],0.375)
            self.assertEqual(audio[384*2],0.125)
            self.assertEqual(audio[512*2],0)
            self.assertEqual(result["automation_points"],2)
            self.assertEqual(result["class_id"],"6623100114424231A562100212142801")
            restored=render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",
                                   source,root,state=Path(result["state"]))
            self.assertFalse(any(Path(restored["audio"]).read_bytes()))
            changes.write_text("0 9999 0.5\n",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"unknown or read-only"):
                render_plugin(BUILD/"arranger-vst3.exe",BUILD/"arranger-delay-fixture.vst3",
                              source,root,automation=changes)
    def test_delayed_instrument_note_off_and_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "silence.f32"
            source.write_bytes(bytes(4096 * 8))
            notes = root / "notes.txt"
            notes.write_text("50 100 60 100\n", encoding="utf-8")
            result = render_plugin(BUILD / "arranger-vst3.exe",
                                   BUILD / "arranger-delay-fixture.vst3", source, root, notes=notes)
            raw = array("f")
            raw.frombytes(Path(result["audio"]).read_bytes())
            aligned = raw[result["latency_samples"] * 2:]
            self.assertEqual(aligned[49 * 2], 0)
            self.assertEqual(aligned[50 * 2], 0.25)
            self.assertEqual(aligned[100 * 2], 0)
            self.assertEqual(aligned[(50 + 128) * 2], 0.125)
            self.assertEqual(aligned[(100 + 128) * 2], 0)

    def test_delay_echo_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            signal = array("f", [0.0]) * 2048
            signal[200] = signal[201] = 0.5
            source = root / "input.f32"
            source.write_bytes(signal.tobytes())
            args = (BUILD / "arranger-vst3.exe", BUILD / "arranger-delay-fixture.vst3", source, root)
            first = render_plugin(*args)
            output = array("f")
            output.frombytes(Path(first["audio"]).read_bytes())
            self.assertEqual(first["latency_samples"], 128)
            self.assertEqual(first["tail_samples"], 256)
            self.assertEqual(output[228 * 2], 0.5)
            self.assertEqual(output[356 * 2], 0.25)
            self.assertEqual(sum(value != 0 for value in output), 4)
            second = render_plugin(*args, state=Path(first["state"]))
            self.assertFalse(first["component_state_restored"])
            self.assertTrue(second["component_state_restored"])
            self.assertTrue(second["controller_state_restored"])
            self.assertTrue(second["controller_component_synced"])
            self.assertEqual(Path(first["audio"]).read_bytes(), Path(second["audio"]).read_bytes())

    def test_actual_plugin_abort_is_contained(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.f32"
            source.write_bytes(bytes(8192))
            command = [str(BUILD / "arranger-vst3.exe"), str(BUILD / "arranger-delay-fixture.vst3"),
                       str(source), str(root / "output"), "-", str(root / "state")]
            result = subprocess.run(command, capture_output=True, timeout=10,
                                    env=dict(os.environ, ARRANGER_FIXTURE_CRASH="1"))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "state").exists())

    def test_plugin_abort_does_not_publish_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.f32"
            source.write_bytes(bytes(8192))
            with patch.dict(os.environ, {"ARRANGER_FIXTURE_CRASH": "1"}):
                with self.assertRaisesRegex(ValueError, "worker failed"):
                    render_plugin(BUILD / "arranger-vst3.exe",
                                  BUILD / "arranger-delay-fixture.vst3", source, root)
            self.assertEqual(list(root.iterdir()), [source])

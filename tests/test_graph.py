from array import array
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from graph import process_graph,validate_graph
from commands import execute

BUILD=Path(os.environ["LOCALAPPDATA"],"SampleArranger/tools/arranger-native")
PLUGIN=str(BUILD/"arranger-delay-fixture.vst3")
DELAY="6623100114424231A562100212142801"
ROUTED="6623100414424231A562100212142801"


@unittest.skipUnless((BUILD/"arranger-vst3.exe").exists(),"native build needed")
class GraphTests(unittest.TestCase):
    def test_finite_inputs_that_overflow_float32_mix_fail_before_encoding(self):
        from graph import mix_buses
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'large.f32';source.write_bytes(array('f',[2.5e38]*32).tobytes())
            with self.assertRaisesRegex(ValueError,'float32 finite range'):
                mix_buses([(source,4)],root/'mixed.f32',16)
            self.assertEqual((root/'mixed.f32').stat().st_size,0)
            mix_buses([(source,4),(source,-4)],root/'canceled.f32',16)
            self.assertEqual((root/'canceled.f32').read_bytes(),bytes(128))
    def test_shared_graph_request_publishes_mp3_and_actual_states(self):
        import numpy as np
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/"signal.f32"
            # Keep the alignment probe outside the product's5ms music edge fade.
            # Raw native/graph tests separately assert exact impulses at sample100.
            audio=np.zeros((44100,2),dtype="<f4");audio[1000]=0.5
            source.write_bytes(audio.tobytes())
            jobs=root/"jobs";jobs.mkdir()
            graph={"nodes":[{"id":"effect","plugin":PLUGIN,"class_id":DELAY,
                              "input":{"node":"music","bus":0}}],"outputs":[{"node":"effect","bus":0}]}
            result=execute({"contract":1,"operation":"graph.render","arguments":{
                "graph":graph,"sources":{"music":{"file":str(source)}},"worker":str(BUILD/"arranger-vst3.exe"),
                "seconds":1,"jobs":str(jobs),"tempo":137}})["result"]
            output=Path(result["audio"])
            decoded=subprocess.run(["ffmpeg","-v","error","-i",str(output),"-f","f32le","-"],
                                   capture_output=True,check=True,timeout=10).stdout
            values=np.frombuffer(decoded,dtype="<f4").reshape(-1,2)
            self.assertEqual(len(values),44100)
            self.assertLessEqual(abs(int(np.argmax(np.abs(values[:,0])))-1000),32)
            self.assertGreater(float(np.max(np.abs(values))),0.1)
            self.assertEqual(len(result["attachments"]),2)
            self.assertTrue(all((output.parent/item["file"]).is_file() for item in result["attachments"]))
            self.assertEqual(len(list(jobs.iterdir())),1,"no intermediate graph job published")
    def test_serial_pdc_and_sidechain_multioutput_mix(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            main=root/"main.f32";side=root/"side.f32"
            signal=array("f",[0])*4096
            signal[200]=signal[201]=0.5;main.write_bytes(signal.tobytes())
            signal=array("f",[0])*4096
            signal[400]=signal[401]=0.8;side.write_bytes(signal.tobytes())
            # Deliberately unordered nodes: validation topologically sorts them.
            serial={"nodes":[{"id":"second","plugin":PLUGIN,"class_id":DELAY,"input":{"node":"first","bus":0}},
                              {"id":"first","plugin":PLUGIN,"class_id":DELAY,"input":{"node":"music","bus":0}}],
                    "outputs":[{"node":"second","bus":0}]}
            result=process_graph(serial,{"music":main},BUILD/"arranger-vst3.exe",root,tempo=137)
            audio=array("f");audio.frombytes(result["audio"].read_bytes())
            self.assertEqual(audio[100*2],0.5)
            self.assertEqual(audio[228*2],0.5)
            self.assertEqual(audio[356*2],0.125)
            self.assertEqual([node["latency_samples"] for node in result["nodes"]],[128,128])
            routed={"nodes":[{"id":"router","plugin":PLUGIN,"class_id":ROUTED,
                              "input":{"node":"music","bus":0},"sidechain":{"node":"key","bus":0}}],
                    "outputs":[{"node":"router","bus":0,"gain":0.5},{"node":"router","bus":1,"gain":0.5}]}
            result=process_graph(routed,{"music":main,"key":side},BUILD/"arranger-vst3.exe",root,tempo=137)
            audio=array("f");audio.frombytes(result["audio"].read_bytes())
            self.assertEqual(audio[100*2],0.5)
            self.assertAlmostEqual(audio[200*2],-0.3)
            self.assertEqual(audio[228*2],0.125)
            self.assertTrue(all(path.exists() for _,path in result["attachments"]))
            with self.assertRaisesRegex(ValueError,"storage budget"):
                process_graph(routed,{"music":main,"key":side},BUILD/"arranger-vst3.exe",root,max_work_bytes=1)

    def test_feedback_unknown_windows_collision_and_invalid_gain(self):
        graph={"nodes":[{"id":"first","plugin":PLUGIN,"class_id":DELAY,"input":{"node":"first","bus":0}}],
               "outputs":[{"node":"first","bus":0}]}
        with self.assertRaisesRegex(ValueError,"feedback"):
            validate_graph(graph,{"music":Path("source")})
        graph["nodes"][0]["input"]["node"]="music"
        graph["outputs"][0]["gain"]=float("nan")
        with self.assertRaisesRegex(ValueError,"gain"):
            validate_graph(graph,{"music":Path("source")})

    def test_internal_mixer_routes_to_a_compensated_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"source.f32"
            values=array("f",[0])*4096;values[200]=values[201]=0.5;source.write_bytes(values.tobytes())
            graph={"nodes":[{"id":"bus","mix":[{"node":"music","bus":0,"gain":0.5}]},
                            {"id":"effect","plugin":PLUGIN,"class_id":DELAY,"input":{"node":"bus","bus":0}}],
                   "outputs":[{"node":"effect","bus":0}]}
            result=process_graph(graph,{"music":source},BUILD/"arranger-vst3.exe",root)
            output=array("f");output.frombytes(result["audio"].read_bytes())
            self.assertEqual(output[200],0.25)
            self.assertEqual(output[(100+128)*2],0.125)

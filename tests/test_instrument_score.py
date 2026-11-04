import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from compose import compose
from commands import execute

BUILD=Path(os.environ["LOCALAPPDATA"],"SampleArranger/tools/arranger-native")


@unittest.skipUnless((BUILD/"arranger-vst3.exe").exists(),"native build needed")
class AssignedInstrumentTests(unittest.TestCase):
    def test_hybrid_project_combines_real_sample_pcm_and_accepted_score(self):
        import numpy as np
        import sqlite3
        import wave
        from project import save
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jobs=root/"jobs";jobs.mkdir()
            source=root/"tone.wav";times=np.arange(44100)/44100
            tone=0.25*np.sin(2*np.pi*997*times)
            with wave.open(str(source),"wb") as output:
                output.setparams((2,2,44100,0,"NONE","not compressed"))
                output.writeframes(np.repeat((tone*32767).astype('<i2'),2).tobytes())
            database=root/"catalog.sqlite"
            with sqlite3.connect(database) as db:
                db.execute("CREATE TABLE sample(path TEXT,name TEXT)")
                db.execute("INSERT INTO sample VALUES (?,?)",(str(source),source.name))
            db.close()
            score=compile_intent({"seconds":1,"bpm":120})
            project=root/"hybrid.json"
            saved=save(project,[{"sample":source.name,"seconds":1}],database,score=score)
            self.assertEqual(saved["schema"],4)
            result=execute({"contract":1,"operation":"project.render","arguments":{"project":str(project),"jobs":str(jobs)}})["result"]
            self.assertEqual(result["composition"]["score"],score)
            self.assertEqual({item["role"] for item in result["sources"]},{"sample","composed_layer"})
            data=subprocess.run(["ffmpeg","-v","error","-i",result["audio"],"-f","f32le","-"],capture_output=True,check=True,timeout=10).stdout
            audio=np.frombuffer(data,dtype='<f4').reshape(-1,2)[:,0]
            self.assertEqual(len(audio),44100)
            projection=np.dot(audio,tone)/np.dot(tone,tone)
            self.assertGreater(projection,0.35)
            self.assertGreater(float(np.sqrt(np.mean((audio-projection*tone)**2))),0.005)
            self.assertEqual(len(list(jobs.iterdir())),1)

    def test_project_recall_preserves_assignments_and_blocks_changed_state(self):
        from project import save,inspect
        from music import compile_intent
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);jobs=root/"jobs";jobs.mkdir()
            state=root/"state.bin";state.write_bytes(bytes(4))
            controller=Path(str(state)+".controller");controller.write_bytes(bytes(4))
            assignment={"chords":{"plugin":str(BUILD/"arranger-delay-fixture.vst3"),
                                  "class_id":"6623100314424231A562100212142801"}}
            project=root/"project.json"
            score=__import__('music').compile_intent({"seconds":1,"bpm":137.25})
            from music import set_note_locks
            protected=next(index for index,note in enumerate(score['notes']) if note['part']=='chords')
            score=set_note_locks(score,[protected])
            saved=save(project,[],score=score,instruments=assignment,processing={"worker":str(BUILD/"arranger-vst3.exe")})
            self.assertEqual(saved["schema"],3)
            self.assertTrue(inspect(project)["ready"])
            result=execute({"contract":1,"operation":"project.render","arguments":{"project":str(project),"jobs":str(jobs)}})["result"]
            self.assertEqual(result["composition"]["project"]["instruments"],saved["instruments"])
            self.assertEqual(result['composition']['score']['note_locks'],score['note_locks'])
            assignment["chords"]["state"]=str(state)
            save(project,[],score=score,instruments=assignment,expected_revision=1)
            self.assertTrue(inspect(project)["ready"])
            controller.write_bytes(b"changed")
            self.assertEqual(inspect(project)["issues"][0]["issue"],"missing_or_changed_controller")
            with self.assertRaisesRegex(ValueError,"missing or changed"):
                execute({"contract":1,"operation":"project.render","arguments":{"project":str(project),"jobs":str(jobs)}})

    def test_score_part_uses_vst_instrument_with_pdc_and_saved_states(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            assignment={"chords":{"plugin":str(BUILD/"arranger-delay-fixture.vst3"),
                                   "class_id":"6623100314424231A562100212142801"}}
            result=compose({"seconds":2,"bpm":137.25},root,worker=BUILD/"arranger-vst3.exe",instruments=assignment)
            self.assertEqual(len(result["attachments"]),2)
            graph=result["composition"]["instrument_graph"]
            self.assertEqual(graph["nodes"][0]["latency_samples"],128)
            self.assertEqual(graph["nodes"][0]["class_id"],assignment["chords"]["class_id"])
            from plugins import resolve_state
            saved=Path(result["audio"]).parent/graph["nodes"][0]["state"]["state"]["file"]
            self.assertEqual(resolve_state(BUILD/"arranger-delay-fixture.vst3",saved),assignment["chords"]["class_id"])
            saved.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError,"checksum mismatch"):
                resolve_state(BUILD/"arranger-delay-fixture.vst3",saved)
            decoded=subprocess.run(["ffmpeg","-v","error","-i",result["audio"],"-f","f32le","-"],capture_output=True,check=True,timeout=10).stdout
            values=np.frombuffer(decoded,dtype="<f4")
            self.assertEqual(len(values),2*44100*2)
            self.assertGreater(float(np.max(np.abs(values))),0.1)
            self.assertEqual(len(list(root.iterdir())),1)

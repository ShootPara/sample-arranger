import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from project import save, inspect,pinned_sections


class ProjectTests(unittest.TestCase):
    def test_shared_atomic_note_edit_preserves_other_events_and_project_identity(self):
        from music import compile_intent
        from commands import execute
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'project.json';saved=save(path,[],score=compile_intent({'seconds':4,'form':'bed'}))
            changes=[{'action':'set','index':0,'field':'velocity','value':49}]
            request={'contract':1,'operation':'project.notes.edit','arguments':{'project':str(path),'expected_revision':1,'changes':changes}}
            result=execute(request)['result']['project']
            self.assertEqual(result['revision'],2);self.assertEqual(result['score']['notes'][0]['velocity'],49)
            self.assertEqual(result['score']['notes'][1:],saved['score']['notes'][1:])
            self.assertEqual(result['assets'],saved['assets']);self.assertEqual(result['processing'],saved['processing'])
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'revision conflict'):execute(request)
            invalid={**request,'arguments':{**request['arguments'],'expected_revision':2,'changes':[{'action':'set','index':0,'field':'velocity','value':200}]}}
            with self.assertRaises(ValueError):execute(invalid)
            self.assertEqual(path.read_bytes(),before)
    def test_save_and_new_snapshot_do_not_silently_repin_processing_updates(self):
        from music import compile_intent
        from project import processing_pins
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);plugin=root/'fixture.vst3';plugin.write_bytes(b'nonexecuted identity fixture')
            worker=root/'host.exe';worker.write_bytes(b'nonexecuted host identity fixture')
            state=root/'state.bin';state.write_bytes(b'state');controller=Path(str(state)+'.controller');controller.write_bytes(b'controller')
            score=compile_intent({'seconds':1});assignment={'chords':{'plugin':str(plugin),'class_id':'A'*32,'state':str(state)}}
            path=root/'project.json'
            saved=save(path,[],score=score,instruments=assignment,processing={'worker':str(worker)})
            pins=processing_pins(saved)
            controller.unlink()
            with self.assertRaisesRegex(ValueError,'controller state is missing'):
                save(root/'snapshot.json',[],score=score,instruments=assignment,expected_instruments=pins['instruments'])
            controller.write_bytes(b'controller')
            plugin.write_bytes(b'updated nonexecuted binary')
            with self.assertRaisesRegex(ValueError,'processing content changed'):
                save(path,[],score=score,instruments=assignment,expected_revision=1)
            with self.assertRaisesRegex(ValueError,'processing content changed'):
                save(root/'snapshot.json',[],score=score,instruments=assignment,expected_instruments=pins['instruments'])
            self.assertEqual(inspect(path)['project']['revision'],1)
            plugin.write_bytes(b'nonexecuted identity fixture');worker.write_bytes(b'updated host fixture')
            with self.assertRaisesRegex(ValueError,'processing content changed'):
                save(root/'snapshot.json',[],score=score,processing={'worker':str(worker)},expected_processing=pins['processing'])
            from commands import execute
            review=execute({'contract':1,'operation':'project.processing.review','arguments':{'project':str(path)}})['result']
            self.assertEqual([item['selector'] for item in review['changes']],['processing.worker'])
            arguments={'project':str(path),'updates':{'processing.worker':review['changes'][0]['current_sha256']},'expected_revision':1}
            worker.write_bytes(b'changed again after review')
            with self.assertRaisesRegex(ValueError,'no longer matches'):
                execute({'contract':1,'operation':'project.processing.adopt','arguments':arguments})
            worker.write_bytes(b'updated host fixture')
            adopted=execute({'contract':1,'operation':'project.processing.adopt','arguments':arguments})['result']
            self.assertTrue(adopted['ready']);self.assertEqual(adopted['project']['revision'],2)
            self.assertEqual(len(adopted['project']['processing_updates']),1)
            self.assertEqual(adopted['project']['score'],score)
            with self.assertRaisesRegex(ValueError,'revision conflict'):
                execute({'contract':1,'operation':'project.processing.adopt','arguments':arguments})

    def test_identical_relink_renders_without_catalog_and_rejects_changed_content(self):
        import wave
        from commands import execute
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'original.wav';jobs=root/'jobs';jobs.mkdir()
            with wave.open(str(source),'wb') as output:
                output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(bytes(4410*4))
            database=root/'catalog.sqlite'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE sample(path TEXT,name TEXT)');db.execute('INSERT INTO sample VALUES (?,?)',(str(source),source.name))
            db.close()
            path=root/'project.json';save(path,[{'sample':source.name,'seconds':0.2}],database)
            target=root/'moved-and-renamed.wav';source.rename(target);database.unlink()
            self.assertFalse(inspect(path)['ready'])
            wrong=root/'wrong.wav';wrong.write_bytes(b'wrong')
            request={'contract':1,'operation':'project.relink','arguments':{'project':str(path),'expected_revision':1,'replacements':{'0':str(wrong)}}}
            with self.assertRaisesRegex(ValueError,'match original'):execute(request)
            self.assertEqual(inspect(path)['project']['revision'],1)
            request['arguments']['replacements']['0']=str(target)
            report=execute(request)['result'];self.assertTrue(report['ready']);self.assertEqual(report['project']['schema'],5)
            project,sections=pinned_sections(path);self.assertEqual(sections[0][0],target)
            result=execute({'contract':1,'operation':'project.render','arguments':{'project':str(path),'jobs':str(jobs)}})['result']
            self.assertTrue(Path(result['audio']).is_file())
            with self.assertRaisesRegex(ValueError,'revision conflict'):execute(request)
            bindings={project['sections'][0]['sample']:project['assets'][0]}
            save(path,project['sections'],None,source_assets=bindings,expected_revision=2)
            target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'missing or changed'):
                save(path,project['sections'],None,source_assets=bindings,expected_revision=3)
    def test_score_project_preserves_accepted_notes(self):
        from music import compile_intent
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"score.json"
            score=compile_intent({"bpm":137,"seconds":7})
            score["notes"][0]["velocity"]=49
            save(path,[],score=score)
            project,sections=pinned_sections(path)
            self.assertEqual(sections,[])
            self.assertEqual(project["score"]["notes"][0]["velocity"],49)
    def test_reopen_conflict_missing_and_changed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "loop.wav"
            source.write_bytes(b"original")
            database = root / "catalog.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE sample(path TEXT, name TEXT)")
                connection.execute("INSERT INTO sample VALUES (?, ?)", (str(source), source.name))
            connection.close()
            path = root / "project.json"
            sections = [{"sample": source.name, "seconds": 4}]
            saved = save(path, sections, database)
            self.assertEqual(saved["revision"], 1)
            self.assertTrue(inspect(path)["ready"])
            replacement=root/"replacement.wav"
            replacement.write_bytes(b"original")
            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE sample SET path=?",(str(replacement),))
            connection.close()
            with self.assertRaisesRegex(ValueError,"differs from pinned"):
                pinned_sections(path)
            with self.assertRaisesRegex(ValueError, "conflict"):
                save(path, sections, database)
            self.assertEqual(json.loads(path.read_text())["revision"], 1)
            source.write_bytes(b"modified")
            self.assertEqual(inspect(path)["issues"][0]["issue"], "changed")
            source.unlink()
            self.assertEqual(inspect(path)["issues"][0]["issue"], "missing")

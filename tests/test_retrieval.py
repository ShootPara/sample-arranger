import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from retrieval import rank
from planner import local_sections
from commands import execute


class RetrievalTests(unittest.TestCase):
    def database(self,root):
        path=root/'catalog.sqlite';db=sqlite3.connect(path)
        db.executescript('''CREATE TABLE sample(path TEXT PRIMARY KEY,name TEXT,bytes INTEGER,modified_ns INTEGER,seconds REAL,duration_source TEXT);
        CREATE TABLE tempo_correction(path TEXT PRIMARY KEY,bpm REAL,bytes INTEGER,modified_ns INTEGER,corrected_utc TEXT);
        CREATE TABLE tempo_measurement(path TEXT PRIMARY KEY,modified_ns INTEGER,bytes INTEGER,bpm REAL,confidence REAL,source TEXT,analyzed_seconds REAL);
        CREATE TABLE metadata_observation(path TEXT PRIMARY KEY,bytes INTEGER,modified_ns INTEGER,payload TEXT,inspected_utc TEXT);''')
        return path,db
    def add(self,db,root,name,basename=None):
        source=root/(basename or name);source.write_bytes(b'fixture');stat=source.stat()
        db.execute('INSERT INTO sample VALUES(?,?,?,?,?,?)',(str(source),name,stat.st_size,stat.st_mtime_ns,1,'fixture'))
        return source,stat
    def test_whole_catalog_ranking_reaches_beyond_first256_and_checks_available_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);catalog,db=self.database(root)
            for index in range(300):self.add(db,root,f'A_Drum_{index:03}_80BPM.wav')
            match,stat=self.add(db,root,'Z_Drum_130BPM.wav');db.commit();db.close()
            report=rank(catalog,bpm=130,role='drum',limit=1)
            self.assertEqual(report['catalog_rows_considered'],301)
            self.assertEqual(report['candidates'][0]['sample'],match.name)
            self.assertEqual(local_sections(catalog,'drum',12,130)[0]['sample'],match.name)
            self.assertEqual(report['candidates'][0]['bpm_source'],'filename hint')
            self.assertEqual({item['beat_scale'] for item in report['candidates'][0]['tempo_options']},{.5,1,2})
            match.write_bytes(b'changed') # Same size: stale timestamp still rejects.
            self.assertNotEqual(rank(catalog,bpm=130,role='drum',limit=1)['candidates'][0]['sample'],match.name)
    def test_key_lock_exclusions_duplicates_correction_and_metadata_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);catalog,db=self.database(root)
            source,stat=self.add(db,root,'Bass_C_minor_90BPM.wav')
            db.execute('INSERT INTO tempo_correction VALUES(?,?,?,?,?)',(str(source),130,stat.st_size,stat.st_mtime_ns,'2026-11-04'))
            self.add(db,root,'Bass_D_minor_130BPM.wav');self.add(db,root,'Bass_130BPM.wav');self.add(db,root,'Drum_130BPM.wav')
            self.add(db,root,'Piano_C_minor_130BPM.wav')
            self.add(db,root,'Duplicate_Bass_C_minor_130BPM.wav','duplicate1.wav');self.add(db,root,'Duplicate_Bass_C_minor_130BPM.wav','duplicate2.wav')
            conflict,stat2=self.add(db,root,'Lead_C_minor_120BPM.wav')
            db.execute('INSERT INTO metadata_observation VALUES(?,?,?,?,?)',(str(conflict),stat2.st_size,stat2.st_mtime_ns,json.dumps({'acid':[{'declared_bpm':130,'duration_consistent':True,'one_shot':False}]}),'2026-11-04'))
            db.commit();db.close()
            result=rank(catalog,bpm=130,root=0,mode='minor',excluded_roles=['piano'])['candidates']
            shared=execute({'contract':1,'operation':'catalog.rank','arguments':{'catalog':str(catalog),'bpm':130,'root':0,'mode':'minor','excluded_roles':['piano']}})['result']['candidates']
            self.assertEqual(shared,result,'numeric key root must not be converted to a filesystem root')
            names={item['sample'] for item in result}
            self.assertIn('Bass_C_minor_90BPM.wav',names);self.assertIn('Drum_130BPM.wav',names)
            self.assertNotIn('Bass_D_minor_130BPM.wav',names);self.assertNotIn('Bass_130BPM.wav',names)
            self.assertFalse(any('Piano' in name or 'Duplicate' in name for name in names))
            bass=next(item for item in result if item['sample']==source.name)
            self.assertEqual(bass['bpm'],130);self.assertIn('user correction',bass['bpm_source'])
            self.assertEqual(bass['catalog_observation']['bpm_hint'],90)
            self.assertEqual(bass['catalog_observation']['tempo_correction'],130)
            lead=next(item for item in result if item['sample']==conflict.name)
            self.assertIsNone(lead['bpm']);self.assertTrue(any('conflict' in reason for reason in lead['reasons']))
            compact=rank(catalog,bpm=130,root=0,mode='minor',excluded_roles=['piano'])['planning_candidates']
            state={'revision':1,'seconds':8,'bpm':130,'root':0,'mode':'minor','brief':'Music bed'}
            prepared=execute({'contract':1,'operation':'planning.prepare','arguments':{'musical_state':state,'candidates':compact}})['result']
            self.assertNotIn(str(root),prepared['prompt']);self.assertNotIn(source.name,prepared['prompt'])
            self.assertIn('user_correction',prepared['prompt'])
            chosen=[next(item for item in compact if item['sample']==name) for name in (source.name,'Drum_130BPM.wav')]
            response={'structured':{'revision':1,'sections':[{'asset_id':item['id'],'seconds':4,'beat_scale':1} for item in chosen]}}
            validated=execute({'contract':1,'operation':'planning.validate','arguments':{'musical_state':state,'candidates':compact,'response':response}})['result']
            self.assertEqual(validated['sections'][0]['source_bpm'],130)
            with self.assertRaises(ValueError):rank(catalog,root=0)
            with self.assertRaises(ValueError):rank(catalog,bpm=float('nan'))
            with self.assertRaises(ValueError):rank(catalog,limit=1000)


if __name__=='__main__':unittest.main()

import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute
from catalog_identity import checksum
from retrieval import rank


class CatalogIdentityTests(unittest.TestCase):
    def test_rank_prepare_resolve_pins_real_audio_and_rejects_same_stat_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=root/'catalog.sqlite';source=root/'Drum_120BPM.wav'
            with wave.open(str(source),'wb') as audio:audio.setparams((2,2,44100,0,'NONE','not compressed'));audio.writeframes(b'\x10\x00'*2*4410)
            def call(op,**args):return execute({'contract':1,'operation':op,'arguments':args})['result']
            call('catalog.scan',catalog=str(db),root=str(source));call('catalog.hash',catalog=str(db),path=str(source))
            alias=root/'Other_Drum_120BPM.wav';alias.write_bytes(source.read_bytes());call('catalog.scan',catalog=str(db),root=str(alias));call('catalog.hash',catalog=str(db),path=str(alias))
            report=call('catalog.rank',catalog=str(db),role='drum');self.assertEqual(len(report['candidates']),1,'content aliases must not duplicate planning IDs')
            candidates=report['planning_candidates'];identity=candidates[0]['id'];selected=Path(report['candidates'][0]['path'])
            state={'revision':1,'seconds':1,'bpm':120,'brief':'one second bed'}
            request=call('planning.prepare',musical_state=state,candidates=candidates)
            self.assertNotIn(str(root),request['prompt']);self.assertNotIn(candidates[0]['content_sha256'],request['prompt'])
            response={'structured':{'revision':1,'sections':[{'asset_id':identity,'seconds':1,'beat_scale':1}]}}
            resolved=call('planning.resolve',catalog=str(db),musical_state=state,candidates=candidates,response=response)
            name=candidates[0]['sample'];self.assertTrue(resolved['content_verified']);self.assertEqual(resolved['source_assets'][name]['path'],str(selected))
            project=root/'project.json';call('project.save',project=str(project),sections=resolved['sections'],source_assets=resolved['source_assets'])
            before=selected.stat();data=bytearray(selected.read_bytes());data[-1]^=1;selected.write_bytes(data);os.utime(selected,ns=(before.st_atime_ns,before.st_mtime_ns))
            with self.assertRaisesRegex(ValueError,'content changed'):call('planning.resolve',catalog=str(db),musical_state=state,candidates=candidates,response=response)
            report=call('project.inspect',project=str(project));self.assertFalse(report['ready'])
    def test_content_pinned_musical_corrections_drive_ranking_with_property_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=root/'catalog.sqlite';source=root/'Lead_D_minor_120BPM.wav';source.write_bytes(b'known audio')
            def call(op,**args):return execute({'contract':1,'operation':'catalog.'+op,'arguments':{'catalog':str(db),**args}})['result']
            call('scan',root=str(source));sha=call('hash',path=str(source))['sha256']
            self.assertEqual(rank(db,role='bass',root=0,mode='major')['candidates'],[])
            call('annotate',path=str(source),expected_sha256=sha,role='bass',root=0,mode='major')
            report=rank(db,role='bass',root=0,mode='major');candidate=report['candidates'][0]
            self.assertEqual(candidate['role'],'bass');self.assertEqual(candidate['key'],{'root':0,'mode':'major'})
            self.assertEqual(report['planning_candidates'][0]['provenance'],{'role':'user_correction','key':'user_correction','bpm':'filename'})
            self.assertTrue(candidate['catalog_observation']['musical_annotation']['valid'])
            call('annotate',path=str(source),expected_sha256=sha,role='chords')
            self.assertEqual(rank(db,role='chords',root=0,mode='major')['candidates'][0]['key'],candidate['key'])
            with self.assertRaises(ValueError):call('annotate',path=str(source),expected_sha256=sha,clear=True,role='bass')
            with self.assertRaises(ValueError):call('annotate',path=str(source),expected_sha256=sha,root=True,mode='major')
            with self.assertRaises(ValueError):call('annotate',path=str(source),expected_sha256=sha,root=1)
            with self.assertRaises(ValueError):call('annotate',path=str(source),expected_sha256=sha)
            before=source.stat();source.write_bytes(b'other audio');os.utime(source,ns=(before.st_atime_ns,before.st_mtime_ns))
            with self.assertRaisesRegex(ValueError,'content changed'):call('annotate',path=str(source),expected_sha256=sha,role='bass')
            source.write_bytes(b'modified and longer');call('scan',root=str(source))
            self.assertEqual(rank(db,role='chords',root=0,mode='major')['candidates'],[])
            self.assertFalse(call('search')[0]['musical_annotation']['valid'])
            with closing(sqlite3.connect(db)) as connection:self.assertEqual(connection.execute('SELECT count(*) FROM musical_annotation_history').fetchone()[0],2)
            new_sha=call('hash',path=str(source))['sha256'];call('annotate',path=str(source),expected_sha256=new_sha,role='chords')
            call('annotate',path=str(source),expected_sha256=new_sha,clear=True)
            self.assertIsNone(call('search')[0]['musical_annotation']);self.assertEqual(rank(db)['candidates'][0]['role'],'melody')
    def test_aliases_relocation_provenance_and_catalog_only_forget(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=root/'catalog.sqlite';first=root/'Drum_120BPM.wav';alias=root/'copy.wav'
            first.write_bytes(b'known audio fixture');alias.write_bytes(first.read_bytes())
            def call(op,**args):return execute({'contract':1,'operation':'catalog.'+op,'arguments':{'catalog':str(db),**args}})['result']
            for path in (first,alias):call('scan',root=str(path),metadata_only=True)
            call('correct',path=str(first),bpm=60)
            identities=[call('hash',path=str(path)) for path in (first,alias)]
            sha=hashlib.sha256(first.read_bytes()).hexdigest()
            call('annotate',path=str(first),expected_sha256=sha,role='drum')
            original_id=rank(db,role='drum')['candidates'][0]['id']
            self.assertEqual({entry['sha256'] for entry in identities},{sha})
            duplicates=call('duplicates',limit=1)
            self.assertEqual(duplicates['groups'][0]['count'],2);self.assertFalse(duplicates['live_content_verified'])
            self.assertEqual(call('duplicates',offset=1)['groups'],[])
            replacement=root/'new-location'/'relocated.wav';replacement.parent.mkdir();first.rename(replacement)
            result=call('relocate',path=str(first),replacement=str(replacement),expected_sha256=sha)
            self.assertFalse(result['source_moved']);self.assertFalse(result['projects_changed'])
            row=next(r for r in call('search') if r['path']==str(replacement))
            self.assertEqual(row['tempo_correction'],60);self.assertTrue(row['content_identity']['matches_catalog_stat'])
            self.assertTrue(row['musical_annotation']['valid']);self.assertEqual(rank(db,role='drum')['candidates'][0]['id'],original_id)
            self.assertFalse(row['content_identity']['live_content_verified'])
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute('SELECT old_path,new_path,sha256 FROM catalog_location_history').fetchone(),(str(first),str(replacement),sha))
                self.assertEqual(connection.execute('SELECT path FROM tempo_correction_history').fetchone()[0],str(first))
            call('forget',path=str(replacement),expected_sha256=sha)
            self.assertTrue(replacement.is_file());self.assertTrue(alias.is_file());self.assertEqual(call('duplicates')['groups'],[])

    def test_changed_source_stale_correction_wrong_replacement_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=root/'catalog.sqlite';source=root/'Bass_100BPM.wav';source.write_bytes(b'old')
            def call(op,**args):return execute({'contract':1,'operation':'catalog.'+op,'arguments':{'catalog':str(db),**args}})['result']
            call('scan',root=str(source));call('correct',path=str(source),bpm=50);old=call('hash',path=str(source))
            source.write_bytes(b'new music fixture');call('scan',root=str(source))
            self.assertFalse(call('search')[0]['content_identity']['matches_catalog_stat'])
            with self.assertRaisesRegex(ValueError,'identity changed'):call('forget',path=str(source),expected_sha256=old['sha256'])
            sha=call('hash',path=str(source))['sha256'];replacement=root/'replacement.wav';replacement.write_bytes(b'not identical')
            with self.assertRaisesRegex(ValueError,'not identical'):call('relocate',path=str(source),replacement=str(replacement),expected_sha256=sha)
            self.assertEqual(call('search')[0]['path'],str(source),'failed transaction must not change location')
            replacement.write_bytes(source.read_bytes())
            call('relocate',path=str(source),replacement=str(replacement),expected_sha256=sha)
            relocated=call('search')[0];self.assertIsNone(relocated['tempo_correction'],'stale correction must not be rebound')
            self.assertTrue(source.is_file(),'relocation must never move the source file')
            with patch('catalog_identity.MAX_BYTES',2):
                with self.assertRaisesRegex(ValueError,'budget'):checksum(replacement)
            with self.assertRaises(ValueError):call('duplicates',limit=True)
            with self.assertRaises(ValueError):call('duplicates',offset=-1)

    def test_hash_rejects_changed_scanned_stat_and_observed_same_stat_is_not_live_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);db=root/'catalog.sqlite';source=root/'sample.wav';source.write_bytes(b'aaaa')
            def call(op,**args):return execute({'contract':1,'operation':'catalog.'+op,'arguments':{'catalog':str(db),**args}})['result']
            call('scan',root=str(source));record=call('hash',path=str(source));before=source.stat()
            source.write_bytes(b'bbbb');os.utime(source,ns=(before.st_atime_ns,before.st_mtime_ns))
            self.assertTrue(call('search')[0]['content_identity']['matches_catalog_stat'])
            self.assertFalse(call('search')[0]['content_identity']['live_content_verified'])
            self.assertNotEqual(call('hash',path=str(source))['sha256'],record['sha256'])
            source.write_bytes(b'different size')
            with self.assertRaisesRegex(ValueError,'changed since scan'):call('hash',path=str(source))


if __name__=='__main__':unittest.main()

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from commands import execute

BUILD=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native')


@unittest.skipUnless((BUILD/'arranger-delay-fixture.vst3').is_file(),'native fixture required')
class RegistryTests(unittest.TestCase):
    def test_actual_initialize_abort_quarantine_cached_scan_and_explicit_reviewed_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'plugins';folder.mkdir();registry=root/'registry.sqlite'
            shutil.copy2(BUILD/'arranger-delay-fixture.vst3',folder/'working.vst3')
            args={'registry':str(registry),'worker':str(BUILD/'arranger-vst3.exe'),'root':str(folder)}
            request={'contract':1,'operation':'plugins.scan','arguments':args}
            first=execute(request)['result'];self.assertEqual(first['ready'],1)
            with patch('plugin_registry.inspect',side_effect=AssertionError('unchanged inventory must not relaunch')):
                self.assertEqual(execute(request)['result']['cached'],1)
            failed=folder/'crashing.vst3';shutil.copy2(BUILD/'arranger-delay-fixture.vst3',failed)
            with patch.dict(os.environ,{'ARRANGER_FIXTURE_INITIALIZE_CRASH':'1'}):
                result=execute(request)['result']
            self.assertEqual(result['quarantined'],1);self.assertEqual(result['ready'],1)
            with patch('plugin_registry.inspect',side_effect=AssertionError('quarantine must not auto-retry')):
                self.assertEqual(execute(request)['result']['cached'],2)
            rows=execute({'contract':1,'operation':'plugins.list','arguments':{'registry':str(registry)}})['result']
            quarantined=next(row for row in rows if row['status']=='quarantined')
            self.assertIn('Plugin inspection failed',quarantined['error'])
            retry={'contract':1,'operation':'plugins.retry','arguments':{'registry':str(registry),'worker':args['worker'],'plugin':str(failed),'expected_sha256':'0'*64}}
            with self.assertRaisesRegex(ValueError,'reviewed binary'):execute(retry)
            retry['arguments']['expected_sha256']=quarantined['binary_sha256']
            recovered=execute(retry)['result'];self.assertEqual(recovered['status'],'ready');self.assertFalse(recovered['cached'])
            self.assertEqual(len(recovered['report']['classes']),5)

    def test_cancellation_never_records_a_plugin_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);marker=root/'cancel';marker.touch();registry=root/'registry.sqlite'
            with patch.dict(os.environ,{'ARRANGER_CANCEL_FILE':str(marker)}),self.assertRaisesRegex(ValueError,'canceled'):
                execute({'contract':1,'operation':'plugins.scan','arguments':{'registry':str(registry),'worker':str(BUILD/'arranger-vst3.exe'),'root':str(BUILD/'arranger-delay-fixture.vst3')}})
            rows=execute({'contract':1,'operation':'plugins.list','arguments':{'registry':str(registry)}})['result']
            self.assertEqual(rows,[])

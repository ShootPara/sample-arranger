import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_audio_tools import verify


class AudioToolPinTests(unittest.TestCase):
    def test_byte_mismatch_fails_before_execution_and_version_contract_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);body=b'not an executable; mocked version calls only';tools=[];selected={}
            for name in ('ffmpeg','ffprobe','ffplay'):
                path=root/(name+'.exe');path.write_bytes(body);selected[name+'.exe']=path
                tools.append({'name':name+'.exe','bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'version_line':'known version'})
            lock=root/'lock.json';lock.write_text(json.dumps({'schema':1,'tools':tools}))
            with patch('verify_audio_tools.subprocess.run',return_value=subprocess.CompletedProcess([],0,'known version\n')) as run:
                self.assertEqual(len(verify(lock,selected)['verified_audio_tools']),3);self.assertEqual(run.call_count,3)
            selected['ffmpeg.exe'].write_bytes(body+b'changed')
            with patch('verify_audio_tools.subprocess.run') as run,self.assertRaisesRegex(ValueError,'differs from the pinned'):
                verify(lock,selected)
            run.assert_not_called()
            selected['ffmpeg.exe'].write_bytes(body)
            with patch('verify_audio_tools.subprocess.run',return_value=subprocess.CompletedProcess([],0,'different version\n')),self.assertRaisesRegex(ValueError,'version differs'):
                verify(lock,selected)


if __name__=='__main__':unittest.main()

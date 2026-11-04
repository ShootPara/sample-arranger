"""One bounded real HTTP fixture; never a server/model/credential integration claim."""
import http.server
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from broker_port import configure,status,BrokerPort,endpoint
from ai_planning import score_plan
from commands import execute


class BrokerPortTests(unittest.TestCase):
    def test_protected_app_connection_real_wire_proposal_and_no_token_in_requests_or_projects(self):
        observed=[];identity=str(uuid.uuid4());epoch=str(uuid.uuid4());token='fixture-app-credential-'+('x'*32)
        proposal={'revision':1,'progression':[1,4],'density':'sparse','melody_grid':[0,-1,2,-1,1,-1,2,-1]}
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def respond(self,value,code):
                data=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));observed.append((self.path,body))
                if self.headers.get('Authorization')!='Bearer '+token:self.respond({'error':{'code':'authentication_required'}},401);return
                self.respond({'id':identity,'instance_id':epoch,'state':'queued'},202)
            def do_GET(self):self.respond({'id':identity,'instance_id':epoch,'state':'completed','result':{'structured':proposal,'text':json.dumps(proposal),'limited':False}},200)
        server=http.server.HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}):
                self.assertFalse(status()['configured']);configure(f'http://127.0.0.1:{server.server_port}',token)
                self.assertTrue(status()['configured'])
                result=score_plan('4 seconds gentle music',{'seconds':4,'root':9,'mode':'minor','bpm':120})
                self.assertEqual(result['score']['duration_frames'],176400);self.assertEqual([cell['tone'] for cell in result['score']['melody_pattern']],proposal['melody_grid'])
                self.assertEqual(sum(cell['ticks'] for cell in result['score']['melody_pattern']),3840)
                self.assertEqual(len(observed),1);path,wire=observed[0];self.assertEqual(path,'/api/v1/ai/jobs')
                self.assertEqual(wire['parameters'],{'context_tokens':4096,'max_output_tokens':1024,'temperature':0,'thinking':False})
                self.assertNotIn('model',wire);self.assertNotIn(token,json.dumps(wire));self.assertNotIn(directory,json.dumps(wire))
                for file in Path(directory).rglob('*.json'):self.assertNotIn(token,file.read_text(encoding='utf-8'))
                self.assertNotIn(token,json.dumps(result));self.assertEqual(result['score']['ai_provenance']['inference_receipts'][0]['state'],'completed')
                self.assertTrue(execute({'contract':1,'operation':'ai.status','arguments':{}})['result']['configured'])
                configure(f'http://127.0.0.1:{server.server_port}','wrong-fixture-token-'+('y'*32))
                with self.assertRaises(PermissionError):score_plan('4 seconds music',{'seconds':4})
                self.assertEqual(len(observed),2,'authentication failure must not trigger repair or retry')
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

    def test_transport_endpoint_and_missing_configuration_fail_without_fallback(self):
        for value in ('http://192.0.2.5:11434','https://user:secret@example.com','https://example.com/api','https://example.com?token=x'):
            with self.assertRaises(ValueError):endpoint(value)
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}):
            with self.assertRaises(FileNotFoundError):BrokerPort()

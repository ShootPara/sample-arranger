import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from process_group import popen
from resources import plugin_memory_bytes,command_memory_bytes

BUILD=Path(os.environ["LOCALAPPDATA"],"SampleArranger/tools/arranger-native")

class ResourceTests(unittest.TestCase):
    @unittest.skipUnless((BUILD/'arranger-lifecycle-fixture.exe').exists(),'native fixture required')
    def test_aggregate_command_limit_rejects_second_commit_despite_larger_individual_caps(self):
        import json
        code='''import json,subprocess,sys
sys.path.insert(0,sys.argv[1])
from process_group import popen,diagnostic
children=[]
try:
    values=[]
    for i in range(2):
        child=popen([sys.argv[2],'--hold-memory','300'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,max_job_bytes=1024**3)
        children.append(child);values.append(child.stdout.readline().strip())
    print(json.dumps({'allocations':values,'group':diagnostic([child.pid for child in children])}),flush=True)
finally:
    for child in children:child.communicate('release\\n',timeout=5)
'''
        environment=dict(os.environ);environment['ARRANGER_COMMAND_MEMORY_MIB']='512'
        result=subprocess.run([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]/'src'),str(BUILD/'arranger-lifecycle-fixture.exe')],
                              capture_output=True,text=True,env=environment,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout);self.assertEqual(report['allocations'],['held','denied'])
        self.assertEqual(report['group']['job_memory_limit_bytes'],512*1024**2)
    def test_configured_budget_validation(self):
        with patch.dict(os.environ,{"ARRANGER_PLUGIN_MEMORY_MIB":"2048"}):self.assertEqual(plugin_memory_bytes(),2*1024**3)
        with patch.dict(os.environ,{"ARRANGER_PLUGIN_MEMORY_MIB":"99999"}),self.assertRaises(ValueError):plugin_memory_bytes()
        with patch.dict(os.environ,{'ARRANGER_COMMAND_MEMORY_MIB':'8192'}):self.assertEqual(command_memory_bytes(),8*1024**3)
        for invalid in ('511','16385','NaN','-1'):
            with patch.dict(os.environ,{'ARRANGER_COMMAND_MEMORY_MIB':invalid}),self.assertRaises(ValueError):command_memory_bytes()

    def test_invalid_startup_budget_returns_a_structured_cli_failure_without_running_children(self):
        import json
        environment=dict(os.environ);environment['ARRANGER_COMMAND_MEMORY_MIB']='511'
        result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'src/commands.py')],
                              input=json.dumps({'contract':1,'operation':'capabilities','arguments':{}}),env=environment,
                              text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,2)
        self.assertEqual(json.loads(result.stdout)['error']['code'],'INVALID_REQUEST_OR_STATE')
        self.assertNotIn('child_started',result.stderr);self.assertNotIn('Traceback',result.stderr)

    @unittest.skipUnless((BUILD/"arranger-lifecycle-fixture.exe").exists(),"native fixture required")
    def test_native_commit_rejected_by_owned_128mib_limit(self):
        command=[str(BUILD/"arranger-lifecycle-fixture.exe"),"--probe-memory"]
        self.assertEqual(subprocess.run(command,timeout=5).returncode,9,"control without128MiB child limit must allocate")
        with popen(command,max_job_bytes=128*1024**2) as child:
            self.assertEqual(child.wait(timeout=5),0,"owned limit must reject256MiB allocation")

"""Opt-in real frozen CLI/render/native/playback smoke, outside the source cwd.

PATH excludes installed Python/FFmpeg; generated fixture audio only, no capture.
No clean-Windows-machine or redistribution acceptance is implied.
"""
import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import wave


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--app',type=Path,required=True)
    app=parser.parse_args().app.resolve();cli=app/'arranger-cli.exe'
    fixture=Path(os.environ['LOCALAPPDATA'],'SampleArranger/tools/arranger-native/arranger-delay-fixture.vst3')
    with tempfile.TemporaryDirectory(prefix='arranger-frozen-check-') as directory:
        root=Path(directory);environment=dict(os.environ)
        environment['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
        environment['LOCALAPPDATA']=str(root/'fresh-app-data')
        for key in ('PYTHONPATH','PYTHONHOME'):environment.pop(key,None)
        calls=[]
        def request(operation_name,**arguments):
            result=subprocess.run([str(cli)],input=json.dumps({'contract':1,'operation':operation_name,'arguments':arguments}),
                                  text=True,capture_output=True,cwd=root,env=environment,timeout=60)
            if result.returncode:raise AssertionError((operation_name,result.returncode,result.stdout,result.stderr))
            response=json.loads(result.stdout)
            if 'error' in response:raise AssertionError(response)
            calls.append(operation_name);return response['result']
        request('capabilities')
        assert len(request('contracts.schema',operation='project.graph.save')['oneOf'])==1
        source=root/'known.wav'
        with wave.open(str(source),'wb') as output:
            output.setparams((2,2,44100,0,'NONE','not compressed'));output.writeframes(bytes(4410*4))
        catalog=root/'catalog.sqlite'
        assert request('catalog.scan',catalog=str(catalog),root=str(source),metadata_only=True)['indexed']==1
        assert request('catalog.metadata',catalog=str(catalog),path=str(source))['embedded_metadata']['state']=='observed'
        score=request('score.compile',intent={'seconds':1,'bpm':137.25})
        score=request('score.harmony.edit',score=score,changes=[{'bar':0,'degree':4}])
        protected=next(index for index,note in enumerate(score['notes']) if note['part']=='chords')
        score=request('score.locks.set',score=score,indices=[protected])
        project=root/'project.json';jobs=root/'jobs';jobs.mkdir()
        worker=app/'_internal/native/arranger-vst3.exe'
        request('project.save',project=str(project),sections=[],score=score,processing={'worker':str(worker)},
                instruments={'chords':{'plugin':str(fixture),'class_id':'6623100614424231A562100212142801'}})
        arguments={'jobs':str(jobs),'project':str(project),'project_sha256':hashlib.sha256(project.read_bytes()).hexdigest(),'request_id':str(uuid.uuid4())}
        first=request('jobs.submit',**arguments);second=request('jobs.submit',**arguments)
        assert first==second and len(list(jobs.glob('job-*')))==1
        assert len(first['attachments'])==2
        data=subprocess.run([str(app/'_internal/bin/ffmpeg.exe'),'-v','error','-i',first['audio'],'-f','f32le','-'],capture_output=True,check=True,env=environment,timeout=10).stdout
        audio=array('f');audio.frombytes(data)
        assert len(audio)==44100*2 and max(map(abs,audio))>0.01
        assert first['composition']['score']['harmony'][0]['degree']==4
        assert first['composition']['score']['note_locks']==score['note_locks']
        graph_project=root/'graph.json'
        graph={'nodes':[{'id':'synth','plugin':str(fixture),'class_id':'6623100314424231A562100212142801',
                         'input':{'node':'silence','bus':0},'score_part':'chords','automation_points':[{'frame':0,'id':1,'value':.25}]}],
               'outputs':[{'node':'synth','bus':0,'gain':.5}]}
        assert request('project.graph.save',project=str(graph_project),graph=graph,sources={'silence':{'silence':True}},
                       worker=str(worker),seconds=1,tempo=137.25,score=score)['ready']
        routed=request('jobs.submit',project=str(graph_project),project_sha256=hashlib.sha256(graph_project.read_bytes()).hexdigest(),jobs=str(jobs),request_id=str(uuid.uuid4()))
        assert routed['composition']['nodes'][0]['latency_samples']==128 and not routed['measurements']['silent']
        marker=root/'cancel'
        child=subprocess.Popen([str(cli),'--cancel-file',str(marker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               cwd=root,env=environment,text=True)
        try:
            child.stdin.write(json.dumps({'contract':1,'operation':'continuous.play','arguments':{'builtin':True,'bpm':128}}));child.stdin.close();child.stdin=None
            deadline=time.monotonic()+10
            while not list((root/'fresh-app-data/SampleArranger/continuous').glob('session-*/chunk-*.wav')):
                if time.monotonic()>deadline or child.poll() is not None:raise AssertionError('packaged disposable playback did not start')
                time.sleep(0.05)
            time.sleep(1);marker.touch();stdout,stderr=child.communicate(timeout=15)
            assert child.returncode==0,(stdout,stderr)
            result=json.loads(stdout)['result'];assert result['state']=='stopped' and 'audio' not in result
            assert not list((root/'fresh-app-data/SampleArranger/continuous').glob('session-*/chunk-*.wav'))
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=5)
        print(json.dumps({'frozen_cli':True,'source_cwd':False,'system_path_only':True,'fresh_app_data':True,
                          'operations':calls,'decoded_frames':len(audio)//2,'native_state_files':len(first['attachments']),
                          'continuous_cancel_cleanup':True,'capture':False}))


if __name__=='__main__':main()

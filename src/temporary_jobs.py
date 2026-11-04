"""User-controlled temporary normal jobs; distinct from no-save continuous audio.

GUI sessions retain normal deliverables until the workspace closes. CLI delivery
waits for explicit caller acknowledgement before clearing its owned session.
Catalogs, source assets and explicitly saved projects remain independent.
"""
import json
import os
from pathlib import Path
import sys
import time
import uuid
from scratch import scratch,cleanup,bounded_tree
MAX_RESULTS=8
MAX_RESULT_BYTES=2*1024**3
MAX_NEW_JOB_BYTES=320*1024**2


def root_path():return Path(os.environ['LOCALAPPDATA'],'SampleArranger/temporary-normal')


def recover():return {'removed_sessions':cleanup(root_path()),'scope':'inactive app-owned temporary normal jobs only'}


class TemporaryJobs:
    def __init__(self):
        self.context=scratch(root_path());self.jobs=self.context.__enter__();self.closed=False
    def reserve(self):
        if self.closed:raise ValueError('temporary session is closed')
        if len(list(self.jobs.glob('job-*')))>=MAX_RESULTS or len(list(self.jobs.glob('.control/*.json')))>=MAX_RESULTS:
            raise ValueError('temporary session holds eight results or attempts; clear temporary results or close this workspace first')
        files,_=bounded_tree(self.jobs)
        if sum(path.stat().st_size for path in files)+MAX_NEW_JOB_BYTES>MAX_RESULT_BYTES:
            raise ValueError('temporary result allocation would exceed the two-GiB retained-output budget')
        return self.jobs
    def close(self):
        if not self.closed:
            try:self.context.__exit__(None,None,None)
            finally:self.closed=True
        elif self.jobs.exists():
            recover()
            if self.jobs.exists():raise ValueError('temporary session cleanup is incomplete; owned leftovers require recovery review')
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def deliver(project,project_sha256,ack_file,timeout_seconds=300):
    from job_control import submit
    if type(timeout_seconds) not in (int,float) or not 1<=timeout_seconds<=3600:raise ValueError('temporary acknowledgement timeout must be1 to3600 seconds')
    ack_file=Path(ack_file)
    if ack_file.exists() or ack_file.is_symlink() or not ack_file.parent.is_dir():raise ValueError('acknowledgement must be an initially absent file in a caller-owned existing control folder')
    with TemporaryJobs() as session:
        result=submit(session.reserve(),str(uuid.uuid4()),project,project_sha256)
        event={'event':'artifact_ready','temporary':True,'audio':result['audio'],'audio_sha256':result['audio_sha256'],
               'manifest':str(Path(result['audio']).parent/'manifest.json'),'seconds':result['requested_seconds'],
               'acknowledgement':'write JSON {audio_sha256: the reported hash} after retrieval; this authorizes cleanup',
               'expires_in_seconds':timeout_seconds}
        print(json.dumps(event),file=sys.stderr,flush=True)
        deadline=time.monotonic()+timeout_seconds;state='expired'
        while time.monotonic()<deadline:
            marker=os.environ.get('ARRANGER_CANCEL_FILE')
            if marker and Path(marker).exists():state='canceled';break
            if ack_file.is_file():
                if ack_file.is_symlink():raise ValueError('temporary acknowledgement cannot be redirected')
                if ack_file.stat().st_size>256:raise ValueError('temporary acknowledgement exceeds256 bytes')
                try:value=json.loads(ack_file.read_text(encoding='utf-8'))
                except (ValueError,OSError):value=None # Caller may still be publishing it atomically.
                if value=={'audio_sha256':result['audio_sha256']}:state='acknowledged';break
            time.sleep(0.05)
        identity=result['audio_sha256']
    return {'state':state,'audio_sha256':identity,'temporary_audio_cleared':True,'ack_file_retained':'caller-controlled',
            'source_assets_deleted':False,'catalog_or_saved_projects_deleted':False}

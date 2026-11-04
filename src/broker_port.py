"""App-owned broker connection; verified TLS, protected local secret, no provider API."""
import ctypes
from ctypes import wintypes
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import threading
import uuid
from urllib.parse import urlsplit
from inference_session import AdmissionRejected,validate_request


def root():return Path(os.environ['LOCALAPPDATA'],'SampleArranger/ai')


def protect(value,decode=False):
    if os.name!='nt':raise OSError('AI credentials require Windows current-user protection')
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]
    buffer=ctypes.create_string_buffer(value);incoming=Blob(len(value),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));out=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    function=crypt.CryptUnprotectData if decode else crypt.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    if not function(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(out)):raise OSError('Windows could not protect/read the app credential')
    try:return ctypes.string_at(out.data,out.size)
    finally:kernel.LocalFree(out.data)


def endpoint(value):
    if not isinstance(value,str) or len(value)>2048:raise ValueError('invalid AI broker endpoint')
    url=urlsplit(value)
    if (url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment
            or url.path not in ('','/') or url.scheme=='http' and url.hostname not in ('127.0.0.1','localhost')):
        raise ValueError('AI broker requires verified HTTPS, or loopback HTTP; no URL credentials/path')
    return url


def configure(address,token,ca_file=None):
    endpoint(address)
    if not isinstance(token,str) or not 32<=len(token)<=512 or not token.isascii() or any(c.isspace() for c in token):raise ValueError('provide the dedicated app inference token')
    folder=root();folder.mkdir(parents=True,exist_ok=True)
    if folder.is_symlink() or folder.is_junction():raise ValueError('AI configuration folder is redirected')
    ca=str(Path(ca_file).resolve()) if ca_file else None
    if ca and not Path(ca).is_file():raise ValueError('AI certificate authority file is unavailable')
    # Unique protected secret means a failed settings replacement retains the old connection.
    name='credential-'+str(uuid.uuid4())+'.dpapi';secret=folder/name;secret.write_bytes(protect(token.encode('ascii')))
    config={'schema':1,'principal':'sample-arranger','endpoint':address,'ca_file':ca,'credential_file':name}
    temporary=folder/('connection-'+str(uuid.uuid4())+'.tmp')
    try:temporary.write_text(json.dumps(config),encoding='utf-8');os.replace(temporary,folder/'connection.json')
    finally:temporary.unlink(missing_ok=True)
    return status()


def connection():
    path=root()/'connection.json'
    if not path.is_file():raise FileNotFoundError('AI connection is not configured; open AI connection and provide the dedicated app credential')
    if path.stat().st_size>16000:raise ValueError('AI connection configuration exceeds bounds')
    config=json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(config,dict) or set(config)!={'schema','principal','endpoint','ca_file','credential_file'} or config['schema']!=1 or config['principal']!='sample-arranger'):
        raise ValueError('AI connection must use the dedicated sample-arranger identity')
    endpoint(config['endpoint']);name=config['credential_file']
    if not isinstance(name,str) or Path(name).name!=name or not name.startswith('credential-') or not name.endswith('.dpapi'):raise ValueError('AI secret must be app-owned current-user protected storage')
    return config


def status():
    try:
        config=connection();path=root()/config['credential_file']
        return {'configured':path.is_file(),'principal':'sample-arranger','transport':'verified broker; no cloud/provider fallback','live_verified':False}
    except (FileNotFoundError,ValueError,OSError):return {'configured':False,'live_verified':False}


class BrokerError(OSError):
    def __init__(self,code,http_status=None):super().__init__('AI broker: '+code);self.code=code;self.http_status=http_status


class BrokerPort:
    def __init__(self):
        config=connection();self.url=endpoint(config['endpoint']);path=root()/config['credential_file']
        if path.stat().st_size>16384:raise ValueError('AI protected credential exceeds bounds')
        self._token=protect(path.read_bytes(),True).decode('ascii')
        if not 32<=len(self._token)<=512:raise ValueError('AI protected credential is invalid')
        self.context=ssl.create_default_context(cafile=config['ca_file']) if self.url.scheme=='https' else None;self.instances={}

    def request(self,method,path,body=None,*,timeout=5):
        if not 0<timeout<=5:raise ValueError('AI HTTP call exceeds its bounded deadline')
        raw=json.dumps(body,allow_nan=False,ensure_ascii=False,separators=(',',':')).encode('utf-8') if body is not None else None
        if raw and len(raw)>65536:raise ValueError('AI request exceeds broker body bounds')
        cls=http.client.HTTPSConnection if self.context else http.client.HTTPConnection
        options={'timeout':timeout}
        if self.context:options['context']=self.context
        conn=cls(self.url.hostname,self.url.port,**options);sock=None;expired=threading.Event();response=None
        def interrupt():
            expired.set()
            if sock:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
        timer=threading.Timer(timeout,interrupt);timer.daemon=True;timer.start()
        try:
            conn.connect();sock=conn.sock
            if expired.is_set():raise TimeoutError()
            conn.request(method,path,raw,{'Authorization':'Bearer '+self._token,'Content-Type':'application/json'})
            response=conn.getresponse();data=response.read(64001)
            if expired.is_set():raise TimeoutError()
            if len(data)>64000:raise BrokerError('response_too_large')
            value=json.loads(data)
            if not isinstance(value,dict):raise BrokerError('invalid_response')
            if response.status>=400:
                code=value.get('error',{}).get('code')
                if not isinstance(code,str) or not code.replace('_','').isalnum() or len(code)>80:code='http_error'
                raise BrokerError(code,response.status)
            return value
        except BrokerError:raise
        except (OSError,ValueError,http.client.HTTPException):raise BrokerError('transport_or_TLS_failure') from None
        finally:
            timer.cancel()
            if response:response.close()
            conn.close()

    def normalized(self,value):
        identity=value.get('id');instance=value.get('instance_id')
        try:uuid.UUID(identity);uuid.UUID(instance)
        except (ValueError,TypeError,AttributeError):raise BrokerError('invalid_job_identity') from None
        if identity in self.instances and self.instances[identity]!=instance:raise BrokerError('broker_epoch_changed')
        self.instances[identity]=instance;state=value.get('state')
        if state=='timed_out':state='failed'
        return {'id':identity,'state':state,'result':value.get('result')}

    def admit(self,request,timeout):
        validate_request(request['prompt'],request['context'],request['output_limit'],request['schema'])
        wire={'input':{'type':'prompt','prompt':request['prompt']},'output':{'type':'json_schema','schema':request['schema']},
              'parameters':{'context_tokens':request['context'],'max_output_tokens':request['output_limit'],'temperature':0,'thinking':False},
              'timeouts':{'queue_seconds':request['queue_timeout_seconds'],'execution_seconds':request['execution_timeout_seconds']},'client_request_id':request['request_id']}
        try:return self.normalized(self.request('POST','/api/v1/ai/jobs',wire,timeout=timeout))
        except BrokerError as error:
            if error.http_status in (401,403):raise PermissionError('AI app credential was denied; no inference was admitted') from None
            if error.http_status==429:raise AdmissionRejected('busy') from None
            if error.http_status==503:raise AdmissionRejected('unavailable') from None
            raise
    def poll(self,job_id,timeout):
        if job_id not in self.instances:raise ValueError('AI can only poll its owned admitted job')
        return self.normalized(self.request('GET','/api/v1/ai/jobs/'+job_id,timeout=timeout))
    def cancel(self,job_id,timeout):
        if job_id not in self.instances:raise ValueError('AI can only cancel its owned admitted job')
        try:
            result=self.normalized(self.request('DELETE','/api/v1/ai/jobs/'+job_id,timeout=timeout));return result['state']=='canceled'
        except BrokerError as error:
            if error.http_status==409:return False
            raise

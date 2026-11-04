"""Windows job lifetime ownership for explicitly admitted app child processes.

No OS policy changes or sandbox claim. The non-inheritable handle intentionally
stays open until process exit; closing it while this process lives would kill self.
"""
import ctypes
from ctypes import wintypes
import os
import subprocess
import threading
import weakref
from pathlib import Path

_handle=None
_layout=None


class OwnedChild:
    """Popen-compatible ownership: closing/killing this child also releases helpers."""
    def __init__(self,child,job,kernel):
        self.child,self.job,self.kernel=child,job,kernel
        self.finalizer=weakref.finalize(self,kernel.CloseHandle,job)
    def __getattr__(self,name):return getattr(self.child,name)
    def release(self):
        if self.job:
            self.finalizer();self.job=None
    def poll(self):
        code=self.child.poll()
        if code is not None:self.release()
        return code
    def wait(self,timeout=None):
        code=self.child.wait(timeout=timeout);self.release();return code
    def communicate(self,*args,**kwargs):
        try:return self.child.communicate(*args,**kwargs)
        finally:self.poll()
    def kill(self):
        if self.job:
            if not self.kernel.TerminateJobObject(self.job,1):raise ctypes.WinError(ctypes.get_last_error())
        elif self.child.poll() is None:self.child.kill()
    terminate=kill
    def __enter__(self):return self
    def __exit__(self,*args):
        if args[0] is not None:self.kill()
        self.release()
        return self.child.__exit__(*args)


def own_process_tree():
    global _handle,_layout
    if os.name!="nt" or _handle is not None:return
    class Basic(ctypes.Structure):
        _fields_=[("process_time",ctypes.c_longlong),("job_time",ctypes.c_longlong),
                  ("flags",wintypes.DWORD),("minimum",ctypes.c_size_t),("maximum",ctypes.c_size_t),
                  ("active",wintypes.DWORD),("affinity",ctypes.c_size_t),
                  ("priority",wintypes.DWORD),("scheduling",wintypes.DWORD)]
    class Counters(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ("read_ops","write_ops","other_ops","read_bytes","write_bytes","other_bytes")]
    class Extended(ctypes.Structure):
        _fields_=[("basic",Basic),("io",Counters),("process_memory",ctypes.c_size_t),
                  ("job_memory",ctypes.c_size_t),("peak_process",ctypes.c_size_t),("peak_job",ctypes.c_size_t)]
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    from resources import command_memory_bytes
    aggregate_budget=command_memory_bytes()
    handle=kernel.CreateJobObjectW(None,None)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    limits=Extended();limits.basic.flags=0x2000|0x200 # KILL_ON_JOB_CLOSE + owned aggregate JOB_MEMORY
    limits.job_memory=aggregate_budget
    if not kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
        error=ctypes.get_last_error();kernel.CloseHandle(handle);raise ctypes.WinError(error)
    if not kernel.AssignProcessToJobObject(handle,kernel.GetCurrentProcess()):
        error=ctypes.get_last_error();kernel.CloseHandle(handle);raise ctypes.WinError(error)
    _handle=handle
    _layout=Extended
    owner=os.environ.get("ARRANGER_OWNER_PID","")
    if owner.isascii() and owner.isdigit() and 0<int(owner)!=os.getpid():
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        parent=kernel.OpenProcess(0x100000,False,int(owner))
        if not parent:raise OSError("owning app process is no longer available")
        marker=os.environ.get("ARRANGER_CANCEL_FILE")
        def owner_exited():
            kernel.WaitForSingleObject(parent,0xFFFFFFFF);kernel.CloseHandle(parent)
            if marker:
                try:Path(marker).touch()
                except OSError:pass
                threading.Event().wait(5) # Give cooperative staging cleanup a bounded grace period.
            os._exit(125)
        threading.Thread(target=owner_exited,daemon=True).start()


def popen(command,**kwargs):
    """Create suspended, admit to the owned group, then resume before app code runs.

    Explicit admission is necessary: implicit inheritance failed in this measured
    host environment. No enclosing job/security policy is changed or bypassed.
    """
    from audio_tools import file_inputs
    command=file_inputs(command)
    max_job_bytes=kwargs.pop("max_job_bytes",None)
    if max_job_bytes is not None and (type(max_job_bytes) is not int or not 128*1024**2<=max_job_bytes<=8*1024**3):
        raise ValueError("owned child memory budget must be128MiB to8GiB")
    if os.name!="nt":
        if max_job_bytes is not None:raise OSError("owned memory limit requires Windows jobs")
        return subprocess.Popen(command,**kwargs)
    own_process_tree()
    environment=dict(kwargs.get("env") or os.environ)
    environment["ARRANGER_OWNER_PID"]=str(os.getpid())
    kwargs["env"]=environment
    kwargs["creationflags"]=kwargs.get("creationflags",0)|0x00000004 # CREATE_SUSPENDED
    child=subprocess.Popen(command,**kwargs)
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.OpenThread.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenThread.restype=wintypes.HANDLE
    kernel.ResumeThread.argtypes=[wintypes.HANDLE];kernel.ResumeThread.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    class ThreadEntry(ctypes.Structure):
        _fields_=[("size",wintypes.DWORD),("usage",wintypes.DWORD),("thread",wintypes.DWORD),
                  ("owner",wintypes.DWORD),("priority",wintypes.LONG),("delta",wintypes.LONG),("flags",wintypes.DWORD)]
    kernel.Thread32First.argtypes=[wintypes.HANDLE,ctypes.POINTER(ThreadEntry)]
    kernel.Thread32Next.argtypes=[wintypes.HANDLE,ctypes.POINTER(ThreadEntry)]
    child_job=None
    try:
        if not kernel.AssignProcessToJobObject(_handle,int(child._handle)):raise ctypes.WinError(ctypes.get_last_error())
        child_job=kernel.CreateJobObjectW(None,None)
        if not child_job:raise ctypes.WinError(ctypes.get_last_error())
        limits=_layout();limits.basic.flags=0x2000
        if max_job_bytes is not None:
            limits.basic.flags|=0x200 # JOB_OBJECT_LIMIT_JOB_MEMORY, owned children only
            limits.job_memory=max_job_bytes
        if not kernel.SetInformationJobObject(child_job,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(child_job,int(child._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        snapshot=kernel.CreateToolhelp32Snapshot(4,0)
        if snapshot==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        threads=[]
        try:
            entry=ThreadEntry();entry.size=ctypes.sizeof(entry)
            ok=kernel.Thread32First(snapshot,ctypes.byref(entry))
            while ok:
                if entry.owner==child.pid:threads.append(entry.thread)
                ok=kernel.Thread32Next(snapshot,ctypes.byref(entry))
        finally:kernel.CloseHandle(snapshot)
        if len(threads)!=1:raise OSError("owned child primary thread could not be identified before resume")
        thread=kernel.OpenThread(2,False,threads[0])
        if not thread:raise ctypes.WinError(ctypes.get_last_error())
        try:
            if kernel.ResumeThread(thread)==0xFFFFFFFF:raise ctypes.WinError(ctypes.get_last_error())
        finally:kernel.CloseHandle(thread)
        return OwnedChild(child,child_job,kernel)
    except BaseException:
        child.kill();child.wait(timeout=5)
        if child_job:kernel.CloseHandle(child_job)
        for stream in (child.stdin,child.stdout,child.stderr):
            if stream:stream.close()
        raise


def diagnostic(pids):
    """Noncontent test evidence for this process's own group only."""
    kernel=ctypes.WinDLL("kernel32",use_last_error=True)
    kernel.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
    limits=_layout()
    queried=kernel.QueryInformationJobObject(_handle,9,ctypes.byref(limits),ctypes.sizeof(limits),None)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.IsProcessInJob.argtypes=[wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    members=[]
    for pid in [os.getpid(),*pids]:
        process=kernel.OpenProcess(0x1000,False,pid);member=wintypes.BOOL()
        ok=kernel.IsProcessInJob(process,_handle,ctypes.byref(member))
        members.append({"pid":pid,"queried":bool(ok),"member":bool(member.value)})
        kernel.CloseHandle(process)
    return {"size":ctypes.sizeof(limits),"flags":limits.basic.flags,"queried":bool(queried),"members":members,
            'job_memory_limit_bytes':limits.job_memory,'peak_job_memory_bytes':limits.peak_job}

"""Windows process-object guard for bounded UI cancellation, including launchers.

The CLI reports its actual process and creation time before executing a request.
The UI holds that exact kernel process object; forced cancellation never kills a
reused PID. This is app lifetime coordination, not a plugin security sandbox.
"""
import ctypes
from ctypes import wintypes
import os


def kernel():
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.GetCurrentProcess.restype=wintypes.HANDLE
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
    api.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    api.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    return api


def created(api,handle):
    values=[wintypes.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(handle,*(ctypes.byref(value) for value in values)):raise ctypes.WinError(ctypes.get_last_error())
    return values[0].dwLowDateTime|(values[0].dwHighDateTime<<32)


def current_identity():
    api=kernel();return os.getpid(),created(api,api.GetCurrentProcess())


class ProcessGuard:
    def __init__(self,pid,creation):
        if type(pid) is not int or not 0<pid<2**32 or type(creation) is not int or not 0<creation<2**64:raise ValueError('invalid command lifetime identity')
        self.api=kernel();self.handle=self.api.OpenProcess(0x101001,False,pid)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        try:
            if created(self.api,self.handle)!=creation:raise ValueError('command process identity changed')
        except Exception:self.close();raise
    def running(self):return bool(self.handle and self.api.WaitForSingleObject(self.handle,0)==258)
    def terminate(self):
        if self.running() and not self.api.TerminateProcess(self.handle,125):raise ctypes.WinError(ctypes.get_last_error())
    def close(self):
        if self.handle:self.api.CloseHandle(self.handle);self.handle=None

"""Stop the server tree if Electron dies, including a hard main-process crash."""
import os
import signal
import sys
import time

parent, server = map(int, sys.argv[1:3])

if os.name == 'nt':
    import ctypes
    from ctypes import wintypes as w

    k = ctypes.WinDLL('kernel32', use_last_error=True)

    class BasicLimits(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', w.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                     'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IO),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    k.CreateJobObjectW.restype = w.HANDLE
    k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    k.WaitForSingleObject.restype = w.DWORD
    k.CloseHandle.argtypes = [w.HANDLE]
    handles = []
    try:
        child = k.OpenProcess(0x100000 | 0x0100 | 0x0001, False, server)
        job = k.CreateJobObjectW(None, None)
        handles = [job, child]
        if not all(handles):
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not k.AssignProcessToJobObject(job, child):
            raise ctypes.WinError(ctypes.get_last_error())
        owner = k.OpenProcess(0x100000, False, parent)  # SYNCHRONIZE
        handles.append(owner)
        print('Watchdog ready (Windows Job Object)', flush=True)
        while owner and k.WaitForSingleObject(owner, 500) == 0x102:  # WAIT_TIMEOUT
            if k.WaitForSingleObject(child, 0) != 0x102:
                break
    finally:
        # Closing the job kills every remaining descendant, even if the server exited.
        for handle in handles:
            if handle:
                k.CloseHandle(handle)
else:
    def exists(pid):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def group_exists():
        try:
            os.killpg(server, 0)
            return True
        except ProcessLookupError:
            return False

    print('Watchdog ready (POSIX process group)', flush=True)
    while exists(parent) and group_exists():
        # Linux zombies have exited but can linger until their parent reaps them.
        if sys.platform == 'linux':
            try:
                if open(f'/proc/{parent}/stat').read().split(') ', 1)[1].startswith('Z'):
                    break
            except FileNotFoundError:
                break
        time.sleep(0.5)
    if group_exists():
        try:
            os.killpg(server, signal.SIGTERM)
            time.sleep(2)
            os.killpg(server, signal.SIGKILL)
        except ProcessLookupError:
            pass

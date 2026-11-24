#!/usr/bin/env python3
"""oscompat: the operating-system primitives the maker uses that POSIX and Windows spell differently.

On POSIX every function here is exactly the call the maker made before this module existed (a new session per tool
and `killpg`, `flock`, `O_NOFOLLOW`, `S_ISLNK`), so POSIX behaviour does not change. On Windows (t_9b8f56f0):

- **Process trees.** A tool starts suspended in a new process group with no console window, is put into a Job Object
  of its own (`KILL_ON_JOB_CLOSE`) and only then resumed, so every process it starts is in the job from its first
  instruction. "Signal the group" terminates the job: Windows has no SIGTERM for a console-less process, so a tool stop
  on Windows is immediate (no grace period). A job that cannot be created or assigned is refused (the tool is killed and
  `OSError` raised): a tool never runs without its tree kill. When the sidecar dies its job handles close and the kernel
  kills every tool (the Windows counterpart of PR_SET_PDEATHSIG).
- **Locks.** `msvcrt.locking` on byte 0 of the lock file (per handle, like `flock` per open file description).
- **Links.** A link is a symlink **or any name-surrogate reparse point** (a junction, a volume mount point): `lstat`
  reports a junction as a plain directory, so `S_ISLNK` alone would miss it.
- **No-follow opens.** Windows has no `O_NOFOLLOW`: an existing file is `lstat`ed (refused when it is a link), opened,
  and `fstat`ed; the open is refused unless the descriptor is the same file (volume serial + file index) the `lstat`
  saw, so a name swapped for a link between the two calls is refused, never followed. An `O_CREAT | O_EXCL` open needs
  no check (CREATE_NEW fails on any existing name, a link included).
- **Held directories.** `hold_dir` opens a directory handle that does not share delete access (and does not follow a
  reparse point): while it is open nobody can rename or remove that directory, nor (NTFS) any directory above it. The
  output tree (zipout) holds every directory it writes through this way, in place of POSIX's directory descriptors.
- **Names.** `windows_unsafe_name` is true for the device names (CON, NUL, COM1, ...), a trailing dot or space and the
  characters Windows forbids; the output tree refuses such a name on Windows.

Stdlib only (ctypes on Windows).
"""

import errno
import os
import signal
import stat
import subprocess
import sys
import threading
import time
import weakref

WINDOWS = os.name == "nt"

# the hard-kill signal: Windows has none (`Popen.send_signal(SIGTERM)` is TerminateProcess there)
SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)

_NAME_SURROGATE = 0x20000000                 # IsReparseTagNameSurrogate: the reparse point names another entity
_REPARSE_POINT = 0x400                       # FILE_ATTRIBUTE_REPARSE_POINT


# ---- links ----------------------------------------------------------------------------------------------------------

def is_link(st):
    """True when the `lstat` result @p st is a link: a symlink, or on Windows a name-surrogate reparse point (a
    junction or a mount point; `lstat` reports those as directories)."""
    if stat.S_ISLNK(st.st_mode):
        return True
    return WINDOWS and bool(getattr(st, "st_reparse_tag", 0) & _NAME_SURROGATE)


def islink(path):
    """`os.path.islink` that also sees Windows junctions and mount points; False when @p path cannot be `lstat`ed."""
    if not WINDOWS:
        return os.path.islink(path)
    try:
        return is_link(os.lstat(path))
    except (OSError, ValueError):
        return False


def same_file(a, b):
    """True when the stat results @p a and @p b are the same file (device + inode; volume serial + file index)."""
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def open_nofollow(path, flags, mode=0o777, dir_fd=None):
    """`os.open(path, flags | O_NOFOLLOW, mode, dir_fd=dir_fd)`. On Windows (no `O_NOFOLLOW`, no `dir_fd`) @p flags
    must be read-only or `O_CREAT | O_EXCL`; a read open is checked as the module docstring says. `OSError` (`ELOOP`)
    for a link."""
    if not WINDOWS:
        return os.open(path, flags | os.O_NOFOLLOW, mode, dir_fd=dir_fd)
    if dir_fd is not None:
        raise NotImplementedError("dir_fd is not available on Windows")
    flags |= os.O_BINARY | os.O_NOINHERIT
    if flags & os.O_CREAT:
        if not flags & os.O_EXCL:
            raise ValueError("open_nofollow: O_CREAT needs O_EXCL on Windows")
        return os.open(path, flags, mode)            # CREATE_NEW: fails on any existing name, a link included
    if flags & (os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_APPEND):
        raise ValueError("open_nofollow: only read opens (or O_CREAT | O_EXCL) on Windows")
    before = os.lstat(path)
    if is_link(before):
        raise OSError(errno.ELOOP, "is a link", path)
    fd = os.open(path, flags, mode)
    try:
        if not same_file(os.fstat(fd), before):
            raise OSError(errno.ELOOP, "changed while it was opened", path)
    except BaseException:
        os.close(fd)
        raise
    return fd


# ---- names ----------------------------------------------------------------------------------------------------------

_DEVICE_NAMES = ({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                 | {"%s%s" % (p, c) for p in ("COM", "LPT") for c in "0123456789¹²³"})
_FORBIDDEN_CHARS = set('<>:"/\\|?*')


def windows_unsafe_name(name):
    """True when the single path component @p name cannot be a plain file name on Windows: a device name (also with an
    extension: `CON.SVF`), a trailing dot or space, a forbidden character or a control character."""
    if not name or name in (".", ".."):
        return True
    if name[-1] in ". " or any(c in _FORBIDDEN_CHARS or ord(c) < 32 for c in name):
        return True
    return name.split(".", 1)[0].rstrip(" ").upper() in _DEVICE_NAMES


# ---- locks ----------------------------------------------------------------------------------------------------------

def lock(fd, blocking=True):
    """An exclusive lock on the open lock file @p fd (`flock`; Windows: `msvcrt.locking` of byte 0). Non-blocking:
    `OSError` when another holder has it."""
    if not WINDOWS:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    import msvcrt
    while True:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if not blocking or exc.errno not in (errno.EACCES, errno.EDEADLK):
                raise
        time.sleep(0.02)


def unlock(fd):
    """Release @p fd's lock (`flock(LOCK_UN)`; Windows: unlock byte 0)."""
    if not WINDOWS:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    import msvcrt
    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


# ---- Windows API ----------------------------------------------------------------------------------------------------

if WINDOWS:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                      "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BasicLimit(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    def _proto(name, restype, *argtypes, dll=None):
        fn = getattr(dll or _k32, name)
        fn.restype = restype
        fn.argtypes = argtypes
        return fn

    _CreateJobObjectW = _proto("CreateJobObjectW", wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCWSTR)
    _SetInformationJobObject = _proto("SetInformationJobObject", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
                                      wintypes.LPVOID, wintypes.DWORD)
    _AssignProcessToJobObject = _proto("AssignProcessToJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE)
    _TerminateJobObject = _proto("TerminateJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
    _CloseHandle = _proto("CloseHandle", wintypes.BOOL, wintypes.HANDLE)
    _OpenProcess = _proto("OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _TerminateProcess = _proto("TerminateProcess", wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
    _WaitForSingleObject = _proto("WaitForSingleObject", wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
    _GetProcessTimes = _proto("GetProcessTimes", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                              ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                              ctypes.POINTER(wintypes.FILETIME))
    _CreateFileW = _proto("CreateFileW", wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                          wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _NtResumeProcess = _proto("NtResumeProcess", ctypes.c_long, wintypes.HANDLE, dll=_ntdll)
    _GetFileInformationByHandleEx = _proto("GetFileInformationByHandleEx", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
                                           wintypes.LPVOID, wintypes.DWORD)

    class _AttributeTagInfo(ctypes.Structure):
        _fields_ = [("FileAttributes", wintypes.DWORD), ("ReparseTag", wintypes.DWORD)]
    _FILE_ATTRIBUTE_TAG_INFO = 9

    _INVALID_HANDLE = wintypes.HANDLE(-1).value
    _JOB_EXTENDED_LIMIT = 9                          # JobObjectExtendedLimitInformation
    _KILL_ON_JOB_CLOSE = 0x2000
    _DIE_ON_UNHANDLED_EXCEPTION = 0x400              # no error-report dialog holds a crashed tool open
    _CREATE_SUSPENDED = 0x4
    _CREATE_NEW_PROCESS_GROUP = 0x200
    _CREATE_NO_WINDOW = 0x08000000
    _SYNCHRONIZE = 0x100000
    _PROCESS_TERMINATE = 0x1
    _PROCESS_QUERY_LIMITED = 0x1000
    _WAIT_TIMEOUT = 0x102
    _INFINITE = 0xFFFFFFFF
    _ERROR_INVALID_PARAMETER = 87
    _GENERIC_READ = 0x80000000
    _FILE_SHARE_READ, _FILE_SHARE_WRITE = 0x1, 0x2
    _OPEN_EXISTING = 3
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000         # needed to open a directory
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000       # the link itself, never its target

    def _last_error(what):
        code = ctypes.get_last_error()
        exc = ctypes.WinError(code)
        exc.strerror = "%s: %s" % (what, exc.strerror)
        return exc

    def _new_job():
        job = _CreateJobObjectW(None, None)
        if not job:
            raise _last_error("CreateJobObject")
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE | _DIE_ON_UNHANDLED_EXCEPTION
        if not _SetInformationJobObject(job, _JOB_EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)):
            exc = _last_error("SetInformationJobObject")
            _CloseHandle(job)
            raise exc
        return job


# ---- process trees --------------------------------------------------------------------------------------------------

def popen_group(argv, **kwargs):
    """`subprocess.Popen(argv, **kwargs)` with the child at the head of a process tree the maker can kill at once:
    POSIX a new session (`start_new_session=True`, so the pid is the group id); Windows a Job Object (see the module
    docstring)."""
    if not WINDOWS:
        return subprocess.Popen(argv, start_new_session=True, **kwargs)
    flags = kwargs.pop("creationflags", 0) | _CREATE_SUSPENDED | _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW
    job = _new_job()
    try:
        proc = subprocess.Popen(argv, creationflags=flags, **kwargs)
    except BaseException:
        _CloseHandle(job)
        raise
    try:
        if not _AssignProcessToJobObject(job, int(proc._handle)):
            raise _last_error("AssignProcessToJobObject")
        status = _NtResumeProcess(int(proc._handle))
        if status != 0:
            raise OSError(errno.EIO, "NtResumeProcess failed (status 0x%08x)" % (status & 0xFFFFFFFF))
    except BaseException:
        try:
            proc.kill()                                # never left running (or suspended) outside its job
            proc.wait()
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
            _CloseHandle(job)
        raise
    proc._svf_job = job
    weakref.finalize(proc, _CloseHandle, job)          # the last handle: KILL_ON_JOB_CLOSE takes any straggler
    return proc


def signal_group(proc, sig):
    """Send @p sig to the process group @p proc leads (`os.killpg`); `OSError` when it is gone. Windows: the tool's job
    is terminated, whatever @p sig is (no graceful stop exists for a console-less process)."""
    if not WINDOWS:
        os.killpg(proc.pid, sig)
        return
    job = getattr(proc, "_svf_job", None)
    if job is None:
        raise OSError(errno.ESRCH, "no job object for this process")
    if not _TerminateJobObject(job, 1):
        raise _last_error("TerminateJobObject")


def kill_registered(pid):
    """Kill what a dead run registered under @p pid (its group id = its pid): POSIX `killpg(pid, SIGKILL)`. Windows:
    `TerminateProcess` of that pid (its job died with the sidecar that held it, taking the tool's children with it).
    `OSError` when it cannot be done."""
    if not WINDOWS:
        os.killpg(pid, signal.SIGKILL)
        return
    handle = _OpenProcess(_PROCESS_TERMINATE, False, pid)
    if not handle:
        raise _last_error("OpenProcess")
    try:
        if not _TerminateProcess(handle, 1):
            raise _last_error("TerminateProcess")
    finally:
        _CloseHandle(handle)


def process_alive(pid):
    """Windows: True when process @p pid exists and has not exited (an access-denied process counts as alive)."""
    handle = _OpenProcess(_SYNCHRONIZE | _PROCESS_QUERY_LIMITED, False, pid)
    if not handle:
        return ctypes.get_last_error() != _ERROR_INVALID_PARAMETER
    try:
        return _WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        _CloseHandle(handle)


def process_start_time(pid):
    """Windows: process @p pid's creation time (FILETIME, 100 ns units) as text, or None."""
    handle = _OpenProcess(_PROCESS_QUERY_LIMITED, False, pid)
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not _GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            return None
        return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
    finally:
        _CloseHandle(handle)


def watch_process(pid, on_exit, name="svf-maker-process-watch"):
    """Windows: a daemon thread that calls @p on_exit() once process @p pid has exited (at once when it cannot be
    opened: it is gone already). The handle is opened here, before the thread starts, so a pid reused later is never
    mistaken for it."""
    handle = _OpenProcess(_SYNCHRONIZE, False, pid)

    def wait():
        if handle:
            _WaitForSingleObject(handle, _INFINITE)
            _CloseHandle(handle)
        on_exit()
    thread = threading.Thread(target=wait, daemon=True, name=name)
    thread.start()
    return thread


def request_stop():
    """Ask this process to stop as SIGTERM would: POSIX `kill(getpid(), SIGTERM)`; Windows simulates SIGTERM in the main
    thread (`os.kill` there would be TerminateProcess, with no cleanup)."""
    if not WINDOWS:
        os.kill(os.getpid(), signal.SIGTERM)
        return
    import _thread
    _thread.interrupt_main(signal.SIGTERM)


# ---- held directories (Windows) -------------------------------------------------------------------------------------

def hold_dir(path):
    """Windows: a descriptor of directory @p path that keeps it (and, on NTFS, every directory above it) from being
    renamed or removed while it is open, and never follows a reparse point. `OSError` (`ELOOP`) when @p path is a link,
    (`ENOTDIR`) when it is not a directory."""
    handle = _CreateFileW(path, _GENERIC_READ, _FILE_SHARE_READ | _FILE_SHARE_WRITE, None, _OPEN_EXISTING,
                          _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT, None)
    if handle == _INVALID_HANDLE or not handle:
        exc = _last_error("CreateFile")
        exc.filename = path
        raise exc
    try:
        tag = _AttributeTagInfo()
        if not _GetFileInformationByHandleEx(handle, _FILE_ATTRIBUTE_TAG_INFO, ctypes.byref(tag), ctypes.sizeof(tag)):
            raise _last_error("GetFileInformationByHandleEx")
        if tag.FileAttributes & _REPARSE_POINT and tag.ReparseTag & _NAME_SURROGATE:
            raise OSError(errno.ELOOP, "is a link", path)
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        _CloseHandle(handle)
        raise
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise OSError(errno.ENOTDIR, "not a folder", path)
    except BaseException:
        os.close(fd)
        raise
    return fd

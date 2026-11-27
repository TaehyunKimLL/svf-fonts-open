#!/usr/bin/env python3
"""oscompat: the operating-system primitives the maker uses that POSIX and Windows spell differently.

On POSIX every function here is exactly the call the maker made before this module existed (a new session per tool
and `killpg`, `flock`, `O_NOFOLLOW`, `S_ISLNK`), so POSIX behaviour does not change. On Windows (t_9b8f56f0):

- **Process trees.** A tool starts suspended in a new process group with no console window, is put into a Job Object
  of its own (`KILL_ON_JOB_CLOSE`) and only then resumed, so every process it starts is in the job from its first
  instruction. "Signal the group" terminates the job: Windows has no SIGTERM for a console-less process, so a tool stop
  on Windows is immediate (no grace period). A job that cannot be created or assigned is refused (the tool is killed and
  `OSError` raised): a tool never runs without its tree kill. When the sidecar dies its job handles close and the kernel
  kills every tool (the Windows counterpart of PR_SET_PDEATHSIG). The sidecar itself runs in a job of its own
  (`contain_children`), so a tool killed with it between creation and assignment does not survive it either.
- **Locks.** `msvcrt.locking` of one byte far past the lock file's end (per handle, like `flock` per open file
  description; past the end, so the file itself stays readable). A sharing conflict on a replace or a read
  (`retry_sharing`) is retried briefly: Windows refuses to replace a file another thread has open.
- **Links.** A link is a symlink **or any name-surrogate reparse point** (a junction, a volume mount point): `lstat`
  reports a junction as a plain directory, so `S_ISLNK` alone would miss it.
- **No-follow opens.** Windows has no `O_NOFOLLOW`: the file is opened with `FILE_FLAG_OPEN_REPARSE_POINT` (the open
  itself never follows a link at the last name: a dangling link makes `CREATE_NEW` fail, a link is never contacted)
  and the handle's reparse tag is checked: a name surrogate (a symlink, a junction) is refused. A file that is another
  kind of reparse point (a deduplicated or cloud placeholder file, which only reads through its filter) is opened again
  normally and must be the same file (volume serial + file index). With `dir_fd` the name is opened relative to that
  held directory's handle (`NtCreateFile`, `OBJ_DONT_REPARSE`), never by a path through it.
- **Held directories.** `hold_dir` / `hold_dir_at` open a directory handle that does not share write or delete access
  (and does not follow a reparse point): while it is open nobody can rename or remove that directory, nor (NTFS) any
  directory above it, nor open it for writing. The output tree (zipout) makes and holds every directory it writes
  through relative to its parent's held handle (`hold_dir_at`), in place of POSIX's `mkdirat`/`openat`, and creates
  its files relative to the held handle, so a folder turned into a junction in place is never written through.
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
    """`os.open(path, flags | O_NOFOLLOW, mode, dir_fd=dir_fd)`. On Windows @p flags must be read-only or
    `O_CREAT | O_EXCL` (+ `O_WRONLY` / `O_RDWR`), and with @p dir_fd (a `hold_dir` descriptor) @p path must be one
    name; the open is done as the module docstring says. `OSError` (`ELOOP`) for a link."""
    if not WINDOWS:
        return os.open(path, flags | os.O_NOFOLLOW, mode, dir_fd=dir_fd)
    create = bool(flags & os.O_CREAT)
    if create and not flags & os.O_EXCL:
        raise ValueError("open_nofollow: O_CREAT needs O_EXCL on Windows")
    if not create and flags & (os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_APPEND):
        raise ValueError("open_nofollow: only read opens (or O_CREAT | O_EXCL) on Windows")
    if flags & os.O_WRONLY:
        access = _GENERIC_WRITE | _FILE_READ_ATTRIBUTES
    elif flags & os.O_RDWR:
        access = _GENERIC_READ | _GENERIC_WRITE
    else:
        access = _GENERIC_READ
    attrs = _FILE_ATTRIBUTE_NORMAL if mode & stat.S_IWRITE else _FILE_ATTRIBUTE_READONLY   # as os.open does
    handle = _open_handle(path, dir_fd, access, create, False, attrs, True)
    try:
        tag = _attribute_tag(handle)
        if tag.FileAttributes & _REPARSE_POINT and tag.ReparseTag & _NAME_SURROGATE:
            raise OSError(errno.ELOOP, "is a link", path)
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        _CloseHandle(handle)
        raise
    if create or not tag.FileAttributes & _REPARSE_POINT:
        return fd
    # a reparse point that names nothing else (dedup, cloud placeholder): its data reads through its filter, so it is
    # opened again normally, and must be the same file
    try:
        first = os.fstat(fd)
    finally:
        os.close(fd)
    handle = _open_handle(path, dir_fd, access, False, False, attrs, False)
    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    try:
        again = os.fstat(fd)
        if not first.st_ino or not same_file(again, first):
            raise OSError(errno.ELOOP, "changed while it was opened", path)
    except BaseException:
        os.close(fd)
        raise
    return fd


# ---- sharing retries ----------------------------------------------------------------------------------------------

SHARING_RETRY_S = 2.0
_SHARING_WINERRORS = (5, 32, 33)             # ERROR_ACCESS_DENIED (a delete pending), SHARING_VIOLATION, LOCK_VIOLATION


def retry_sharing(fn, *args, **kwargs):
    """`fn(*args, **kwargs)`. Windows: a `PermissionError` that is a sharing conflict (another thread or process has the
    file open, or is replacing it, at this moment: a reader of job.json while the worker writes it) is retried for up to
    `SHARING_RETRY_S` seconds; POSIX has no such conflict and calls once."""
    if not WINDOWS:
        return fn(*args, **kwargs)
    end = time.monotonic() + SHARING_RETRY_S
    while True:
        try:
            return fn(*args, **kwargs)
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in _SHARING_WINERRORS or time.monotonic() >= end:
                raise
        time.sleep(0.01)


def replace(src, dst):
    """`os.replace(src, dst)`, retried on Windows while the target is open elsewhere (`retry_sharing`)."""
    return retry_sharing(os.replace, src, dst)


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

# Windows byte-range locks are mandatory: a lock on byte 0 would make the (empty) lock file unreadable to everyone else,
# so the locked byte lies far past its end (locking beyond the end of a file is allowed).
_LOCK_OFFSET = 1 << 30


def lock(fd, blocking=True):
    """An exclusive lock on the open lock file @p fd (`flock`; Windows: `msvcrt.locking` of one byte at `_LOCK_OFFSET`).
    Non-blocking: `OSError` when another holder has it."""
    if not WINDOWS:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    import msvcrt
    while True:
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if not blocking or exc.errno not in (errno.EACCES, errno.EDEADLK):
                raise
        time.sleep(0.02)


def unlock(fd):
    """Release @p fd's lock (`flock(LOCK_UN)`; Windows: unlock the byte at `_LOCK_OFFSET`)."""
    if not WINDOWS:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    import msvcrt
    os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
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
    _GetCurrentProcess = _proto("GetCurrentProcess", wintypes.HANDLE)
    class _ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    _CreateToolhelp32Snapshot = _proto("CreateToolhelp32Snapshot", wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)
    _Process32FirstW = _proto("Process32FirstW", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(_ProcessEntry))
    _Process32NextW = _proto("Process32NextW", wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(_ProcessEntry))
    _PeekNamedPipe = _proto("PeekNamedPipe", wintypes.BOOL, wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                            wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID)
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
    _GENERIC_READ, _GENERIC_WRITE = 0x80000000, 0x40000000
    _FILE_READ_ATTRIBUTES = 0x80
    _FILE_SHARE_READ, _FILE_SHARE_WRITE = 0x1, 0x2
    _CREATE_NEW, _OPEN_EXISTING = 1, 3
    _FILE_ATTRIBUTE_READONLY, _FILE_ATTRIBUTE_NORMAL = 0x1, 0x80
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000         # needed to open a directory
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000       # the link itself, never its target
    # NtCreateFile
    _FILE_OPEN, _FILE_CREATE, _FILE_OPEN_IF = 1, 2, 3
    _FILE_DIRECTORY_FILE, _FILE_SYNCHRONOUS_IO_NONALERT, _FILE_NON_DIRECTORY_FILE = 0x1, 0x20, 0x40
    _FILE_OPEN_REPARSE_POINT = 0x00200000
    _OBJ_CASE_INSENSITIVE, _OBJ_DONT_REPARSE = 0x40, 0x1000
    _STATUS_INVALID_PARAMETER = 0xC000000D
    _STATUS_REPARSE_POINT_ENCOUNTERED = 0xC000050B

    class _UnicodeString(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", ctypes.c_void_p)]

    class _ObjectAttributes(ctypes.Structure):
        _fields_ = [("Length", wintypes.ULONG), ("RootDirectory", wintypes.HANDLE),
                    ("ObjectName", ctypes.POINTER(_UnicodeString)), ("Attributes", wintypes.ULONG),
                    ("SecurityDescriptor", ctypes.c_void_p), ("SecurityQualityOfService", ctypes.c_void_p)]

    class _IoStatusBlock(ctypes.Structure):
        _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

    _NtCreateFile = _proto("NtCreateFile", ctypes.c_long, ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                           ctypes.POINTER(_ObjectAttributes), ctypes.POINTER(_IoStatusBlock), ctypes.c_void_p,
                           wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p,
                           wintypes.ULONG, dll=_ntdll)
    _RtlNtStatusToDosError = _proto("RtlNtStatusToDosError", wintypes.ULONG, wintypes.ULONG, dll=_ntdll)

    def _last_error(what):
        code = ctypes.get_last_error()
        exc = ctypes.WinError(code)
        exc.strerror = "%s: %s" % (what, exc.strerror)
        return exc

    def _attribute_tag(handle):
        tag = _AttributeTagInfo()
        if not _GetFileInformationByHandleEx(handle, _FILE_ATTRIBUTE_TAG_INFO, ctypes.byref(tag), ctypes.sizeof(tag)):
            raise _last_error("GetFileInformationByHandleEx")
        return tag

    def _nt_open_at(dir_fd, name, access, share, disposition, options, attrs, no_reparse=True):
        """`NtCreateFile` of the single name @p name relative to the held directory @p dir_fd, never following a
        reparse point (`OBJ_DONT_REPARSE`, `FILE_OPEN_REPARSE_POINT`) while @p no_reparse; the handle, or `OSError`."""
        if not name or name in (".", "..") or any(c in name for c in '\\/:'):
            raise ValueError("not a single name: %r" % (name,))
        buf = ctypes.create_unicode_buffer(name)
        size = (len(buf) - 1) * ctypes.sizeof(ctypes.c_wchar)
        uname = _UnicodeString(size, size, ctypes.cast(buf, ctypes.c_void_p))
        root = msvcrt.get_osfhandle(dir_fd)
        tries = (_OBJ_CASE_INSENSITIVE | _OBJ_DONT_REPARSE, _OBJ_CASE_INSENSITIVE) if no_reparse else (
            _OBJ_CASE_INSENSITIVE,)
        for oattrs in tries:
            oa = _ObjectAttributes(ctypes.sizeof(_ObjectAttributes), root, ctypes.pointer(uname), oattrs, None, None)
            handle, iosb = wintypes.HANDLE(), _IoStatusBlock()
            status = _NtCreateFile(ctypes.byref(handle), access | _SYNCHRONIZE, ctypes.byref(oa), ctypes.byref(iosb),
                                   None, attrs, share, disposition,
                                   options | _FILE_SYNCHRONOUS_IO_NONALERT
                                   | (_FILE_OPEN_REPARSE_POINT if no_reparse else 0), None, 0)
            status &= 0xFFFFFFFF
            if status < 0x80000000:
                return handle.value
            if status != _STATUS_INVALID_PARAMETER:     # OBJ_DONT_REPARSE needs Windows 10 1703: retried without it
                break                                   # (one name below a held handle: nothing else to traverse)
        if status == _STATUS_REPARSE_POINT_ENCOUNTERED:
            raise OSError(errno.ELOOP, "is a link", name)
        exc = ctypes.WinError(_RtlNtStatusToDosError(status))
        exc.filename = name
        raise exc

    def _open_handle(path, dir_fd, access, create, directory, attrs, no_reparse):
        """A handle on @p path (one name below the held @p dir_fd when given): created new (@p create) or opened,
        a file or (@p directory) a folder, never following a reparse point at the last name while @p no_reparse."""
        share = _FILE_SHARE_READ if directory else _FILE_SHARE_READ | _FILE_SHARE_WRITE
        if dir_fd is not None:
            options = _FILE_DIRECTORY_FILE if directory else _FILE_NON_DIRECTORY_FILE
            return _nt_open_at(dir_fd, path, access, share, (_FILE_OPEN_IF if directory else _FILE_CREATE)
                               if create else _FILE_OPEN, options, attrs, no_reparse)
        flags = attrs | (_FILE_FLAG_OPEN_REPARSE_POINT if no_reparse else 0) | (
            _FILE_FLAG_BACKUP_SEMANTICS if directory else 0)
        handle = _CreateFileW(path, access, share, None, _CREATE_NEW if create else _OPEN_EXISTING, flags, None)
        if handle == _INVALID_HANDLE or not handle:
            exc = _last_error("CreateFile")
            exc.filename = path
            raise exc
        return handle

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


_self_job = []


def contain_children():
    """Windows: put this process into a Job Object of its own (`KILL_ON_JOB_CLOSE`), held until it exits, so every
    process it starts is inside a job from its creation: when this process dies, however, the kernel kills them all,
    a tool still suspended between its creation and `AssignProcessToJobObject` (`popen_group`) included. The tool jobs
    nest inside it (Windows 8+). `OSError` when the job cannot be made or joined (the caller decides); POSIX: nothing
    (PR_SET_PDEATHSIG and the tool registry cover it)."""
    if not WINDOWS or _self_job:
        return
    job = _new_job()
    if not _AssignProcessToJobObject(job, _GetCurrentProcess()):
        exc = _last_error("AssignProcessToJobObject (self)")
        _CloseHandle(job)
        raise exc
    _self_job.append(job)                                # never closed: it closes when this process ends


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


def _descendants(pid):
    """Windows: the pids below @p pid (children first found, deepest last), by the parent links of a process snapshot.
    A child must have been created after its parent: a parent pid that was reused by an older process links nothing."""
    snap = _CreateToolhelp32Snapshot(0x2, 0)               # TH32CS_SNAPPROCESS
    if snap == _INVALID_HANDLE or not snap:
        return []
    children = {}
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        ok = _Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            children.setdefault(entry.th32ParentProcessID, []).append(entry.th32ProcessID)
            ok = _Process32NextW(snap, ctypes.byref(entry))
    finally:
        _CloseHandle(snap)
    out, todo = [], [pid]
    while todo:
        parent = todo.pop()
        born = process_start_time(parent)
        for child in children.get(parent, ()):
            if child in out or child == pid:
                continue
            started = process_start_time(child)
            if born is None or started is None or int(started) < int(born):
                continue
            out.append(child)
            todo.append(child)
    return out


def _terminate(pid):
    handle = _OpenProcess(_PROCESS_TERMINATE, False, pid)
    if not handle:
        raise _last_error("OpenProcess")
    try:
        if not _TerminateProcess(handle, 1):
            raise _last_error("TerminateProcess")
    finally:
        _CloseHandle(handle)


def kill_registered(pid):
    """Kill what a dead run registered under @p pid (its group id = its pid): POSIX `killpg(pid, SIGKILL)`. Windows:
    `TerminateProcess` of that pid and of every process below it (by the snapshot's parent links; normally they died
    with the dead sidecar's Job Objects already). `OSError` when the pid itself cannot be terminated."""
    if not WINDOWS:
        os.killpg(pid, signal.SIGKILL)
        return
    below = _descendants(pid)
    try:
        _terminate(pid)
    finally:                                             # the descendants too when the root has just exited
        for child in below:
            try:
                _terminate(child)
            except OSError:
                pass


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


def wait_stdin_eof(poll_s=0.5):
    """Return once stdin has reached end of file (POSIX: read until EOF, what is read is ignored). Windows: the pipe
    is polled with PeekNamedPipe and never read, because a pending synchronous read on a pipe holds up other calls on
    that handle (a child process could not be created meanwhile). A stdin that is not a pipe (a console, NUL, a file)
    is never "at its end" there: the call then blocks for good, as an unwatched stdin would."""
    if not WINDOWS:
        try:
            while sys.stdin.buffer.read1(4096):
                pass
        except (OSError, ValueError, AttributeError):
            pass
        return
    try:
        handle = msvcrt.get_osfhandle(0)
    except OSError:
        handle = None
    avail = wintypes.DWORD()
    while True:
        if handle is not None and not _PeekNamedPipe(handle, None, 0, None, ctypes.byref(avail), None):
            if ctypes.get_last_error() in (109, 232, 6):  # BROKEN_PIPE, NO_DATA (closing), INVALID_HANDLE: the writer is gone
                return
            handle = None                                 # not a pipe: nothing to watch
        if handle is None:
            threading.Event().wait()
        time.sleep(poll_s)


def request_stop():
    """Ask this process to stop as SIGTERM would: POSIX `kill(getpid(), SIGTERM)`; Windows simulates SIGINT in the main
    thread (`os.kill` there would be TerminateProcess, with no cleanup). SIGINT, not SIGTERM: only a simulated SIGINT
    also sets the interrupt event that wakes a main thread blocked in a wait (`time.sleep`); the server binds both
    signals to the same stop."""
    if not WINDOWS:
        os.kill(os.getpid(), signal.SIGTERM)
        return
    import _thread
    _thread.interrupt_main(signal.SIGINT)


# ---- held directories (Windows) -------------------------------------------------------------------------------------

def hold_dir(path):
    """Windows: a descriptor of directory @p path that keeps it (and, on NTFS, every directory above it) from being
    renamed, removed or opened for writing while it is open, and never follows a reparse point. `OSError` (`ELOOP`)
    when @p path is a link, (`ENOTDIR`) when it is not a directory."""
    return _hold(path, None, False)


def hold_dir_at(dir_fd, name):
    """Windows: `hold_dir` of the folder @p name in the held folder @p dir_fd, made there first when it is missing
    (`mkdirat` + `openat(O_NOFOLLOW | O_DIRECTORY)` in one call, relative to the held handle: no path is walked, so a
    folder above that was turned into a junction in place is never gone through)."""
    return _hold(name, dir_fd, True)


def _hold(path, dir_fd, create):
    handle = _open_handle(path, dir_fd, _GENERIC_READ, create, True, 0, True)
    try:
        tag = _attribute_tag(handle)
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


def fd_is_link(fd):
    """Windows: True when the open file @p fd is now a name-surrogate reparse point (a folder turned into a junction
    in place after it was opened)."""
    tag = _attribute_tag(msvcrt.get_osfhandle(fd))
    return bool(tag.FileAttributes & _REPARSE_POINT and tag.ReparseTag & _NAME_SURROGATE)

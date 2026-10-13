"""LARK benchmark-only Linux guard, Apache-2.0. Installed before policy load."""
import ctypes
import errno


def restrict():
    lib = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    lib.seccomp_init.argtypes = [ctypes.c_uint32]
    lib.seccomp_init.restype = ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    lib.seccomp_load.argtypes = [ctypes.c_void_p]
    lib.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = lib.seccomp_init(0x7fff0000)
    if not ctx:
        raise RuntimeError('seccomp initialization failed')
    try:
        for name in ('socket', 'socketpair', 'connect', 'bind', 'listen', 'accept',
                     'accept4', 'sendto', 'sendmsg', 'sendmmsg', 'execve', 'execveat',
                     'io_uring_setup'):
            number = lib.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and lib.seccomp_rule_add(ctx, 0x50000 | errno.EPERM, number, 0):
                raise RuntimeError('seccomp rule failed: ' + name)
        if lib.seccomp_load(ctx):
            raise RuntimeError('seccomp installation failed')
    finally:
        lib.seccomp_release(ctx)


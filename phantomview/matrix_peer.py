"""Connect to a matrix broker under a dedicated Linux service identity."""

import contextlib
import os
import socket
import subprocess
import sys

_CONNECT = """
import os
import socket
import sys

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as broker:
    broker.settimeout(5)
    broker.connect(sys.argv[1])
    with socket.socket(fileno=1) as control:
        socket.send_fds(control, [b'm'], [broker.fileno()])
"""


@contextlib.contextmanager
def connect(path, uid, gid):
    """Pass a connected fd back to the viewer, which retains HTTP authorization."""
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or type(uid) is not int
        or uid <= 0
        or type(gid) is not int
        or gid <= 0
        or not isinstance(path, str)
        or not os.path.isabs(path)
    ):
        raise ValueError("matrix connector unavailable")
    reader, writer = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    fds = []
    try:
        with reader, writer:
            reader.settimeout(5)
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-B", "-c", _CONNECT, path],
                user=uid,
                group=gid,
                extra_groups=[],
                env={"PATH": "/usr/bin:/bin"},
                cwd="/",
                stdin=subprocess.DEVNULL,
                stdout=writer,
                stderr=subprocess.DEVNULL,
                timeout=6,
                check=False,
            )
            if result.returncode:
                raise OSError("matrix connector failed")
            data, fds, flags, _ = socket.recv_fds(reader, 1, 1, socket.MSG_CMSG_CLOEXEC)
            if (
                data != b"m"
                or len(fds) != 1
                or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC)
            ):
                raise OSError("invalid matrix socket handoff")
        with socket.socket(fileno=fds[0]) as stream:
            fds.clear()
            yield stream
    except subprocess.TimeoutExpired as exc:
        raise OSError("matrix connector timed out") from exc
    finally:
        for fd in fds:
            os.close(fd)

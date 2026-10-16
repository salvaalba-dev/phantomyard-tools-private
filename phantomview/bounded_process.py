"""Linux pipe and process-group lifecycle; no model, identity or delivery policy."""
import os
import selectors
import signal
import subprocess
import sys
import time


def _signal_group(process, sig):
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def run(command, payload, *, cwd, deadline, cancelled, stderr_sink=None,
        environment=None, output_limit=64000, popen=subprocess.Popen):
    """Return bounded stdout, closing pipes and terminating the original group.

    The caller supplies trusted fixed argv/environment and a monotonic deadline.
    Descendants that deliberately escape the group require external containment;
    this library is not a cgroup or privilege boundary.
    """
    if (sys.platform != 'linux' or not isinstance(payload, bytes) or len(payload) > 65536
            or not callable(cancelled) or not 0 < output_limit <= 64000):
        raise RuntimeError('Native process unavailable')
    if cancelled() or time.monotonic() >= deadline:
        raise RuntimeError('Native process stopped')
    process = None
    selector = selectors.DefaultSelector()
    output, offset, exited = bytearray(), 0, None
    try:
        process = popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        start_new_session=True, close_fds=True, cwd=cwd, env=environment)
        for pipe, event in ((process.stdin, selectors.EVENT_WRITE),
                            (process.stdout, selectors.EVENT_READ), (process.stderr, selectors.EVENT_READ)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, event)
        while selector.get_map():
            now = time.monotonic()
            if cancelled() or now >= deadline:
                raise RuntimeError('Native process stopped')
            if process.poll() is not None:
                exited = exited or now
                if now - exited > 0.25:
                    raise RuntimeError('Native process left open pipes')
            for key, _ in selector.select(min(.05, max(0, deadline - now))):
                pipe = key.fileobj
                if pipe is process.stdin:
                    if offset < len(payload):
                        offset += os.write(pipe.fileno(), payload[offset:offset + 4096])
                    if offset == len(payload):
                        selector.unregister(pipe)
                        pipe.close()
                    continue
                part = os.read(pipe.fileno(), 4096)
                if not part:
                    selector.unregister(pipe)
                    pipe.close()
                elif pipe is process.stdout:
                    output.extend(part)
                    if len(output) > output_limit:
                        raise RuntimeError('Native process output exceeded bounds')
                elif stderr_sink is not None:
                    stderr_sink(part)
        while process.poll() is None:
            if cancelled() or time.monotonic() >= deadline:
                raise RuntimeError('Native process stopped')
            time.sleep(.05)
        if process.returncode != 0 or offset != len(payload) or cancelled() or time.monotonic() >= deadline:
            raise RuntimeError('Native process failed')
        return bytes(output)
    except (OSError, ValueError):
        raise RuntimeError('Native process failed') from None
    finally:
        selector.close()
        if process is not None:
            try:
                _signal_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    pass
                # Kill the original group even after its leader exited: a child
                # may still hold pipes or ignore TERM. Escaped sessions are outside
                # this guarantee and require operator-managed containment.
                _signal_group(process, signal.SIGKILL)
                process.wait(timeout=3)
            finally:
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe is not None:
                        pipe.close()

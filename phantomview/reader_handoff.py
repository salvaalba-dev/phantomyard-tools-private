"""Opt-in listener lifecycle sharing the reader's in-memory identified gate.

No CLI, environment variable or import starts this listener. Native channel
isolation, reviewed resources and backend authorization remain deployment gates.
"""
from pathlib import Path
import socket
import stat
import threading

from identified_access import IdentifiedGate
from trusted_handoff import PeerPolicy, bind_listener, serve_connection


class ReaderHandoff:
    def __init__(self, path, group_id, peer_policy, gate, *, actor=None):
        if not isinstance(gate, IdentifiedGate) or not isinstance(peer_policy, PeerPolicy):
            raise ValueError('An identified reader gate and kernel peer policy are required')
        self.path, self.group_id, self.peer_policy, self.gate = Path(path), group_id, peer_policy, gate
        if actor is not None:
            gate.issuer_links(actor)
        self.actor = actor
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._listener, self._connection, self._thread, self._identity = None, None, None, None
        self._started, self._failed = False, False

    @property
    def healthy(self):
        return self._started and not self._stop.is_set() and not self._failed and self._thread.is_alive()

    def start(self, server):
        """Start once, only when the HTTP reader holds this exact gate instance."""
        if self._started or self._stop.is_set():
            raise ValueError('A handoff runtime cannot be started twice or reused after close')
        if getattr(server, 'gate', None) is not self.gate:
            raise ValueError('Handoff and HTTP redemption must share the exact identified gate')
        self._listener = bind_listener(self.path, self.group_id)
        try:
            info = self.path.lstat()
            self._identity = (info.st_dev, info.st_ino, info.st_uid)
            self._thread = threading.Thread(target=self._run, name='phantomview-native-handoff', daemon=True)
            self._started = True
            self._thread.start()
        except BaseException:
            self.close()
            raise

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    connection, _ = self._listener.accept()
                except TimeoutError:
                    continue
                with self._lock:
                    if self._stop.is_set():
                        connection.close()
                        return
                    self._connection = connection
                try:
                    # One connection at a time bounds signing work and in-flight
                    # identity state; rejected peers never reach request reads.
                    serve_connection(connection, self.gate, self.peer_policy, actor=self.actor)
                finally:
                    with self._lock:
                        self._connection = None
        except Exception:
            # Never expose transport exception text, identities or credentials.
            if not self._stop.is_set():
                self._failed = True
        finally:
            self._listener.close()

    def close(self):
        """Interrupt I/O and remove only this runtime's unchanged socket inode."""
        self._stop.set()
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None and self._thread.ident is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise RuntimeError('Private handoff did not stop; reader shutdown is incomplete')
        if self._identity is not None:
            try:
                info = self.path.lstat()
                current = (info.st_dev, info.st_ino, info.st_uid)
                if stat.S_ISSOCK(info.st_mode) and current == self._identity:
                    self.path.unlink()
            except FileNotFoundError:
                pass

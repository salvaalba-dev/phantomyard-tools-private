"""Serve a configured matrix through the identified scoped viewer."""

import json
import os
import re
import socket
import struct

from matrix_peer import connect

_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_FIELDS = {
    "socket",
    "server_uid",
    "client_uid",
    "client_gid",
    "domain",
    "project_type",
    "scope_id",
}


def dispatch(handler, backend, path):
    from phantomdocs.view_matrix import MAX_MATRIX_BYTES
    from phantomdocs.view_matrix_broker import ACK, MAX_REQUEST, TIMEOUT, _line
    from phantomdocs.workflow_admission_config import _json
    from phantomdocs.workflow_audit_authority import project_category
    from phantomdocs.workflows import WorkflowError

    version = path.removeprefix("/api/matrix/")
    started = False
    try:
        config_path = os.environ.get("PHANTOMVIEW_MATRIX_PEER_ROUTES")
        if not config_path or not _VERSION.fullmatch(version):
            raise ValueError("matrix route unavailable")
        config = _json(config_path)
        if (
            not isinstance(config, dict)
            or set(config) != {"version", "routes"}
            or config["version"] != 2
            or not isinstance(config["routes"], dict)
            or len(config["routes"]) != 1
        ):
            raise ValueError("invalid matrix configuration")
        recipient, directory = backend.gate.identified_scope(handler.headers)
        actor = getattr(recipient, "persona", None)
        if (
            getattr(recipient, "human", None) is not None
            or actor not in config["routes"]
        ):
            raise ValueError("unexpected matrix recipient")
        route = config["routes"][actor]
        if (
            not isinstance(route, dict)
            or set(route) != _FIELDS
            or type(route["server_uid"]) is not int
            or route["server_uid"] != 0
        ):
            raise ValueError("invalid matrix route")

        def permitted(current, current_directory):
            org = current_directory.org
            project = route["scope_id"]
            resource = {
                "organization": org["organization"]["id"],
                "secret": False,
                "scope": {"id": project, "kind": "project"},
                "project": project,
                "category": project_category(
                    org, route["domain"], route["project_type"]
                ),
            }
            return current_directory.permits(current, resource)

        if not permitted(recipient, directory):
            raise ValueError("matrix scope denied")
        request = json.dumps({"version": version}).encode() + b"\n"
        if len(request) > MAX_REQUEST:
            raise ValueError("invalid matrix request")
        with connect(
            route["socket"], route["client_uid"], route["client_gid"]
        ) as connection:
            if (
                connection.family != socket.AF_UNIX
                or connection.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
                != socket.SOCK_STREAM
                or connection.getpeername() != route["socket"]
            ):
                raise ValueError("unexpected matrix endpoint")
            connection.settimeout(TIMEOUT)
            pid, uid, _ = struct.unpack(
                "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            )
            if pid <= 0 or uid != route["server_uid"]:
                raise ValueError("unexpected matrix broker")
            connection.sendall(request)
            response = json.loads(_line(connection, MAX_MATRIX_BYTES * 6 + 64))
            if (
                not isinstance(response, dict)
                or set(response) != {"matrix"}
                or not isinstance(response["matrix"], str)
            ):
                raise ValueError("invalid matrix response")
            current, current_directory = backend.gate.identified_scope(handler.headers)
            if current != recipient or not permitted(current, current_directory):
                raise ValueError("matrix session changed")
            previous = handler.connection.gettimeout()
            try:
                handler.connection.settimeout(5)
                started = True
                handler.send(200, {"version": version, "content": response["matrix"]})
            finally:
                handler.connection.settimeout(previous)
            try:
                connection.sendall(ACK)
            except OSError:
                pass  # Response has already been sent.
    except (OSError, ValueError, TypeError, KeyError, WorkflowError, struct.error):
        if not started:
            handler.send(404, {"error": "Matrix unavailable"})
    return True

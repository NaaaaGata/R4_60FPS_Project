from __future__ import annotations

from collections import deque
import socket
import secrets
import threading
import time
from typing import Any, Callable

from .protocol import JsonlDecoder, ProtocolError, encode_message, match_response, request_message


class TransportClosed(ConnectionError):
    pass


class TcpJsonlTransport:
    """Single-client JSONL transport bound exclusively to the loopback interface."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        if host != "127.0.0.1":
            raise ValueError("IPC server must bind exactly to 127.0.0.1")
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, port))
        self._listener.listen(1)
        self.host = host
        self.port = int(self._listener.getsockname()[1])
        self.session_token = secrets.token_urlsafe(32)
        self._connection: socket.socket | None = None
        self._decoder = JsonlDecoder()
        self._pending: deque[dict[str, Any]] = deque()
        self._events: deque[dict[str, Any]] = deque()
        self._request_sequence = 0
        self._lock = threading.Lock()
        self._closed = False

    @property
    def connected(self) -> bool:
        return self._connection is not None and not self._closed

    def accept(self, timeout_seconds: float) -> None:
        if self._closed:
            raise TransportClosed("transport is closed")
        self._listener.settimeout(timeout_seconds)
        try:
            connection, peer = self._listener.accept()
        except TimeoutError as error:
            raise TimeoutError("timed out waiting for PCSX-Redux Lua IPC connection") from error
        if peer[0] != "127.0.0.1":
            connection.close()
            raise ConnectionRefusedError(f"rejected non-loopback IPC peer: {peer[0]}")
        self._connection = connection
        self._listener.close()

    def _receive(self, deadline: float) -> dict[str, Any]:
        if self._pending:
            return self._pending.popleft()
        connection = self._connection
        if connection is None or self._closed:
            raise TransportClosed("IPC connection is not available")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for IPC message")
            connection.settimeout(remaining)
            try:
                chunk = connection.recv(65536)
            except socket.timeout as error:
                raise TimeoutError("timed out waiting for IPC message") from error
            if not chunk:
                self._closed = True
                try:
                    self._decoder.finish()
                except ProtocolError as error:
                    raise TransportClosed(f"IPC closed with a partial message: {error}") from error
                raise TransportClosed("PCSX-Redux Lua IPC connection closed")
            messages = self._decoder.feed(chunk)
            self._pending.extend(messages)
            if self._pending:
                return self._pending.popleft()

    def request(self, operation: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        with self._lock:
            connection = self._connection
            if connection is None or self._closed:
                raise TransportClosed("cannot send request without an IPC connection")
            self._request_sequence += 1
            request = request_message(operation, payload, self._request_sequence)
            connection.sendall(encode_message(request))
            deadline = time.monotonic() + timeout_seconds
            while True:
                message = self._receive(deadline)
                if message["kind"] == "event":
                    self._events.append(message)
                    continue
                if message["kind"] != "response":
                    raise ProtocolError(f"unexpected IPC message kind: {message['kind']}")
                if message.get("request_id") != request["request_id"]:
                    raise ProtocolError("received response for an unknown request")
                return match_response(request, message)

    def wait_for_events(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        count: int,
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        if count <= 0:
            raise ValueError("event count must be positive")
        matched = [event for event in self._events if predicate(event)]
        deadline = time.monotonic() + timeout_seconds
        with self._lock:
            while len(matched) < count:
                message = self._receive(deadline)
                if message["kind"] != "event":
                    raise ProtocolError("unexpected response while waiting for events")
                self._events.append(message)
                if predicate(message):
                    matched.append(message)
        return matched[-count:]

    def drain_events(self) -> list[dict[str, Any]]:
        result = list(self._events)
        self._events.clear()
        return result

    def close(self) -> None:
        if self._closed and self._connection is None:
            return
        self._closed = True
        if self._connection is not None:
            try:
                self._connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._connection.close()
            self._connection = None
        try:
            self._listener.close()
        except OSError:
            pass

    def __enter__(self) -> TcpJsonlTransport:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

import json
import socket
import threading
import time

import pytest

from r4_autolab.emulator.protocol import JsonlDecoder, ProtocolError
from r4_autolab.emulator.transport import TcpJsonlTransport


def test_tcp_transport_handles_event_then_matching_response() -> None:
    transport = TcpJsonlTransport()

    def client() -> None:
        connection = socket.create_connection((transport.host, transport.port), timeout=2)
        request = JsonlDecoder().feed(connection.recv(65536))[0]
        event = {
            "protocol_version": 1,
            "kind": "event",
            "event": "vblank",
            "sequence": 1,
            "vblank_index": 1,
        }
        response = {
            "protocol_version": 1,
            "kind": "response",
            "request_id": request["request_id"],
            "sequence": 2,
            "ok": True,
            "payload": {"protocol_version": 1},
        }
        connection.sendall((json.dumps(event) + "\n" + json.dumps(response) + "\n").encode())
        connection.close()

    worker = threading.Thread(target=client)
    worker.start()
    transport.accept(2)
    assert transport.request("handshake", {}, 2) == {"protocol_version": 1}
    assert transport.drain_events()[0]["event"] == "vblank"
    transport.close()
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_tcp_transport_rejects_invalid_json() -> None:
    transport = TcpJsonlTransport()

    def client() -> None:
        connection = socket.create_connection((transport.host, transport.port), timeout=2)
        connection.sendall(b"{not-json}\n")
        connection.close()

    worker = threading.Thread(target=client)
    worker.start()
    transport.accept(2)
    with pytest.raises(ProtocolError, match="invalid JSONL"):
        transport.wait_for_events(lambda _: True, 1, 2)
    transport.close()
    worker.join(timeout=2)


def test_tcp_transport_refuses_non_loopback_bind() -> None:
    with pytest.raises(ValueError, match="127.0.0.1"):
        TcpJsonlTransport("0.0.0.0")


def test_tcp_transport_request_timeout_is_bounded() -> None:
    transport = TcpJsonlTransport()

    def client() -> None:
        connection = socket.create_connection((transport.host, transport.port), timeout=2)
        connection.recv(65536)
        time.sleep(0.2)
        connection.close()

    worker = threading.Thread(target=client)
    worker.start()
    transport.accept(2)
    with pytest.raises(TimeoutError, match="IPC message"):
        transport.request("pause", {}, 0.05)
    transport.close()
    worker.join(timeout=2)

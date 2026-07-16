from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from uuid import uuid4


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 1_048_576


class ProtocolError(ValueError):
    pass


def request_message(operation: str, payload: dict[str, Any], sequence: int) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "kind": "request",
        "request_id": str(uuid4()),
        "sequence": sequence,
        "operation": operation,
        "payload": payload,
    }


def encode_message(message: dict[str, Any]) -> bytes:
    validate_message(message)
    encoded = (json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message exceeds size limit")
    return encoded


def validate_message(message: dict[str, Any]) -> None:
    if message.get("protocol_version") != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    if message.get("kind") not in {"request", "response", "event"}:
        raise ProtocolError("invalid message kind")
    sequence = message.get("sequence")
    if not isinstance(sequence, int) or sequence < 0:
        raise ProtocolError("sequence must be a non-negative integer")
    kind = message["kind"]
    if kind in {"request", "response"} and not isinstance(message.get("request_id"), str):
        raise ProtocolError("request/response requires request_id")
    if kind == "request" and not isinstance(message.get("operation"), str):
        raise ProtocolError("request requires operation")
    if kind == "response" and not isinstance(message.get("ok"), bool):
        raise ProtocolError("response requires boolean ok")
    if kind == "event" and not isinstance(message.get("event"), str):
        raise ProtocolError("event requires event name")


@dataclass
class JsonlDecoder:
    last_sequence: int = -1
    _buffer: bytes = b""

    def feed(self, chunk: bytes) -> list[dict[str, Any]]:
        self._buffer += chunk
        if len(self._buffer) > MAX_MESSAGE_BYTES:
            raise ProtocolError("unterminated message exceeds size limit")
        decoded: list[dict[str, Any]] = []
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            if not line:
                continue
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ProtocolError(f"invalid JSONL message: {error}") from error
            if not isinstance(value, dict):
                raise ProtocolError("message must be a JSON object")
            validate_message(value)
            sequence = int(value["sequence"])
            if sequence <= self.last_sequence:
                raise ProtocolError("duplicate or out-of-order sequence")
            self.last_sequence = sequence
            decoded.append(value)
        return decoded

    def finish(self) -> None:
        if self._buffer.strip():
            raise ProtocolError("partial message remained at end of stream")


def match_response(request: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    validate_message(request)
    validate_message(response)
    if response["kind"] != "response":
        raise ProtocolError("expected a response")
    if request["request_id"] != response["request_id"]:
        raise ProtocolError("response request_id mismatch")
    if not response["ok"]:
        error = response.get("error", {})
        raise ProtocolError(f"bridge error: {error}")
    payload = response.get("payload", {})
    if not isinstance(payload, dict):
        raise ProtocolError("response payload must be an object")
    return payload


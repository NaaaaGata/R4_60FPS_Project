import pytest

from r4_autolab.emulator.protocol import (
    JsonlDecoder,
    ProtocolError,
    encode_message,
    match_response,
    request_message,
)


def test_partial_jsonl_is_reassembled() -> None:
    request = request_message("pause", {}, 1)
    encoded = encode_message(request)
    decoder = JsonlDecoder()
    assert decoder.feed(encoded[:5]) == []
    assert decoder.feed(encoded[5:]) == [request]
    decoder.finish()


def test_out_of_order_sequence_is_rejected() -> None:
    decoder = JsonlDecoder()
    decoder.feed(encode_message(request_message("pause", {}, 2)))
    with pytest.raises(ProtocolError, match="out-of-order"):
        decoder.feed(encode_message(request_message("resume", {}, 1)))


def test_response_id_is_matched() -> None:
    request = request_message("pause", {}, 1)
    response = {
        "protocol_version": 1,
        "kind": "response",
        "request_id": request["request_id"],
        "sequence": 2,
        "ok": True,
        "payload": {"paused": True},
    }
    assert match_response(request, response) == {"paused": True}


import pytest

from r4_autolab.analysis.mips_branch import branch_taken, parse_ghidra_branch


def record(text: str = "bne v0,zero,0x8001ec48") -> dict[str, object]:
    return {
        "address": "0x8001EC54",
        "text": text,
        "target": "0x8001EC48",
        "fall_through": "0x8001EC5C",
        "previous_address": "0x8001EC50",
        "previous_text": "slt v0,v0,s0",
        "delay_slot_address": "0x8001EC58",
        "delay_slot_text": "_nop",
    }


def test_parse_branch_preserves_comparison_and_delay_slot() -> None:
    branch = parse_ghidra_branch(record())
    assert branch.address == 0x8001EC54
    assert branch.target == 0x8001EC48
    assert branch.fall_through == 0x8001EC5C
    assert branch.previous_text == "slt v0,v0,s0"
    assert branch.delay_slot_text == "nop"
    assert branch_taken(branch, {"v0": 1})
    assert not branch_taken(branch, {"v0": 0})


@pytest.mark.parametrize(
    ("text", "value", "expected"),
    [
        ("beq s0,zero,0x8001ec48", 0, True),
        ("blez s0,0x8001ec48", 0, True),
        ("bgtz s0,0x8001ec48", 1, True),
        ("bltz s0,0x8001ec48", 0xFFFFFFFF, True),
        ("bgez s0,0x8001ec48", 0xFFFFFFFF, False),
    ],
)
def test_branch_decoder_handles_signed_mips_conditions(text: str, value: int, expected: bool) -> None:
    branch = parse_ghidra_branch(record(text))
    assert branch_taken(branch, {"s0": value}) is expected

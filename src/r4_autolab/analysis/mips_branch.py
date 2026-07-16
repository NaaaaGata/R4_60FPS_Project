from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MipsBranch:
    address: int
    mnemonic: str
    rs: str
    rt: str | None
    target: int
    fall_through: int
    delay_slot_address: int
    delay_slot_text: str
    previous_address: int | None = None
    previous_text: str | None = None


def parse_ghidra_branch(value: dict[str, Any]) -> MipsBranch:
    text = str(value["text"]).replace("_", "").strip()
    mnemonic, _, operand_text = text.partition(" ")
    operands = [part.strip() for part in operand_text.split(",") if part.strip()]
    if mnemonic in {"beq", "bne"} and len(operands) == 3:
        rs, rt = operands[0], operands[1]
    elif mnemonic in {"blez", "bgtz", "bltz", "bgez"} and len(operands) == 2:
        rs, rt = operands[0], None
    else:
        raise ValueError(f"unsupported conditional branch: {text}")
    target = value.get("target")
    fall_through = value.get("fall_through")
    delay_address = value.get("delay_slot_address")
    delay_text = value.get("delay_slot_text")
    if target is None or fall_through is None or delay_address is None or delay_text is None:
        raise ValueError("branch export is missing target/fall-through/delay-slot metadata")
    previous = value.get("previous_address")
    return MipsBranch(
        address=int(str(value["address"]), 0),
        mnemonic=mnemonic,
        rs=rs,
        rt=rt,
        target=int(str(target), 0),
        fall_through=int(str(fall_through), 0),
        delay_slot_address=int(str(delay_address), 0),
        delay_slot_text=str(delay_text).replace("_", ""),
        previous_address=int(str(previous), 0) if previous is not None else None,
        previous_text=str(value["previous_text"]).replace("_", "")
        if value.get("previous_text") is not None
        else None,
    )


def branch_taken(branch: MipsBranch, registers: dict[str, int]) -> bool:
    rs = _register(registers, branch.rs)
    rt = _register(registers, branch.rt) if branch.rt is not None else None
    if branch.mnemonic == "beq":
        return rs == rt
    if branch.mnemonic == "bne":
        return rs != rt
    signed_rs = _signed32(rs)
    if branch.mnemonic == "blez":
        return signed_rs <= 0
    if branch.mnemonic == "bgtz":
        return signed_rs > 0
    if branch.mnemonic == "bltz":
        return signed_rs < 0
    if branch.mnemonic == "bgez":
        return signed_rs >= 0
    raise ValueError(f"unsupported branch mnemonic: {branch.mnemonic}")


def _register(registers: dict[str, int], name: str | None) -> int:
    if name in {None, "zero", "r0"}:
        return 0
    if name not in registers:
        raise KeyError(f"register snapshot is missing {name}")
    return int(registers[name]) & 0xFFFFFFFF


def _signed32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value

import pytest

from r4_autolab.scratch_audit import evaluate_scratch_samples, validate_scratch_address


def test_scratch_audit_passes_only_unchanged_unaccessed_samples() -> None:
    samples = [
        {"before_hex": "00000000", "after_hex": "00000000"},
        {"before_hex": "00000000", "after_hex": "00000000"},
    ]
    status, reasons = evaluate_scratch_samples(samples, [])
    assert status == "PASS"
    assert "read_write_breakpoint_hits=0" in reasons
    assert evaluate_scratch_samples(samples, [{"access": "read"}])[0] == "FAIL"


def test_scratch_address_must_be_aligned_and_inside_scratchpad() -> None:
    validate_scratch_address(0x1F8003FC)
    with pytest.raises(ValueError, match="aligned"):
        validate_scratch_address(0x1F8003FD)
    with pytest.raises(ValueError, match="inside"):
        validate_scratch_address(0x1F800400)

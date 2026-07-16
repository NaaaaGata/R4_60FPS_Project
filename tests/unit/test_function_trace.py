from r4_autolab.function_trace import summarize_function_hits


def test_function_hit_summary_reports_vblank_coverage_and_callers() -> None:
    events = [
        {"accessed_address": 0x80010000, "vblank_index": 1, "ra": 0x80020000},
        {"accessed_address": 0x80010000, "vblank_index": 1, "ra": 0x80020000},
        {"accessed_address": 0x80010000, "vblank_index": 3, "ra": 0x80030000},
    ]
    summary = summarize_function_hits(events, 4)[0]
    assert summary["hits"] == 3
    assert summary["vblanks_with_hits"] == 2
    assert summary["hits_per_vblank"] == 0.75
    assert summary["vblank_coverage"] == 0.5
    assert summary["callers"][0] == {"ra": "0x80020000", "count": 2}

"""Animated on-screen counters: only the final value (confirmed by narration) is evidence."""

import pytest

from vjournalist.pipeline.knowledge_text import counter_hints, local_screen_text, repeats_speech


def record(id_, t, text, confidence="exact"):
    return {"id": id_, "timestamp_s": t, "last_seen_s": t, "text": text, "text_confidence": confidence, "ocr_score": 0.95}


@pytest.fixture
def evidence():
    return {
        "transcript": {
            "language": "en",
            "segments": [
                {"start": 0, "end": 4, "text": "We replayed 1096 simulated orders over six years."},
                {"start": 4, "end": 8, "text": "The final tally is on screen."},
            ],
        },
        "platform_info": {"content_duration_s": 30},
        "scan": {
            "frames": [],
            "screen_text": [
                record(1, 10.0, "368 TRADES", "approximate"),
                record(2, 12.0, "1,096 TRADES"),
                record(3, 2.8, "COME BACK?", "approximate"),
                record(4, 20.0, "21,475"),
            ],
        },
    }


def test_counter_final_only_and_local_ocr(evidence):
    hints = counter_hints(evidence)
    assert hints[0]["final"] == 1096
    assert hints[0]["readings"][0]["value"] == 368
    assert "inferred" in hints[0]["evidence"]
    lines = local_screen_text(evidence)
    text = "\n".join(r["text"] for r in lines)
    assert "368 TRADES" not in text and "21,475" not in text
    assert not any(repeats_speech(r, evidence["transcript"]) for r in lines)
    # Neutral headers are not all labelled uncertain; claims and numbers are when approximate.
    for r in lines:
        if r["text"] == "COME BACK?":
            assert not r["uncertain_content"]

import re

import pytest

from vjournalist.bridge import transcript as T


def test_fidelity_max_span_flags_and_fragment():
    segs = [
        {"start": i * 4, "end": (i + 1) * 4, "text": f"Word {i}.", "avg_logprob": -1 if i == 2 else 0}
        for i in range(15)
    ]
    blocks = T.build_blocks(segs)
    text = "\n".join(T.block_line(b) for b in blocks)
    assert T.norm_ws(re.sub(r"^\[\d\d:\d\d\] ", "", text, flags=re.M).replace(" [?]", "")) == T.norm_ws(
        " ".join(s["text"] for s in segs)
    )
    assert all(b[-1]["end"] - b[0]["start"] <= 20 for b in blocks)
    assert text.count("[?]") == 1
    assert "[00:48]" in T.fragment(text, 53, 20)
    assert "[00:00]" not in T.fragment(text, 53, 20)


@pytest.mark.parametrize("bad,good", [("55.7", "55.2"), ("1069", "1096"), ("41.6", "40.6"), ("2.8", "2.6")])
def test_four_number_errors(bad, good):
    assert T.number_check(bad, [good])[0][bad].startswith("conflict")


@pytest.mark.parametrize("a,b", [("1000", "9000"), ("1096", "1000"), ("100", "1000")])
def test_insignificant_or_different_length_never_conflict(a, b):
    assert T.number_check(a, [b])[0][a] == "speech_only"





def test_long_segment_fails_without_losing_words():
    with pytest.raises(ValueError, match="word timestamps"):
        T.build_blocks([{"start": 0, "end": 21, "text": "All words."}])


def test_two_significant_digits_conflict_and_decimal_separator_does_not():
    assert T.number_check("12", ["13"])[0]["12"].startswith("conflict")
    assert T.number_check("1.2", ["132"])[0]["1.2"] == "speech_only"

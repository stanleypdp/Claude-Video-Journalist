import pytest

from vjournalist.bridge.repair import decode
from vjournalist.bridge.transcript import is_low, nums
from vjournalist.pipeline.windows import merge, windows


def test_window_boundaries_and_merge_conflict():
    assert windows(56.44) == [(0, 56.44)]
    assert windows(181, 75) == [(0, 75), (75, 150), (150, 181)]
    with pytest.raises(ValueError):
        windows(180, 30)
    a = {"events": [{"id": "x", "start": 2, "value": 1}]}
    result, conflicts = merge([a, a])
    assert len(result["events"]) == 1 and not conflicts
    _, conflicts = merge([a, {"events": [{"id": "x", "start": 2, "value": 2}]}])
    assert len(conflicts) == 1


def test_threshold_boundaries_and_polish_numbers():
    assert not is_low({"avg_logprob": -0.8, "no_speech_prob": 0.6})
    assert is_low({"avg_logprob": -0.81, "no_speech_prob": 0.6})
    assert is_low({"avg_logprob": 0, "no_speech_prob": 0.61})
    assert set(nums("55,2% 1,096 40.6%")) == {55.2, 1096, 40.6}
    value, repaired = decode('{"a":["literal comma,]",],}')
    assert repaired and value["a"] == ["literal comma,]"]

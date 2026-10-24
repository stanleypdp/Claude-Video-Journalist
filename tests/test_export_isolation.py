from pathlib import Path

from tests.test_read_contract import example
from vjournalist.bridge.cards import export_read, normalize_read


def test_read_exports_are_isolated_to_requested_root(tmp_path):
    p, v = example()
    value = normalize_read(v, p)
    common = {
        "transcript": {"language": "en", "segments": [{"start": 0, "end": 2, "text": "55.2%."}]},
        "scan": {"screen_text": [], "frames": []},
        "metadata": {"duration_s": 2},
        "platform_info": {"content_duration_s": 2},
    }
    root = tmp_path / "bridge"
    export_read("isolated", value, common, root)
    assert (root / "cards/isolated.md").exists()
    assert (root / "INDEX.md").exists()
    assert not Path("bridge/cards/isolated.md").exists()

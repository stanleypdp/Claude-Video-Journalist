import pytest

from vjournalist import cli
from vjournalist.pipeline.content_scan import platform_info
from vjournalist.pipeline.payload import build_payload
from vjournalist.roles import schema_for_role


def content(duration=30):
    return {
        "metadata": {"duration_s": duration, "fps": 25, "width": 180, "height": 320},
        "transcript": {"language": "en", "segments": [{"start": 0, "end": duration, "text": "source"}]},
        "scenes": [
            {"number": 1, "start": 0, "end": duration, "duration_s": duration, "platform_artifact": False}
        ],
        "scan": {"frames": [], "screen_text": []},
        "platform_info": {"content_duration_s": duration},
    }


def item(text, x=0.5, y=0.4, score=0.99):
    return {
        "text": text,
        "score": score,
        "box": [[x - 0.05, y - 0.02], [x + 0.05, y - 0.02], [x + 0.05, y + 0.02], [x - 0.05, y + 0.02]],
    }


def test_only_knowledge_role_exists():
    assert schema_for_role("knowledge")["properties"]["card"]
    for role in ("taste", "both"):
        with pytest.raises(ValueError):
            schema_for_role(role)


def test_cli_requires_known_command_and_folder_must_exist(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["analyze", "x.mp4"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        cli.main(["read", str(tmp_path / "missing")])
    assert exc.value.code == 2


def test_platform_end_card_and_black_removed_but_watermark_is_not():
    meta = {"duration_s": 30}
    scenes = [
        {"number": 1, "start": 0, "end": 25.8, "duration_s": 25.8},
        {"number": 2, "start": 25.8, "end": 26, "duration_s": 0.2},
        {"number": 3, "start": 26, "end": 30, "duration_s": 4},
    ]
    frames = [
        {"timestamp_s": 25.9, "brightness": 0, "items": []},
        {"timestamp_s": 27, "brightness": 0.1, "items": [item("TikTok"), item("@exact", y=0.6)]},
    ]
    result = platform_info(meta, scenes, {"frames": frames})
    assert result["content_duration_s"] == 25.8 and result["cuts_per_second"] == 0
    assert result["source_account"] == "@exact"
    frames[-1]["items"] = [item("TikTok", x=0.1, y=0.9), item("@exact", x=0.1, y=0.94)]
    assert platform_info(meta, scenes, {"frames": frames})["artifact_start_s"] is None


def test_platform_search_handle_without_at_matches_exact_watermark():
    meta = {"duration_s": 30}
    scenes = [
        {"number": 1, "start": 0, "end": 26, "duration_s": 26},
        {"number": 2, "start": 26, "end": 30, "duration_s": 4},
    ]
    frames = [
        {
            "timestamp_s": 20,
            "brightness": 0.4,
            "items": [item("TikTok", x=0.9, y=0.9), item("@example.handle", x=0.9, y=0.94)],
        },
        {"timestamp_s": 28, "brightness": 0.08, "items": [item("TikTok"), item("example.handle", y=0.6)]},
    ]
    result = platform_info(meta, scenes, {"frames": frames})
    assert result["artifact_start_s"] == 26
    assert result["source_account"] == "@example.handle"


def test_read_payload_only_data_image_exceptions(tmp_path):
    common = content()
    common["scan"]["frames"] = [
        {
            "timestamp_s": i,
            "needs_data_image": i % 2 == 0,
            "kind": "chart" if i % 2 == 0 else "text",
            "file": f"{i}.jpg",
        }
        for i in range(20)
    ]
    for frame in common["scan"]["frames"]:
        (tmp_path / frame["file"]).write_bytes(b"x")
    payload = build_payload(common, None, tmp_path)
    assert payload["schema_version"] == 6 and len(payload["images"]) == 6
    assert all(f["kind"] == "chart" for f in payload["data_images"])
    assert not {"scenes", "audio_metrics", "contact_sheets", "higgsfield_models"} & payload.keys()
    common["scan"]["frames"] = []
    assert build_payload(common, None, tmp_path)["images"] == []

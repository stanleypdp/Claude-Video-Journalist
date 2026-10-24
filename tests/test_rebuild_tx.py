import json

from tests.test_read_contract import example
from vjournalist import cli
from vjournalist.bridge.cards import export_read, normalize_read
from vjournalist.rebuild import cache_index, format_rebuild, rebuild
from vjournalist.storage import atomic_json, slug

COMMON = {
    "transcript": {
        "language": "en",
        "segments": [{"start": 0, "end": 6, "text": "NASDAQ tested 55.2% since 2020 before costs."}],
    },
    "scan": {"screen_text": [], "frames": []},
    "metadata": {"duration_s": 6},
    "platform_info": {"content_duration_s": 6},
}


def seeded(tmp_path, config):
    """One video with a cached raw answer and the OUTPUT built from it."""
    payload, value = example()
    digest = "c" * 64
    id_ = f"{slug('clip')}-{digest[:12]}"
    cache = config.data / "cache" / digest
    atomic_json(cache / "provenance.json", {"name": "clip", "sha256": digest})
    directory = cache / "roles/knowledge/v6"
    atomic_json(directory / "analysis.json", {"invocations": 1})
    atomic_json(directory / "payload.json", payload)
    atomic_json(directory / "common.json", COMMON)
    atomic_json(directory / "llm/response-1.json", {"result": json.dumps(value)})
    root = tmp_path / "OUTPUT" / "X"
    export_read(id_, normalize_read(value, payload), COMMON, root)
    return id_, root


def test_rebuild_from_cache_is_identical_and_leaves_cache_alone(tmp_path, config):
    id_, root = seeded(tmp_path, config)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    cache_before = {p: p.read_bytes() for p in config.data.rglob("*") if p.is_file()}
    assert id_ in cache_index(config)
    report = rebuild(root, config=config)
    assert report["rebuilt"] == [id_] and not report["failures"]
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    assert {p: p.read_bytes() for p in config.data.rglob("*") if p.is_file()} == cache_before
    assert "0 LLM" in format_rebuild(report)


def test_rebuild_reports_cards_missing_from_cache(tmp_path, config):
    id_, root = seeded(tmp_path, config)
    (root / "cards" / "ghost-000000000000.md").write_text((root / "cards" / f"{id_}.md").read_text())
    report = rebuild(root, config=config)
    assert report["failures"] == [("ghost-000000000000", "not in cache")]


def test_tx_prints_blocks_around_the_second(tmp_path, capsys):
    root = tmp_path / "OUTPUT" / "X"
    (root / "archive").mkdir(parents=True)
    (root / "archive" / "vid-1.tx.md").write_text("[00:00] a\n[00:10] b\n[00:20] c\n[00:50] d\n")
    assert cli.main(["tx", "vid-1", "--at", "12", "--window", "10", "--output", str(root)]) == 0
    out = capsys.readouterr().out
    assert "[00:10] b" in out and "[00:50] d" not in out
    assert cli.main(["tx", "nope", "--at", "1", "--output", str(root)]) == 1


def test_rebuild_keeps_cards_with_recorded_results(tmp_path, config):
    id_, root = seeded(tmp_path, config)
    card = root / "cards" / f"{id_}.md"
    edited = card.read_text().replace("status: untested", "status: in_test")
    edited += "\n- run 1: reproduced 55.2% on our data\n"
    card.write_text(edited)
    report = rebuild(root, config=config)
    assert report["kept"] == [id_] and not report["rebuilt"]
    assert card.read_text() == edited
    assert "Kept as is" in format_rebuild(report)
    forced = rebuild(root, config=config, overwrite=True)
    assert forced["rebuilt"] == [id_] and "status: untested" in card.read_text()


def test_index_command_regenerates_from_card_headers(tmp_path, config, capsys):
    id_, root = seeded(tmp_path, config)
    card = root / "cards" / f"{id_}.md"
    card.write_text(card.read_text().replace("status: untested", "status: confirmed"))
    assert cli.main(["index", str(root)]) == 0
    row = [line for line in (root / "INDEX.md").read_text().splitlines() if id_ in line][0]
    assert "| confirmed |" in row
    capsys.readouterr()

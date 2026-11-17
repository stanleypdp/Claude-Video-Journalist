import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "_run", Path(__file__).resolve().parents[1] / "skills" / "video-read" / "scripts" / "_run.py"
)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_git_clone_keeps_project_data_dir(tmp_path):
    (tmp_path / ".git").mkdir()
    assert launcher.data_dir_for(tmp_path, {}) is None


def test_installed_copy_stores_data_outside_the_plugin_folder(tmp_path):
    chosen = launcher.data_dir_for(tmp_path, {})
    assert chosen == str(Path.home() / ".vjournalist" / "data")
    assert not Path(chosen).is_relative_to(tmp_path)


def test_explicit_data_dir_wins(tmp_path):
    assert launcher.data_dir_for(tmp_path, {"DATA_DIR": "/somewhere"}) is None


def test_no_project_found_changes_nothing():
    assert launcher.data_dir_for(None, {}) is None

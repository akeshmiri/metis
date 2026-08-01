"""
Tests for config_manager.py's resolution rule itself -- built against real
temp directories and real files, not mocked, since the whole point is
proving the file-system resolution order actually works.
"""
import os
import tempfile
import shutil
from pathlib import Path

from metis_mcp.config_manager import ConfigManager, ConfigNotFoundError, resolve_config_path


def _make_temp_project(with_project_config: bool, with_host_config: bool):
    """Sets up real temp directories for a project root and a fake $HOME,
    with METIS_HOME pointed at the fake home so host-level resolution is
    actually testable without touching the real ~/.metis."""
    project_dir = Path(tempfile.mkdtemp())
    host_dir = Path(tempfile.mkdtemp())
    os.environ["METIS_HOME"] = str(host_dir)

    if with_project_config:
        (project_dir / ".metis").mkdir()
        (project_dir / ".metis" / "config.yaml").write_text(
            "zdr:\n  confirmed: false\nrepositories:\n"
            "  - name: from-project\n    classification: public_internal\n"
        )
    if with_host_config:
        (host_dir / "config.yaml").write_text(
            "zdr:\n  confirmed: true\nrepositories:\n"
            "  - name: from-host\n    classification: confidential\n"
        )
    return project_dir, host_dir


def test_project_overrides_host_when_both_exist():
    """First-found-wins: project-level must win when both are present, per
    the real atlas-config-manager convention this was modeled on."""
    project_dir, host_dir = _make_temp_project(with_project_config=True, with_host_config=True)
    try:
        cm = ConfigManager(start_dir=project_dir)
        assert cm.resolution.source == "project"
        assert cm.get_classification("from-project") == "public_internal"
        assert cm.get_classification("from-host") is None  # host file's content must NOT merge in
        assert cm.get_zdr_confirmed() is False  # project's value (False), not host's (True)
    finally:
        shutil.rmtree(project_dir)
        shutil.rmtree(host_dir)


def test_host_used_when_project_absent():
    """Host-level is the runtime default when no project-level config exists."""
    project_dir, host_dir = _make_temp_project(with_project_config=False, with_host_config=True)
    try:
        cm = ConfigManager(start_dir=project_dir)
        assert cm.resolution.source == "host"
        assert cm.get_classification("from-host") == "confidential"
        assert cm.get_zdr_confirmed() is True
    finally:
        shutil.rmtree(project_dir)
        shutil.rmtree(host_dir)


def test_halts_when_neither_exists():
    """No silent default -- must raise, not fall back to an assumed config."""
    project_dir, host_dir = _make_temp_project(with_project_config=False, with_host_config=False)
    try:
        try:
            ConfigManager(start_dir=project_dir)
            assert False, "should have raised ConfigNotFoundError"
        except ConfigNotFoundError as e:
            assert "No Métis config found" in str(e)
    finally:
        shutil.rmtree(project_dir)
        shutil.rmtree(host_dir)


def test_no_merge_across_locations():
    """A repository classified ONLY at host-level must not be visible when a
    project-level config exists and takes precedence -- proves no merge
    happens, matching 'first found wins -- no merge across locations.'"""
    project_dir, host_dir = _make_temp_project(with_project_config=True, with_host_config=True)
    try:
        cm = ConfigManager(start_dir=project_dir)
        assert cm.get_classification("from-host") is None
    finally:
        shutil.rmtree(project_dir)
        shutil.rmtree(host_dir)


if __name__ == "__main__":
    import sys
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)

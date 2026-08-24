"""
Connection resolution (application spec PLT-002, PLT-003, PLT-005).

Free to run: no Neo4j needed. `resolve()` is pure apart from the environment and
the filesystem, and both are redirected here.

The case worth naming is **environment beats file**. A machine with a stored
password and a one-off `METIS_NEO4J_PASSWORD=... metis ...` in front of a command
must use the one-off; the alternative is a run that silently talks to the wrong
database while the operator believes they redirected it.
"""
import json
import os
import stat

import pytest

from metis_mcp.mbt import graph_session
from metis_mcp.mbt.graph_session import (
    DEFAULT_URI,
    GraphNotConfigured,
    PASSWORD_ENV,
    resolve,
)

# Captured before the autouse fixture replaces it. A test that wants the real
# search order cannot ask the module for it later -- by then it is the stub.
REAL_CONFIG_PATHS = graph_session.config_paths

BLOCK = {"graph": {"backend": "neo4j", "neo4j": {
    "uri": "bolt://host.example:7687", "user": "from-file"}}}


def _config(tmp_path, block, name="config.json", mode=0o600):
    path = tmp_path / name
    path.write_text(json.dumps(block))
    path.chmod(mode)
    return path


@pytest.fixture(autouse=True)
def _no_ambient_config(monkeypatch, tmp_path):
    # The once-per-process advisory is per-process state; a test that asserts on
    # it must not depend on which test ran first.
    graph_session._ANNOUNCED.clear()
    """Clear the environment, the announce-once state, and both search paths.

    Without this the developer's own ~/.metis/config.json decides the result,
    which is the class of test that passes on one machine only.
    """
    for var in (PASSWORD_ENV, "METIS_NEO4J_URI", "METIS_NEO4J_USER",
                graph_session.CONFIG_PATH_ENV):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(graph_session, "config_paths",
                        lambda: (tmp_path / "absent.json",))
    monkeypatch.setattr(graph_session, "unreadable_config_paths", tuple)


def test_environment_alone_still_works(monkeypatch):
    """The path that existed before the config file did."""
    monkeypatch.setenv(PASSWORD_ENV, "from-env")
    config = resolve()
    assert (config.password, config.uri, config.user) == (
        "from-env", DEFAULT_URI, "neo4j")
    assert config.password_source == PASSWORD_ENV


def test_no_password_anywhere_halts_and_names_where_it_looked(monkeypatch, tmp_path):
    monkeypatch.setattr(graph_session, "config_paths",
                        lambda: (tmp_path / "nope.json",))
    with pytest.raises(GraphNotConfigured) as e:
        resolve()
    assert PASSWORD_ENV in str(e.value)
    assert "nope.json" in str(e.value)


def test_a_yaml_config_is_reported_rather_than_ignored(monkeypatch, tmp_path):
    """The confusing case: configuration is present and this build cannot read it."""
    yaml = tmp_path / "config.yaml"
    yaml.write_text("graph:\n  neo4j:\n    uri: bolt://x\n")
    monkeypatch.setattr(graph_session, "unreadable_config_paths", lambda: (yaml,))
    with pytest.raises(GraphNotConfigured) as e:
        resolve()
    assert "config.yaml" in str(e.value) and "JSON only" in str(e.value)


def test_password_env_indirection_is_the_documented_path(monkeypatch, tmp_path):
    """`password_env` names the variable; the secret never enters the file."""
    block = json.loads(json.dumps(BLOCK))
    block["graph"]["neo4j"]["password_env"] = "PROJECT_GRAPH_PW"
    monkeypatch.setattr(graph_session, "config_paths",
                        lambda: (_config(tmp_path, block),))
    monkeypatch.setenv("PROJECT_GRAPH_PW", "indirect")

    config = resolve()
    assert config.password == "indirect"
    assert config.password_source == "PROJECT_GRAPH_PW"
    assert (config.uri, config.user) == ("bolt://host.example:7687", "from-file")


def test_password_env_named_but_unset_says_which_variable(monkeypatch, tmp_path):
    block = json.loads(json.dumps(BLOCK))
    block["graph"]["neo4j"]["password_env"] = "PROJECT_GRAPH_PW"
    monkeypatch.setattr(graph_session, "config_paths",
                        lambda: (_config(tmp_path, block),))
    with pytest.raises(GraphNotConfigured) as e:
        resolve()
    assert "PROJECT_GRAPH_PW" in str(e.value)


def test_a_literal_password_is_read_from_an_owner_only_file(monkeypatch, tmp_path,
                                                            capsys):
    # A distinctive value, so "the secret is not in the notice" is a real
    # assertion rather than a collision with the notice's own wording.
    block = json.loads(json.dumps(BLOCK))
    block["graph"]["neo4j"]["password"] = "sh0uld-never-be-printed"
    path = _config(tmp_path, block, mode=0o600)
    monkeypatch.setattr(graph_session, "config_paths", lambda: (path,))

    config = resolve()
    assert config.password == "sh0uld-never-be-printed"
    assert config.password_source == str(path)
    # Said out loud, and on stderr -- stdout is the MCP JSON-RPC channel.
    captured = capsys.readouterr()
    assert "password_env" in captured.err
    assert captured.out == ""
    assert "sh0uld-never-be-printed" not in captured.err


def test_a_literal_password_in_a_readable_file_refuses(monkeypatch, tmp_path):
    """Fail-closed, with the fix in the message."""
    block = json.loads(json.dumps(BLOCK))
    block["graph"]["neo4j"]["password"] = "literal"
    path = _config(tmp_path, block, mode=0o644)
    monkeypatch.setattr(graph_session, "config_paths", lambda: (path,))

    with pytest.raises(GraphNotConfigured) as e:
        resolve()
    assert "chmod 600" in str(e.value)


def test_the_environment_beats_the_file(monkeypatch, tmp_path):
    """A one-off override must actually override."""
    block = json.loads(json.dumps(BLOCK))
    block["graph"]["neo4j"]["password"] = "from-file"
    monkeypatch.setattr(graph_session, "config_paths",
                        lambda: (_config(tmp_path, block),))
    monkeypatch.setenv(PASSWORD_ENV, "from-env")
    monkeypatch.setenv("METIS_NEO4J_URI", "bolt://override:7687")

    config = resolve()
    assert config.password == "from-env"
    assert config.password_source == PASSWORD_ENV
    assert config.uri == "bolt://override:7687"
    # user was not overridden, so the file still supplies it
    assert config.user == "from-file"


def test_explicit_arguments_beat_everything_except_the_password(monkeypatch,
                                                                tmp_path):
    block = json.loads(json.dumps(BLOCK))
    block["graph"]["neo4j"]["password"] = "from-file"
    monkeypatch.setattr(graph_session, "config_paths",
                        lambda: (_config(tmp_path, block),))
    config = resolve(uri="bolt://arg:7687", user="arg-user")
    assert (config.uri, config.user) == ("bolt://arg:7687", "arg-user")
    assert config.password == "from-file"


def test_first_found_wins_with_no_merge(monkeypatch, tmp_path):
    """Project config decides alone; the host file is not consulted for gaps."""
    project = _config(tmp_path, {"graph": {"neo4j": {"password": "project"}}},
                      name="project.json")
    host = _config(tmp_path, BLOCK | {}, name="host.json")
    monkeypatch.setattr(graph_session, "config_paths", lambda: (project, host))

    config = resolve()
    assert config.password == "project"
    # host's uri would have been bolt://host.example:7687 had they been merged
    assert config.uri == DEFAULT_URI


def test_malformed_json_halts_rather_than_falling_through(monkeypatch, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    broken.chmod(0o600)
    host = _config(tmp_path, {"graph": {"neo4j": {"password": "host"}}},
                   name="host.json")
    monkeypatch.setattr(graph_session, "config_paths", lambda: (broken, host))

    with pytest.raises(GraphNotConfigured) as e:
        resolve()
    assert "not valid JSON" in str(e.value)


def test_a_config_without_a_graph_block_is_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(graph_session, "config_paths",
                        lambda: (_config(tmp_path, {"models": {}}),))
    with pytest.raises(GraphNotConfigured) as e:
        resolve()
    assert PASSWORD_ENV in str(e.value)


def test_redacted_never_carries_the_secret(monkeypatch):
    monkeypatch.setenv(PASSWORD_ENV, "s3cret")
    assert "s3cret" not in resolve().redacted


def test_the_literal_password_notice_is_said_once(monkeypatch, tmp_path, capsys):
    """Twice is how a notice becomes noise. `coverage` resolves three times."""
    block = json.loads(json.dumps(BLOCK))
    block["graph"]["neo4j"]["password"] = "sh0uld-never-be-printed"
    path = _config(tmp_path, block, mode=0o600)
    monkeypatch.setattr(graph_session, "config_paths", lambda: (path,))

    resolve()
    resolve()
    assert capsys.readouterr().err.count("using the literal password") == 1


def test_metis_config_path_is_the_only_candidate_when_set(monkeypatch, tmp_path):
    """The chart's contract. An explicit path must not fall back to $HOME."""
    named = _config(tmp_path, {"graph": {"neo4j": {"password": "from-named",
                                                   "uri": "bolt://pod:7687"}}},
                    name="mounted.json")
    monkeypatch.setenv(graph_session.CONFIG_PATH_ENV, str(named))
    # The default search would find this one; it must not be consulted.
    monkeypatch.setattr(graph_session, "config_paths", REAL_CONFIG_PATHS)
    config = resolve()
    assert config.password == "from-named"
    assert config.uri == "bolt://pod:7687"


def test_a_named_config_that_is_absent_says_so(monkeypatch, tmp_path):
    """Silence here is a pod reading whatever the node happened to have."""
    monkeypatch.setenv(graph_session.CONFIG_PATH_ENV, str(tmp_path / "gone.json"))
    monkeypatch.setattr(graph_session, "config_paths", REAL_CONFIG_PATHS)
    with pytest.raises(GraphNotConfigured) as e:
        resolve()
    assert "does not exist" in str(e.value)

"""
Métis config manager — modeled directly on the real atlas-config-manager
convention (checked against the actual Atlas archive, not invented fresh):

  "host-level ~/.atlas/configs/** is the runtime default; project-level
   .agents/configs/** is the override when present. First found wins —
   no merge across locations."

Métis's equivalent:
  - Host-level default:  ~/.metis/config.yaml
  - Project-level override: <project_root>/.metis/config.yaml
  - First found wins (project, if present, overrides host) — no merging
    of the two files' contents.
  - Resolved ONCE per process and cached — matches the real convention's
    "resolve once per session, never re-ask."
  - If NEITHER exists: this halts with a clear, actionable error rather
    than falling back to a hardcoded default in code. This is the whole
    point of the "no configuration in code" directive -- a missing config
    is a setup gap to fix, not something for the code to paper over with
    an assumption.

This is the ONLY place model names, ZDR status, per-repository
classifications, and the corpus path are allowed to live for this server.
Nothing here is hardcoded in classification_gate.py or server.py anymore --
see the git history / prior version of both files for what was removed.
"""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigNotFoundError(Exception):
    """
    Raised when neither a project-level nor host-level config file exists.
    Deliberately NOT caught silently anywhere in this codebase -- per the
    same discipline as REQ-METIS-CONN-06 (per-project connector conventions):
    absent configuration halts, it does not fall back to a guess.
    """
    def __init__(self, project_path: Path, host_path: Path):
        super().__init__(
            f"No Métis config found.\n"
            f"  Checked project-level: {project_path} (not found)\n"
            f"  Checked host-level:    {host_path} (not found)\n"
            f"Create one of these files -- see metis.config.example.yaml for the "
            f"expected shape. This is a deliberate halt, not a bug: Métis does not "
            f"assume a default classification or ZDR status when none is configured."
        )
        self.project_path = project_path
        self.host_path = host_path


@dataclass(frozen=True)
class ConfigResolution:
    effective_path: Path
    project_path: Path
    host_path: Path
    project_path_exists: bool
    host_path_exists: bool
    source: str  # "project" or "host" -- which one was actually used


def _project_config_path(start_dir: Path | None = None) -> Path:
    start = Path(start_dir or Path.cwd()).resolve()
    return (start / ".metis" / "config.yaml").resolve()


def _host_config_path() -> Path:
    home = Path(os.environ.get("METIS_HOME", "~/.metis")).expanduser()
    return (home / "config.yaml").resolve()


def resolve_config_path(start_dir: Path | None = None) -> ConfigResolution:
    """
    Pure resolution logic (no file reading) -- first-found-wins, project over
    host, no merge. Separated from loading so the resolution itself is
    independently testable, same as the real config_provider.py's
    resolve_config_layers() being separate from load_json_config().
    """
    project_path = _project_config_path(start_dir)
    host_path = _host_config_path()
    project_exists = project_path.exists()
    host_exists = host_path.exists()

    if project_exists:
        effective, source = project_path, "project"
    elif host_exists:
        effective, source = host_path, "host"
    else:
        raise ConfigNotFoundError(project_path, host_path)

    return ConfigResolution(
        effective_path=effective,
        project_path=project_path,
        host_path=host_path,
        project_path_exists=project_exists,
        host_path_exists=host_exists,
        source=source,
    )


class ConfigManager:
    """
    Resolved and loaded ONCE at construction, then cached for the lifetime of
    this instance -- matches the real convention's "resolve once per
    session, never re-ask." A caller that wants to pick up a config change
    must construct a new ConfigManager, not call a re-resolve method --
    this is deliberate, not an oversight, since the whole point of resolving
    once is that config shouldn't silently change mid-session.
    """

    def __init__(self, start_dir: Path | None = None):
        self.resolution = resolve_config_path(start_dir)
        with open(self.resolution.effective_path, encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}

    @property
    def effective_path(self) -> Path:
        return self.resolution.effective_path

    def get_zdr_confirmed(self) -> bool:
        return bool(self._data.get("zdr", {}).get("confirmed", False))

    def get_zdr_record(self) -> dict:
        return dict(self._data.get("zdr", {}))

    def get_classification(self, repository: str) -> str | None:
        """Returns the raw string classification for a repository, or None if
        not explicitly listed -- the caller (ClassificationGate) is
        responsible for applying the fail-closed default, not this method."""
        repos = self._data.get("repositories", [])
        for entry in repos:
            if entry.get("name") == repository:
                return entry.get("classification")
        return None

    def get_model_config(self) -> dict:
        return dict(self._data.get("models", {}))

    def get_corpus_glob(self) -> str | None:
        return self._data.get("corpus", {}).get("glob")

    def get_graph_backend(self) -> str:
        """'local' (LocalGraphStore, dogfooding corpus) or 'neo4j' (Neo4jGraphStore,
        real Cypher). Defaults to 'local' when unset so existing configs written
        before Neo4jGraphStore existed keep working without edits."""
        return self._data.get("graph", {}).get("backend", "local")

    def get_neo4j_config(self) -> dict:
        """uri/user/password_env -- password_env names an environment variable
        holding the actual secret, so the secret itself never has to live in a
        checked-in config.yaml.

        NEO4J_URI, if set in the environment, overrides config.yaml's
        graph.neo4j.uri -- real bug found deploying this to a real cluster:
        metis-chart/values.yaml already declares a NEO4J_URI env var (the
        real per-deployment service address, e.g. the in-cluster Neo4j
        service DNS name or a docker-desktop test target), but nothing
        ever read it; config.yaml's URI is a fixed string that can't vary
        per deployment. This is standard env-injected deployment
        configuration, not a "config in code" violation -- config.yaml
        still supplies the default for local/dogfooding use, the platform
        supplies the override for a real deployment."""
        cfg = dict(self._data.get("graph", {}).get("neo4j", {}))
        env_uri = os.environ.get("NEO4J_URI")
        if env_uri:
            cfg["uri"] = env_uri
        return cfg

    def get_connector_config(self, connector_id: str) -> dict:
        """Per-connector settings (e.g. connectors.application_code.athena),
        same password_env indirection as get_neo4j_config -- the secret
        itself never lives in a checked-in config.yaml.

        Same env-override pattern as get_neo4j_config() for the Athena
        connector specifically: ATHENA_DB_HOSTNAME/ATHENA_DB_PORT/
        ATHENA_DB_DATABASE/ATHENA_DB_USERNAME, already declared in
        metis-chart/values.yaml, override the corresponding config.yaml
        fields when set."""
        cfg = dict(self._data.get("connectors", {}).get(connector_id, {}))
        if connector_id == "application_code" and "athena" in cfg:
            athena = dict(cfg["athena"])
            if os.environ.get("ATHENA_DB_HOSTNAME"):
                athena["host"] = os.environ["ATHENA_DB_HOSTNAME"]
            if os.environ.get("ATHENA_DB_PORT"):
                athena["port"] = int(os.environ["ATHENA_DB_PORT"])
            if os.environ.get("ATHENA_DB_DATABASE"):
                athena["dbname"] = os.environ["ATHENA_DB_DATABASE"]
            if os.environ.get("ATHENA_DB_USERNAME"):
                athena["user"] = os.environ["ATHENA_DB_USERNAME"]
            cfg["athena"] = athena
        return cfg

    def get_token_optimization_config(self) -> dict:
        """§9.1's Headroom-style response-compression proxy is opt-in, not a
        silent default -- REQ-METIS-COST-01 requires the field-level
        provenance exclusion to be an explicit, guardrail-boundary-enforced
        configuration, not a tuning default that could accidentally start
        compressing source_episode_id/source_span. Missing entirely ->
        disabled, same 'no config in code, safe default' convention as
        get_graph_backend()."""
        return dict(self._data.get("token_optimization", {"headroom_enabled": False}))

    def get_transport(self) -> str:
        """'stdio' (default, Phase 0-5 dogfooding) or 'streamable-http'
        (Phase 6, production multi-client). MCP_TRANSPORT env var, if set
        (metis-chart/values.yaml already declares it for mcp-server), overrides
        config.yaml -- same real-deployment-override pattern as get_neo4j_config();
        this was previously declared in the chart but never actually read."""
        env_transport = os.environ.get("MCP_TRANSPORT")
        if env_transport:
            return env_transport
        return self._data.get("server", {}).get("transport", "stdio")

    def get_jwt_secret_env(self) -> str | None:
        return self._data.get("security", {}).get("jwt_secret_env")

    def get_server_public_url(self) -> str | None:
        """The real, externally-reachable Streamable HTTP URL (§11.2) --
        docs/metis-multi-client-integration.md's `REPLACE-metis-host...`
        placeholders resolve from here once a real hostname is chosen
        (still genuinely open, per that doc's own §4 -- no OAuth2 provider/
        hostname has been decided). None when unset, same 'don't guess'
        convention as every other config accessor here -- a caller (e.g.
        metis_mcp/copilot_integration.py) decides what to do with an
        unresolved URL, this method doesn't fabricate one."""
        return self._data.get("server", {}).get("public_url")

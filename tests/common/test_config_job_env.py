"""`job_env` of node.toml: environment for every job on a machine."""

import pytest

from mulebox.common.config import load_node_config
from mulebox.common.config_reader import ConfigError

BASE = """
name = "build-1"
roles = ["coordinator", "worker"]

[roots]
jobs = "/srv/mulebox/jobs"
cache = "/srv/mulebox/cache"
staging = "/srv/mulebox/staging"
runners = "/srv/mulebox/runners"
"""


def load(tmp_path, extra=""):
    path = tmp_path / "node.toml"
    path.write_text(BASE + extra)
    return load_node_config(path)


def test_it_is_empty_by_default(tmp_path):
    assert load(tmp_path).job_env == {}


def test_values_are_read(tmp_path):
    config = load(tmp_path, '[job_env]\nNODE_OPTIONS = "--flag=1"\nNPM_CONFIG_FETCH_RETRIES = "5"\n')
    assert config.job_env == {"NODE_OPTIONS": "--flag=1", "NPM_CONFIG_FETCH_RETRIES": "5"}


@pytest.mark.parametrize("name", ["PATH", "HOME", "USER", "SHELL", "MULEBOX_JOB_ID",
                                  "COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "BAD-NAME"])
def test_names_mulebox_owns_are_refused(tmp_path, name):
    with pytest.raises(ConfigError) as caught:
        load(tmp_path, f'[job_env]\n"{name}" = "x"\n')
    assert caught.value.field == f"job_env.{name}"


def test_values_must_be_strings(tmp_path):
    with pytest.raises(ConfigError):
        load(tmp_path, "[job_env]\nRETRIES = 5\n")

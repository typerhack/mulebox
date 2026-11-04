"""Environment names that change how a job starts are not a project's to set."""

import pytest

from mulebox.common import env_rules


@pytest.mark.parametrize("name", ["BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "PS4", "IFS",
                                  "GCONV_PATH", "BASH_FUNC_docker"])
@pytest.mark.parametrize("for_compose", [False, True])
def test_what_changes_how_the_shell_starts_is_refused_for_every_job(name, for_compose):
    assert "shell starts" in env_rules.problem(name, for_compose)


@pytest.mark.parametrize("name", ["LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT"])
def test_the_loader_is_refused_only_where_there_is_a_checked_file_to_protect(name):
    assert "before Docker Compose" in env_rules.problem(name, True)
    assert env_rules.problem(name, False) is None


@pytest.mark.parametrize("for_compose", [False, True])
def test_a_linker_setting_runs_nothing_at_start(for_compose):
    assert env_rules.problem("LD_RUN_PATH", for_compose) is None


def test_an_exported_function_cannot_get_through_on_its_odd_name():
    assert "shell variable" in env_rules.problem("BASH_FUNC_docker%%", False)


@pytest.mark.parametrize("name", ["COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_ENV_FILES",
                                  "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CLI_PLUGIN_X"])
def test_compose_and_docker_names_are_refused_only_for_compose_projects(name):
    assert "Compose" in env_rules.problem(name, True)
    assert env_rules.problem(name, False) is None


@pytest.mark.parametrize("name", ["DOCKER_BUILDKIT", "DOCKER_DEFAULT_PLATFORM", "CI", "APP_ENV",
                                  "NODE_OPTIONS", "ENVIRONMENT", "LDFLAGS"])
def test_ordinary_names_are_fine(name):
    assert env_rules.problem(name, True) is None


@pytest.mark.parametrize("name", ["PATH", "HOME", "USER", "SHELL", "MULEBOX_X"])
def test_what_mulebox_sets_stays_refused(name):
    assert "set by mulebox" in env_rules.problem(name, False)

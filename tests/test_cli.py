from click.testing import CliRunner

from anubis.main import cli


def test_given_root_command_when_help_is_requested_then_legacy_commands_are_excluded() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "bitwarden" in result.output
    assert "check" in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "docker" not in result.output
    assert "airflow" not in result.output
    assert "\n  init " not in result.output
    assert "\n  verify " not in result.output


def test_given_check_command_when_help_is_requested_then_environment_validation_is_available() -> (
    None
):
    result = CliRunner().invoke(cli, ["check", "--help"])

    assert result.exit_code == 0
    assert "\n  environment " in result.output
    assert "\n  repository " not in result.output


def test_given_cluster_command_when_help_is_requested_then_check_is_excluded() -> None:
    result = CliRunner().invoke(cli, ["cluster", "--help"])

    assert result.exit_code == 0
    assert "\n  check " not in result.output
    assert "\n  prepare " in result.output
    assert "\n  plan " in result.output
    assert "\n  destroy " in result.output


def test_given_product_commands_when_help_is_requested_then_refresh_option_is_available() -> None:
    runner = CliRunner()

    for command in ("install", "deploy", "start", "update"):
        result = runner.invoke(cli, [command, "--help"])
        assert result.exit_code == 0
        assert "--refresh" in result.output


def test_given_product_commands_when_help_is_requested_then_installation_is_optional() -> None:
    runner = CliRunner()

    for command in ("install", "deploy", "start", "stop", "update", "destroy"):
        result = runner.invoke(cli, [command, "--help"])
        assert result.exit_code == 0
        assert "[INSTALLATION]" in result.output


def test_given_cluster_setup_commands_when_help_is_requested_then_become_override_is_available() -> (
    None
):
    runner = CliRunner()

    for command in (["install"], ["cluster", "prepare"]):
        result = runner.invoke(cli, [*command, "--help"])
        assert result.exit_code == 0
        assert "--ask-become-pass / --no-ask-become-pass" in result.output


def test_given_cli_when_version_is_requested_then_version_is_available() -> None:
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert "anubis, version" in result.output


def test_given_shell_name_when_completion_is_requested_then_script_is_available() -> None:
    result = CliRunner().invoke(cli, ["--print-completion-script", "zsh"])

    assert result.exit_code == 0
    assert "_anubis_completion" in result.output

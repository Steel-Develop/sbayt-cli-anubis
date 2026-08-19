import subprocess

import pytest

from anubis.errors import AnubisError
from anubis.process import Runner


def test_given_environment_override_when_command_runs_then_arguments_are_safe_and_value_is_removed(
    monkeypatch,
) -> None:
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("PRIVATE_VALUE", "must-not-be-inherited")
    monkeypatch.setattr(subprocess, "run", fake_run)

    Runner().run(["example", "argument"], env={"PRIVATE_VALUE": None})

    assert observed["command"] == ["example", "argument"]
    assert "PRIVATE_VALUE" not in observed["environment"]


def test_given_missing_executable_when_command_runs_then_error_has_no_traceback(
    monkeypatch,
) -> None:
    def fail(*args, **kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(subprocess, "run", fail)

    with pytest.raises(AnubisError, match="cannot execute example"):
        Runner().run(["example"])

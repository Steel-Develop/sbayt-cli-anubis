import json
import subprocess

import pytest

from anubis import bitwarden
from anubis.bitwarden import BitwardenClient, access_token, select_project
from anubis.errors import AnubisError

PROJECTS = [
    {"id": "development-id", "organizationId": "org", "name": "Development"},
    {"id": "production-id", "organizationId": "org", "name": "Production"},
]


class RecordingRunner:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps(self.response), "")


def test_given_bws_1_when_projects_requested_then_current_command_syntax_is_used(
    monkeypatch,
) -> None:
    runner = RecordingRunner(PROJECTS)
    monkeypatch.setattr(bitwarden.shutil, "which", lambda name: f"/bin/{name}")

    assert BitwardenClient(runner, "machine-token").projects() == PROJECTS
    assert runner.calls == [
        (
            ["bws", "project", "list", "--output", "json"],
            {
                "env": {"BWS_ACCESS_TOKEN": "machine-token"},
                "capture": True,
                "sensitive": True,
            },
        )
    ]


def test_given_bws_1_when_secrets_requested_then_current_command_syntax_is_used(
    monkeypatch,
) -> None:
    response = [{"key": "AWS_ACCESS_KEY_ID", "value": "access-key"}]
    runner = RecordingRunner(response)
    monkeypatch.setattr(bitwarden.shutil, "which", lambda name: f"/bin/{name}")

    assert BitwardenClient(runner, "machine-token").secrets("project-id") == {
        "AWS_ACCESS_KEY_ID": "access-key"
    }
    assert runner.calls[0][0] == [
        "bws",
        "secret",
        "list",
        "project-id",
        "--output",
        "json",
    ]


def test_given_project_name_or_id_when_selected_then_matching_project_is_returned() -> None:
    assert select_project(PROJECTS, "Development")["id"] == "development-id"
    assert select_project(PROJECTS, "production-id")["name"] == "Production"


def test_given_unknown_project_when_selected_then_operation_is_rejected() -> None:
    with pytest.raises(AnubisError, match="not found"):
        select_project(PROJECTS, "missing")


def test_given_prompted_access_token_when_requested_twice_then_prompt_occurs_once(
    monkeypatch,
) -> None:
    prompts = []
    monkeypatch.delenv("BWS_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(bitwarden, "_prompted_access_token", None)
    monkeypatch.setattr(bitwarden.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        bitwarden.getpass,
        "getpass",
        lambda message: prompts.append(message) or "machine-token",
    )

    assert access_token() == "machine-token"
    assert access_token() == "machine-token"
    assert len(prompts) == 1

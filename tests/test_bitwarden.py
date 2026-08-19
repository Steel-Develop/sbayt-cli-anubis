import pytest

from anubis import bitwarden
from anubis.bitwarden import access_token, select_project
from anubis.errors import AnubisError

PROJECTS = [
    {"id": "development-id", "organizationId": "org", "name": "Development"},
    {"id": "production-id", "organizationId": "org", "name": "Production"},
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

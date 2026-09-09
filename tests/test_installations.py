import stat
from pathlib import Path

import pytest
import yaml

import anubis.installations as installation_context
from anubis.errors import AnubisError
from anubis.installations import (
    context_path,
    initialize,
    needs_context,
    resolved_manifest,
    resolved_values,
)
from anubis.process import Runner
from anubis.repository import Installation, Repository


def test_given_external_context_when_values_are_resolved_then_installation_is_not_modified(
    tmp_path: Path,
) -> None:
    source = tmp_path / "installation.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "name": "local",
                "clusterProfile": "kind",
                "productProfile": "full",
                "kubeContext": "kind-local",
                "secrets": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    installation = Installation(source, yaml.safe_load(source.read_text()))
    context = {
        "project": {"id": "project", "organizationID": "organization"},
        "values": {"runtime.bootstrapUsers.mongodb": "database-user"},
    }

    result = resolved_values(installation, context)

    assert result["secrets"]["bitwarden"]["projectID"] == "project"
    assert result["runtime"]["bootstrapUsers"]["mongodb"] == "database-user"
    assert "bitwarden" not in yaml.safe_load(source.read_text())["secrets"]


def test_given_complete_installation_when_config_is_absent_then_manifest_is_resolved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "installations" / "local" / "installation.yaml"
    source.parent.mkdir(parents=True)
    values = {
        "name": "local",
        "clusterProfile": "kind",
        "productProfile": "full",
        "kubeContext": "kind-local",
        "secrets": {
            "enabled": True,
            "bitwarden": {"projectID": "project", "organizationID": "organization"},
        },
    }
    source.write_text(yaml.safe_dump(values), encoding="utf-8")
    repository = Repository(tmp_path, {})
    installation = Installation(source, values)

    with resolved_manifest(repository, installation, Runner()) as generated:
        assert generated.is_file()
        assert yaml.safe_load(generated.read_text()) == values

    assert not generated.exists()


def test_given_effective_configuration_when_context_is_checked_then_bindings_are_used(
    tmp_path: Path,
) -> None:
    source = tmp_path / "installation.yaml"
    values = {
        "name": "local",
        "clusterProfile": "kind",
        "kubeContext": "kind-local",
        "secrets": {"enabled": True},
    }
    source.write_text(yaml.safe_dump(values), encoding="utf-8")
    repository = Repository(tmp_path, {})
    installation = Installation(source, values)

    assert needs_context(
        repository,
        installation,
        {"bitwarden": {"bindings": {"runtime.bootstrapUsers.mongodb": "MONGO_USER"}}},
    )

    installation.values["runtime"] = {"bootstrapUsers": {"mongodb": "explicit-user"}}
    installation.values["secrets"]["bitwarden"] = {
        "organizationID": "organization",
        "projectID": "project",
    }
    assert not needs_context(
        repository,
        installation,
        {},
    )


def test_given_repository_bindings_when_values_are_resolved_then_existing_values_are_replaced(
    tmp_path: Path,
) -> None:
    installation = Installation(
        tmp_path / "installation.yaml",
        {
            "name": "local",
            "clusterProfile": "kind",
            "kubeContext": "kind-local",
            "runtime": {"bootstrapUsers": {"mongodb": "existing-user"}},
        },
    )

    result = resolved_values(
        installation,
        {
            "project": {"id": "new-project", "organizationID": "new-organization"},
            "values": {"runtime.bootstrapUsers.mongodb": "resolved-user"},
        },
    )

    assert result["runtime"]["bootstrapUsers"]["mongodb"] == "resolved-user"
    assert result["secrets"]["bitwarden"]["projectID"] == "new-project"


def test_given_resolved_context_when_initialized_then_private_context_is_written(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "installation.yaml"
    values = {
        "name": "local",
        "clusterProfile": "kind",
        "kubeContext": "kind-local",
        "secrets": {"enabled": True},
    }
    source.write_text(yaml.safe_dump(values), encoding="utf-8")
    repository = Repository(tmp_path, {})
    installation = Installation(source, values)

    class Client:
        def __init__(self, runner, token):
            assert token == "machine-token"

        def projects(self):
            return [{"id": "project", "organizationId": "organization", "name": "Dev"}]

        def secrets(self, project_id):
            assert project_id == "project"
            return {"MONGO_USER": "database-user"}

    monkeypatch.setenv("BWS_ACCESS_TOKEN", "machine-token")
    monkeypatch.setattr(installation_context, "BitwardenClient", Client)

    result = initialize(
        repository,
        installation,
        Runner(),
        configuration={
            "bitwarden": {"bindings": {"runtime.bootstrapUsers.mongodb": "MONGO_USER"}}
        },
    )
    destination = context_path(repository, installation)

    assert result["values"] == {"runtime.bootstrapUsers.mongodb": "database-user"}
    assert "machine-token" not in destination.read_text(encoding="utf-8")
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_given_missing_binding_when_context_is_refreshed_then_previous_context_is_preserved(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "installation.yaml"
    values = {
        "name": "local",
        "clusterProfile": "kind",
        "kubeContext": "kind-local",
        "secrets": {"enabled": True},
    }
    source.write_text(yaml.safe_dump(values), encoding="utf-8")
    repository = Repository(tmp_path, {})
    installation = Installation(source, values)
    destination = context_path(repository, installation)
    destination.parent.mkdir(parents=True)
    destination.write_text("valid: context\n", encoding="utf-8")

    class Client:
        def __init__(self, runner, token):
            pass

        def projects(self):
            return [{"id": "project", "organizationId": "organization", "name": "Dev"}]

        def secrets(self, project_id):
            return {}

    monkeypatch.setenv("BWS_ACCESS_TOKEN", "machine-token")
    monkeypatch.setattr(installation_context, "BitwardenClient", Client)

    with pytest.raises(AnubisError, match="missing or empty"):
        initialize(
            repository,
            installation,
            Runner(),
            configuration={
                "bitwarden": {"bindings": {"runtime.bootstrapUsers.mongodb": "MONGO_USER"}}
            },
            refresh=True,
        )

    assert destination.read_text(encoding="utf-8") == "valid: context\n"


def test_given_legacy_context_when_manifest_is_resolved_then_explicit_refresh_is_required(
    tmp_path: Path,
) -> None:
    source = tmp_path / "installation.yaml"
    values = {
        "name": "local",
        "clusterProfile": "kind",
        "kubeContext": "kind-local",
        "secrets": {"enabled": True},
    }
    source.write_text(yaml.safe_dump(values), encoding="utf-8")
    repository = Repository(tmp_path, {})
    installation = Installation(source, values)
    destination = context_path(repository, installation)
    destination.parent.mkdir(parents=True)
    destination.write_text(
        yaml.safe_dump(
            {
                "project": {"id": "project"},
                "values": {"data.mongodb.username": "legacy-user"},
            }
        ),
        encoding="utf-8",
    )

    with (
        pytest.raises(AnubisError, match="deploy, or update with --refresh"),
        resolved_manifest(
            repository,
            installation,
            Runner(),
            configuration={
                "bitwarden": {"bindings": {"runtime.bootstrapUsers.mongodb": "MONGO_USER"}}
            },
        ),
    ):
        pass


def test_given_existing_context_when_manifest_is_refreshed_then_new_context_is_applied(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "installation.yaml"
    values = {
        "name": "local",
        "clusterProfile": "kind",
        "kubeContext": "kind-local",
        "secrets": {"enabled": True},
    }
    source.write_text(yaml.safe_dump(values), encoding="utf-8")
    repository = Repository(tmp_path, {})
    installation = Installation(source, values)
    destination = context_path(repository, installation)
    destination.parent.mkdir(parents=True)
    destination.write_text(
        yaml.safe_dump(
            {
                "project": {
                    "id": "old-project",
                    "organizationID": "old-organization",
                    "name": "Old",
                },
                "values": {"runtime.bootstrapUsers.mongodb": "old-user"},
            }
        ),
        encoding="utf-8",
    )

    class Client:
        def __init__(self, runner, token):
            assert token == "machine-token"

        def projects(self):
            return [{"id": "new-project", "organizationId": "new-organization", "name": "New"}]

        def secrets(self, project_id):
            assert project_id == "new-project"
            return {"MONGO_USER": "new-user"}

    monkeypatch.setenv("BWS_ACCESS_TOKEN", "machine-token")
    monkeypatch.setattr(installation_context, "BitwardenClient", Client)

    with resolved_manifest(
        repository,
        installation,
        Runner(),
        configuration={
            "bitwarden": {"bindings": {"runtime.bootstrapUsers.mongodb": "MONGO_USER"}}
        },
        refresh=True,
    ) as generated:
        resolved = yaml.safe_load(generated.read_text(encoding="utf-8"))

    assert resolved["secrets"]["bitwarden"]["projectID"] == "new-project"
    assert resolved["runtime"]["bootstrapUsers"]["mongodb"] == "new-user"

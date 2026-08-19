"""Resolve installation metadata without modifying versioned manifests."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from anubis.bitwarden import BitwardenClient, access_token, select_project
from anubis.config import get_path, set_path
from anubis.errors import AnubisError
from anubis.process import Runner
from anubis.repository import Installation, Repository


def context_path(repository: Repository, installation: Installation) -> Path:
    installations = repository.root / "installations"
    try:
        identifier = installation.path.parent.relative_to(installations)
    except ValueError:
        identifier = Path(installation.name)
    return repository.work / "anubis" / identifier / "context.yaml"


def _bindings(configuration: Mapping[str, Any]) -> dict[str, str]:
    value = get_path(configuration, "bitwarden.bindings", {})
    if value is None:
        return {}
    if not isinstance(value, Mapping) or any(
        not isinstance(path, str) or not isinstance(key, str) for path, key in value.items()
    ):
        raise AnubisError("anubis.yaml bitwarden.bindings must map paths to secret keys")
    return dict(value)


def load_context(repository: Repository, installation: Installation) -> dict[str, Any] | None:
    source = context_path(repository, installation)
    if not source.is_file():
        return None
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise AnubisError(f"cannot read local installation context: {source}: {error}") from error
    if not isinstance(value, dict):
        raise AnubisError(f"local installation context must be a mapping: {source}")
    return value


def initialize(
    repository: Repository,
    installation: Installation,
    runner: Runner,
    *,
    configuration: Mapping[str, Any] | None = None,
    project_selector: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    existing = load_context(repository, installation)
    if existing is not None and not refresh:
        return existing

    token = access_token()
    if token is None:
        raise AnubisError("set BWS_ACCESS_TOKEN to resolve the Bitwarden context")
    client = BitwardenClient(runner, token)
    project = select_project(client.projects(), project_selector)
    bindings = _bindings(configuration or repository.config)
    secrets = client.secrets(project["id"]) if bindings else {}

    resolved: dict[str, str] = {}
    for target, key in bindings.items():
        value = secrets.get(key, "").strip()
        if not value:
            raise AnubisError(f"Bitwarden key is missing or empty: {key}")
        resolved[target] = value

    context: dict[str, Any] = {
        "project": {
            "id": project["id"],
            "organizationID": project["organizationId"],
            "name": project["name"],
        },
        "values": resolved,
    }
    destination = context_path(repository, installation)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(yaml.safe_dump(context, sort_keys=False), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, destination)
    return context


def resolved_values(
    installation: Installation, context: Mapping[str, Any] | None
) -> dict[str, Any]:
    values = deepcopy(installation.values)
    if context is None:
        return values
    project = context.get("project", {})
    if isinstance(project, Mapping):
        project_id = project.get("id")
        organization_id = project.get("organizationID")
        if isinstance(project_id, str):
            set_path(values, "secrets.bitwarden.projectID", project_id)
        if isinstance(organization_id, str):
            set_path(values, "secrets.bitwarden.organizationID", organization_id)
    bindings = context.get("values", {})
    if isinstance(bindings, Mapping):
        for path, value in bindings.items():
            if isinstance(path, str) and isinstance(value, str):
                set_path(values, path, value)
    return values


def needs_context(
    repository: Repository,
    installation: Installation,
    configuration: Mapping[str, Any] | None = None,
) -> bool:
    bindings = _bindings(configuration or repository.config)
    enabled = get_path(installation.values, "secrets.enabled", False)
    if bindings and enabled:
        return True
    project_id = get_path(installation.values, "secrets.bitwarden.projectID")
    organization_id = get_path(installation.values, "secrets.bitwarden.organizationID")
    return bool(enabled and (not project_id or not organization_id))


def _validate_context(context: Mapping[str, Any], configuration: Mapping[str, Any]) -> None:
    values = context.get("values", {})
    resolved = values if isinstance(values, Mapping) else {}
    missing = [path for path in _bindings(configuration) if not resolved.get(path)]
    if missing:
        names = ", ".join(sorted(missing))
        raise AnubisError(
            f"local context is missing bindings ({names}); "
            "rerun install, deploy, or update with --refresh"
        )


@contextmanager
def resolved_manifest(
    repository: Repository,
    installation: Installation,
    runner: Runner,
    *,
    configuration: Mapping[str, Any] | None = None,
    project_selector: str | None = None,
    refresh: bool = False,
) -> Iterator[Path]:
    context = load_context(repository, installation)
    if refresh:
        context = initialize(
            repository,
            installation,
            runner,
            configuration=configuration,
            project_selector=project_selector,
            refresh=True,
        )
    elif context is None and needs_context(repository, installation, configuration):
        context = initialize(
            repository,
            installation,
            runner,
            configuration=configuration,
            project_selector=project_selector,
        )
    if context is not None:
        _validate_context(context, configuration or repository.config)
    work = repository.work / "anubis" / installation.name
    work.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="installation-", suffix=".yaml", dir=work)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            yaml.safe_dump(resolved_values(installation, context), stream, sort_keys=False)
        path.chmod(0o600)
        yield path
    finally:
        path.unlink(missing_ok=True)

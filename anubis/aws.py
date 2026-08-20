"""AWS and CodeArtifact operations retained from Anubis legacy."""

from __future__ import annotations

import json
import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anubis.bitwarden import BitwardenClient, access_token, select_project
from anubis.config import get_path
from anubis.errors import AnubisError
from anubis.process import Runner
from anubis.tools import ensure_uv, install_aws, install_bws

AWS_KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
UV_CONFIG = Path.home() / ".config" / "uv" / "uv.toml"
UV_MARKER = "# Managed by Anubis\n"


@dataclass(frozen=True)
class AwsSettings:
    region: str
    account_id: str
    domain: str
    repository: str

    @classmethod
    def resolve(cls, config: dict[str, Any], overrides: dict[str, str | None]) -> AwsSettings:
        def value(name: str, path: str, *environment: str) -> str:
            explicit = overrides.get(name)
            if explicit:
                return explicit
            for variable in environment:
                candidate = os.environ.get(variable, "").strip()
                if candidate:
                    return candidate
            candidate = get_path(config, path)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            raise AnubisError(
                f"missing {path}; pass the corresponding option, environment variable, "
                "global config, or optional anubis.yaml"
            )

        return cls(
            region=value("region", "aws.region", "ANUBIS_AWS_REGION", "AWS_REGION"),
            account_id=value(
                "account_id", "aws.accountID", "ANUBIS_AWS_ACCOUNT_ID", "AWS_ACCOUNT_ID"
            ),
            domain=value("domain", "aws.codeArtifact.domain", "ANUBIS_CODEARTIFACT_DOMAIN"),
            repository=value(
                "repository",
                "aws.codeArtifact.repository",
                "ANUBIS_CODEARTIFACT_REPOSITORY",
            ),
        )


def credential_environment(
    runner: Runner, *, project_selector: str | None = None
) -> dict[str, str]:
    ambient = {key: os.environ[key] for key in AWS_KEYS if os.environ.get(key)}
    if ambient.get("AWS_ACCESS_KEY_ID") and ambient.get("AWS_SECRET_ACCESS_KEY"):
        return ambient

    token = access_token()
    if token is None:
        raise AnubisError(
            "AWS credentials are unavailable; set AWS credentials or BWS_ACCESS_TOKEN"
        )
    install_bws(runner)
    client = BitwardenClient(runner, token)
    project = select_project(client.projects(), project_selector)
    secrets = client.secrets(project["id"])
    credentials = {key: secrets[key] for key in AWS_KEYS if secrets.get(key)}
    if not credentials.get("AWS_ACCESS_KEY_ID") or not credentials.get("AWS_SECRET_ACCESS_KEY"):
        raise AnubisError("the selected Bitwarden project has no complete AWS credentials")
    return credentials


def codeartifact_token(
    runner: Runner,
    settings: AwsSettings,
    *,
    project_selector: str | None = None,
) -> str:
    install_aws(runner)
    result = runner.run(
        [
            "aws",
            "codeartifact",
            "get-authorization-token",
            "--domain",
            settings.domain,
            "--domain-owner",
            settings.account_id,
            "--region",
            settings.region,
            "--output",
            "json",
        ],
        env=credential_environment(runner, project_selector=project_selector),
        capture=True,
        sensitive=True,
    )
    try:
        value = json.loads(result.stdout).get("authorizationToken")
    except (AttributeError, json.JSONDecodeError) as error:
        raise AnubisError("AWS returned an invalid CodeArtifact response") from error
    if not isinstance(value, str) or not value:
        raise AnubisError("AWS returned an empty CodeArtifact token")
    return value


def configure_pip(
    runner: Runner,
    settings: AwsSettings,
    *,
    project_selector: str | None = None,
) -> None:
    if shutil.which("pip") is None:
        raise AnubisError("pip is required")
    install_aws(runner)
    runner.run(
        [
            "aws",
            "codeartifact",
            "login",
            "--tool",
            "pip",
            "--domain",
            settings.domain,
            "--domain-owner",
            settings.account_id,
            "--repository",
            settings.repository,
            "--region",
            settings.region,
        ],
        env=credential_environment(runner, project_selector=project_selector),
        sensitive=True,
    )


def configure_uv(
    runner: Runner,
    settings: AwsSettings,
    *,
    project_selector: str | None = None,
) -> None:
    ensure_uv(runner)
    token = codeartifact_token(runner, settings, project_selector=project_selector)
    url = (
        f"https://aws:{token}@{settings.domain}-{settings.account_id}.d.codeartifact."
        f"{settings.region}.amazonaws.com/pypi/{settings.repository}/simple/"
    )
    UV_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    UV_CONFIG.write_text(
        f'{UV_MARKER}[[index]]\nurl = "{url}"\ndefault = true\n', encoding="utf-8"
    )
    UV_CONFIG.chmod(0o600)


def reset_package_indexes(runner: Runner) -> None:
    if shutil.which("pip"):
        configured = runner.run(
            ["pip", "config", "get", "global.index-url"],
            capture=True,
            check=False,
        )
        if configured.returncode == 0 and ".d.codeartifact." in configured.stdout:
            runner.run(["pip", "config", "unset", "global.index-url"])
    if UV_CONFIG.is_file():
        content = UV_CONFIG.read_text(encoding="utf-8")
        if not content.startswith(UV_MARKER):
            raise AnubisError(f"refusing to remove uv config not managed by Anubis: {UV_CONFIG}")
        UV_CONFIG.unlink()


def shell_export(name: str, value: str) -> str:
    return f"export {name}={shlex.quote(value)}"

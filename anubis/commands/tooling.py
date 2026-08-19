"""Configuration, Bitwarden and AWS commands."""

from __future__ import annotations

from typing import Any

import click
import yaml

from anubis.application import Application
from anubis.aws import (
    AwsSettings,
    codeartifact_token,
    configure_pip,
    configure_uv,
    reset_package_indexes,
    shell_export,
)
from anubis.config import load_global_config, write_global_config
from anubis.tools import install_aws, install_bws, remove_aws, remove_bws


@click.group("config")
def config_group() -> None:
    """Manage non-secret user defaults."""


@config_group.command("init")
@click.option("--aws-region")
@click.option("--aws-account-id")
@click.option("--codeartifact-domain")
@click.option("--codeartifact-repository")
def config_init(
    aws_region: str | None,
    aws_account_id: str | None,
    codeartifact_domain: str | None,
    codeartifact_repository: str | None,
) -> None:
    """Create or replace the global non-secret configuration."""
    values: dict[str, Any] = {}
    aws = {
        key: value
        for key, value in {"region": aws_region, "accountID": aws_account_id}.items()
        if value
    }
    codeartifact = {
        key: value
        for key, value in {
            "domain": codeartifact_domain,
            "repository": codeartifact_repository,
        }.items()
        if value
    }
    if codeartifact:
        aws["codeArtifact"] = codeartifact
    if aws:
        values["aws"] = aws
    click.echo(write_global_config(values))


@config_group.command("show")
def config_show() -> None:
    """Print the global non-secret configuration."""
    click.echo(yaml.safe_dump(load_global_config(), sort_keys=False).rstrip())


@click.group("bitwarden")
def bitwarden_group() -> None:
    """Manage the Bitwarden Secrets Manager CLI."""


@bitwarden_group.command("install")
@click.pass_obj
def bitwarden_install(application: Application) -> None:
    """Install bws locally."""
    install_bws(application.runner)


@bitwarden_group.command("remove")
def bitwarden_remove() -> None:
    """Remove the locally installed bws binary."""
    remove_bws()


@click.group("aws")
@click.option("--region")
@click.option("--account-id")
@click.option("--domain")
@click.option("--codeartifact-repository", "artifact_repository")
@click.option("--project", help="Bitwarden project name or ID used for AWS credentials.")
@click.pass_context
def aws_group(
    context: click.Context,
    region: str | None,
    account_id: str | None,
    domain: str | None,
    artifact_repository: str | None,
    project: str | None,
) -> None:
    """Manage AWS and CodeArtifact tooling."""
    context.meta["aws_overrides"] = {
        "region": region,
        "account_id": account_id,
        "domain": domain,
        "repository": artifact_repository,
    }
    context.meta["aws_project"] = project


def _aws_context(context: click.Context) -> tuple[Application, AwsSettings, str | None]:
    application: Application = context.find_root().obj
    settings = AwsSettings.resolve(
        application.configuration(), context.parent.meta["aws_overrides"]
    )
    return application, settings, context.parent.meta["aws_project"]


@aws_group.command("install")
@click.pass_obj
def aws_install(application: Application) -> None:
    """Install AWS CLI locally."""
    install_aws(application.runner)


@aws_group.command("remove")
def aws_remove() -> None:
    """Remove the locally installed AWS CLI."""
    remove_aws()


@aws_group.command("configure-pip")
@click.pass_context
def aws_configure_pip(context: click.Context) -> None:
    """Configure pip for the selected CodeArtifact repository."""
    application, settings, project = _aws_context(context)
    configure_pip(application.runner, settings, project_selector=project)


@aws_group.command("configure-uv")
@click.pass_context
def aws_configure_uv(context: click.Context) -> None:
    """Replace the user uv config with the selected CodeArtifact repository."""
    application, settings, project = _aws_context(context)
    configure_uv(application.runner, settings, project_selector=project)


@aws_group.command("reset")
@click.pass_obj
def aws_reset(application: Application) -> None:
    """Restore public package indexes managed by Anubis."""
    reset_package_indexes(application.runner)


@aws_group.command("token")
@click.option("--format", "output_format", type=click.Choice(["text", "shell"]), default="text")
@click.pass_context
def aws_token(context: click.Context, output_format: str) -> None:
    """Print a short-lived CodeArtifact token."""
    application, settings, project = _aws_context(context)
    token = codeartifact_token(application.runner, settings, project_selector=project)
    click.echo(
        shell_export("CODEARTIFACT_AUTH_TOKEN", token) if output_format == "shell" else token
    )

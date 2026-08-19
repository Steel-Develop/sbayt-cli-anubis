"""Local environment checks."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import click

from anubis.application import Application
from anubis.errors import AnubisError


@click.group("check")
def check_group() -> None:
    """Validate the local development environment."""


@check_group.command("environment")
@click.argument("installation", required=False)
@click.pass_obj
def check_environment(application: Application, installation: str | None) -> None:
    """Check tools required by the selected workflow."""
    tools = ["aws", "bws", "curl", "pip", "unzip", "uv"]
    selected = None
    if installation:
        selected = application.repository().select_installation(installation)
    else:
        try:
            selected = application.repository().select_installation(None, required=False)
        except AnubisError as error:
            if not str(error).startswith("IaC repository not found"):
                raise
    if selected is not None:
        tools.extend(["helm", "helmfile", "kubectl"])
        cluster_tools = (
            ["docker", "kind"] if selected.cluster_profile == "kind" else ["terraform", "ssh"]
        )
        tools.extend(cluster_tools)
    missing = sorted({tool for tool in tools if shutil.which(tool) is None})
    if missing:
        raise AnubisError(f"missing tools: {', '.join(missing)}")
    local_bin = Path.home() / ".local/bin"
    managed_tools = any((local_bin / tool).is_file() for tool in ("aws", "bws"))
    search_path = os.environ.get("PATH", "").split(os.pathsep)
    if managed_tools and str(local_bin) not in search_path:
        raise AnubisError(f"{local_bin} contains managed tools but is not in PATH")
    click.echo("Environment is ready")

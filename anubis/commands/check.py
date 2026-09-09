"""Read-only local environment checks."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

import click
import yaml

from anubis.application import Application
from anubis.cluster import is_managed_lab
from anubis.config import get_path
from anubis.errors import AnubisError
from anubis.repository import Installation
from anubis.tools import (
    BWS_VERSION,
    UV_MINIMUM_VERSION,
    ToolStatus,
    inspect_exact_tool,
    inspect_helm_diff,
    project_toolchain,
    tool_version,
    version_tuple,
)


@click.group("check")
def check_group() -> None:
    """Validate the local development environment."""


def _selected(application: Application, reference: str | None) -> Installation | None:
    try:
        repository = application.repository()
    except AnubisError as error:
        if reference is None and str(error).startswith("IaC repository not found"):
            return None
        raise
    return (
        repository.installation(reference)
        if reference is not None
        else repository.select_installation(None, required=False)
    )


def _show(status: ToolStatus) -> None:
    found = status.version or "missing/unusable"
    path = str(status.path) if status.path else "-"
    state = "OK" if status.ready else "ERROR"
    click.echo(
        f"{state:<5} {status.name:<12} expected={status.expected:<10} found={found:<14} {path}"
    )


def _external_status(name: str, expected: str = "installed") -> ToolStatus:
    path = shutil.which(name)
    return ToolStatus(
        name, expected, Path(path) if path else None, expected if path else None, bool(path)
    )


def _command_ready(application: Application, command: list[str]) -> bool:
    result = application.runner.run(command, capture=True, check=False)
    return result.returncode == 0


def _uses_local_connection(installation: Installation) -> bool:
    source = installation.path.parent / "inventory.yaml"
    if not source.is_file():
        source = installation.path.parent / "inventory.yml"
    if not source.is_file():
        return False
    try:
        values = yaml.safe_load(source.read_text(encoding="utf-8"))
        hosts = values["all"]["children"]["rke2_servers"]["hosts"]
    except (KeyError, OSError, TypeError, yaml.YAMLError) as error:
        raise AnubisError(f"cannot inspect RKE2 inventory: {source}: {error}") from error
    return isinstance(hosts, Mapping) and any(
        isinstance(settings, Mapping) and settings.get("ansible_connection") == "local"
        for settings in hosts.values()
    )


@check_group.command("environment")
@click.argument("installation", required=False)
@click.pass_obj
def check_environment(application: Application, installation: str | None) -> None:
    """Check versions and system dependencies without installing or changing anything."""
    selected = _selected(application, installation)
    python_version = platform.python_version()
    statuses: list[ToolStatus] = [
        ToolStatus(
            "python",
            ">=3.12",
            Path(sys.executable),
            python_version,
            version_tuple(python_version) >= (3, 12, 0),
        )
    ]
    extra_errors: list[str] = []

    if selected is None:
        aws_version, aws_path = tool_version("aws", application.runner)
        statuses.append(
            ToolStatus(
                "aws",
                "major 2",
                aws_path,
                aws_version,
                bool(aws_version and version_tuple(aws_version)[0] == 2),
            )
        )
        statuses.append(inspect_exact_tool("bws", BWS_VERSION, application.runner))
        uv_version, uv_path = tool_version("uv", application.runner)
        statuses.append(
            ToolStatus(
                "uv",
                ">=0.11",
                uv_path,
                uv_version,
                bool(uv_version and version_tuple(uv_version) >= UV_MINIMUM_VERSION),
            )
        )
        statuses.append(_external_status("pip"))
    else:
        repository = application.repository()
        versions = project_toolchain(repository.config)
        for name in ("helm", "helmfile", "kubectl"):
            statuses.append(inspect_exact_tool(name, versions[name], application.runner))
        statuses.append(inspect_helm_diff(repository.config, application.runner))

        if get_path(selected.values, "secrets.enabled", False):
            statuses.append(inspect_exact_tool("bws", BWS_VERSION, application.runner))
        if selected.cluster_profile == "kind":
            statuses.append(inspect_exact_tool("kind", versions["kind"], application.runner))
            docker = _external_status("docker", "daemon ready")
            if docker.ready and not _command_ready(application, ["docker", "info"]):
                docker = ToolStatus("docker", "daemon ready", docker.path, "unavailable", False)
            statuses.append(docker)
        else:
            statuses.append(_external_status("ssh"))
            if _uses_local_connection(selected):
                statuses.append(_external_status("sudo"))
            if is_managed_lab(selected):
                statuses.append(
                    inspect_exact_tool("terraform", versions["terraform"], application.runner)
                )
                virsh = _external_status("virsh", "libvirt ready")
                if virsh.ready and not _command_ready(
                    application, ["virsh", "-c", "qemu:///system", "list"]
                ):
                    virsh = ToolStatus("virsh", "libvirt ready", virsh.path, "unavailable", False)
                statuses.append(virsh)
                kvm = Path("/dev/kvm")
                if not kvm.exists() or not os.access(kvm, os.R_OK | os.W_OK):
                    extra_errors.append("/dev/kvm is missing or is not readable and writable")
                release = Path("/proc/sys/kernel/osrelease")
                kernel = release.read_text(encoding="utf-8") if release.is_file() else ""
                if platform.system() != "Linux" or "microsoft" in kernel.lower():
                    extra_errors.append("managed libvirt labs require native Linux")

    for status in statuses:
        _show(status)
    for message in extra_errors:
        click.echo(f"ERROR system       {message}")

    failed = [status.name for status in statuses if not status.ready]
    if failed or extra_errors:
        names = ", ".join(failed + extra_errors)
        raise AnubisError(f"environment is not ready: {names}")
    click.echo("Environment is ready")

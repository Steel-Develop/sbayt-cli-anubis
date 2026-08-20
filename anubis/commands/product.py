"""Installation and product lifecycle commands."""

from __future__ import annotations

from pathlib import Path

import click

from anubis.application import Application
from anubis.commands.cluster import prepare_cluster
from anubis.errors import AnubisError
from anubis.installations import resolved_manifest
from anubis.kubernetes import Kubernetes, kubeconfig_path


def _operation(application: Application, reference: str | None, kubeconfig: Path | None):
    repository = application.repository()
    installation = repository.select_installation(reference)
    assert installation is not None
    return repository, installation, kubeconfig_path(repository, installation, kubeconfig)


def _converge(
    application: Application,
    installation: str | None,
    kubeconfig: Path | None,
    *,
    component: str | None = None,
    project: str | None = None,
    refresh: bool = False,
    apply: bool = False,
) -> None:
    repository, selected, resolved_kubeconfig = _operation(application, installation, kubeconfig)
    with resolved_manifest(
        repository,
        selected,
        application.runner,
        configuration=application.configuration(),
        project_selector=project,
        refresh=refresh,
    ) as manifest:
        Kubernetes(repository, selected, manifest, resolved_kubeconfig, application.runner).deploy(
            component=component,
            apply=apply,
        )


@click.command("deploy")
@click.argument("installation", required=False)
@click.option("--kubeconfig", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--component")
@click.option("--project", help="Bitwarden project name or ID when initialization is needed.")
@click.option("--refresh", is_flag=True, help="Refresh the cached Bitwarden context.")
@click.pass_obj
def deploy(
    application: Application,
    installation: str | None,
    kubeconfig: Path | None,
    component: str | None,
    project: str | None,
    refresh: bool,
) -> None:
    """Force reconciliation of every release on an existing cluster."""
    _converge(
        application,
        installation,
        kubeconfig,
        component=component,
        project=project,
        refresh=refresh,
    )


@click.command("start")
@click.argument("installation", required=False)
@click.option("--kubeconfig", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--project", help="Bitwarden project name or ID when initialization is needed.")
@click.option("--refresh", is_flag=True, help="Refresh the cached Bitwarden context.")
@click.pass_obj
def start(
    application: Application,
    installation: str | None,
    kubeconfig: Path | None,
    project: str | None,
    refresh: bool,
) -> None:
    """Resume the selected product."""
    _converge(
        application,
        installation,
        kubeconfig,
        project=project,
        refresh=refresh,
    )


@click.command("update")
@click.argument("installation", required=False)
@click.option("--kubeconfig", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--component")
@click.option("--project", help="Bitwarden project name or ID when initialization is needed.")
@click.option("--refresh", is_flag=True, help="Refresh the cached Bitwarden context.")
@click.pass_obj
def update(
    application: Application,
    installation: str | None,
    kubeconfig: Path | None,
    component: str | None,
    project: str | None,
    refresh: bool,
) -> None:
    """Apply only releases whose desired configuration changed."""
    _converge(
        application,
        installation,
        kubeconfig,
        component=component,
        project=project,
        refresh=refresh,
        apply=True,
    )


@click.command("stop")
@click.argument("installation", required=False)
@click.option("--kubeconfig", type=click.Path(path_type=Path, dir_okay=False))
@click.pass_obj
def stop(
    application: Application,
    installation: str | None,
    kubeconfig: Path | None,
) -> None:
    """Stop product workloads while preserving data services."""
    repository, selected, resolved_kubeconfig = _operation(application, installation, kubeconfig)
    application.console.print(f"Stopping product installation [bold]{selected.name}[/bold]")
    Kubernetes(
        repository,
        selected,
        selected.path,
        resolved_kubeconfig,
        application.runner,
    ).stop()


@click.command("destroy")
@click.argument("installation", required=False)
@click.option("--kubeconfig", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--yes", is_flag=True, help="Confirm irreversible product and data removal.")
@click.pass_obj
def destroy(
    application: Application,
    installation: str | None,
    kubeconfig: Path | None,
    yes: bool,
) -> None:
    """Destroy the product and its data while preserving the cluster."""
    if not yes:
        raise AnubisError("destroy requires --yes")
    repository, selected, resolved_kubeconfig = _operation(application, installation, kubeconfig)
    application.console.print(
        f"Destroying product installation [bold]{selected.name}[/bold] and its data"
    )
    Kubernetes(
        repository,
        selected,
        selected.path,
        resolved_kubeconfig,
        application.runner,
    ).destroy()


@click.command("install")
@click.argument("installation", required=False)
@click.option("--project", help="Bitwarden project name or ID.")
@click.option("--refresh", is_flag=True, help="Refresh the cached Bitwarden context.")
@click.option("--inventory", type=click.Path(path_type=Path, dir_okay=False))
@click.option(
    "--ask-become-pass/--no-ask-become-pass",
    default=None,
    help="Override whether Ansible prompts for the sudo password.",
)
@click.option("--base-image", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--ssh-public-key", type=click.Path(path_type=Path, dir_okay=False))
@click.pass_obj
def install(
    application: Application,
    installation: str | None,
    project: str | None,
    refresh: bool,
    inventory: Path | None,
    ask_become_pass: bool | None,
    base_image: Path | None,
    ssh_public_key: Path | None,
) -> None:
    """Prepare the cluster and deploy the product."""
    repository = application.repository()
    selected = repository.select_installation(installation)
    assert selected is not None
    with resolved_manifest(
        repository,
        selected,
        application.runner,
        configuration=application.configuration(),
        project_selector=project,
        refresh=refresh,
    ) as manifest:
        prepare_cluster(
            application,
            selected,
            inventory=inventory,
            ask_become_pass=ask_become_pass,
            base_image=base_image,
            ssh_public_key=ssh_public_key,
        )
        kubernetes = Kubernetes(
            repository,
            selected,
            manifest,
            kubeconfig_path(repository, selected),
            application.runner,
        )
        kubernetes.deploy()

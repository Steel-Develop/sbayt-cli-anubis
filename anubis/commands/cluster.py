"""Kind, RKE2 and managed laboratory commands."""

from __future__ import annotations

from pathlib import Path

import click

from anubis.application import Application
from anubis.cluster import (
    TerraformLab,
    default_base_image,
    ensure_base_image,
    is_managed_lab,
    kind_destroy,
    kind_prepare,
    rke2,
)
from anubis.errors import AnubisError
from anubis.process import Runner
from anubis.repository import Installation, Repository


def _lab(
    repository: Repository,
    installation: Installation,
    runner: Runner,
    base_image: Path | None,
    ssh_public_key: Path | None,
) -> TerraformLab:
    image = (base_image or default_base_image(repository)).expanduser().resolve()
    key = (ssh_public_key or (Path.home() / ".ssh/id_ed25519.pub")).expanduser().resolve()
    return TerraformLab(repository, installation, runner, image, key)


def prepare_cluster(
    application: Application,
    installation: Installation,
    *,
    inventory: Path | None = None,
    ask_become_pass: bool | None = None,
    base_image: Path | None = None,
    ssh_public_key: Path | None = None,
) -> None:
    repository = application.repository()
    if installation.cluster_profile == "kind":
        kind_prepare(repository, installation, application.runner)
        return
    if is_managed_lab(installation):
        lab = _lab(repository, installation, application.runner, base_image, ssh_public_key)
        ensure_base_image(repository, application.runner, lab.base_image)
        lab.apply()
        inventory = lab.inventory
    rke2(
        repository,
        installation,
        application.runner,
        inventory=inventory,
        ask_become_pass=(
            installation.ask_become_pass if ask_become_pass is None else ask_become_pass
        ),
    )


@click.group("cluster")
def cluster_group() -> None:
    """Advanced cluster lifecycle operations."""


@cluster_group.command("plan")
@click.argument("installation", required=False)
@click.option("--base-image", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--ssh-public-key", type=click.Path(path_type=Path, dir_okay=False))
@click.pass_obj
def cluster_plan(
    application: Application,
    installation: str | None,
    base_image: Path | None,
    ssh_public_key: Path | None,
) -> None:
    """Plan a managed Terraform/libvirt laboratory."""
    repository = application.repository()
    selected = repository.select_installation(installation)
    assert selected is not None
    if not is_managed_lab(selected):
        raise AnubisError("cluster plan is available only for managed Terraform labs")
    lab = _lab(repository, selected, application.runner, base_image, ssh_public_key)
    ensure_base_image(repository, application.runner, lab.base_image)
    lab.plan()


@cluster_group.command("prepare")
@click.argument("installation", required=False)
@click.option("--inventory", type=click.Path(path_type=Path, dir_okay=False))
@click.option(
    "--ask-become-pass/--no-ask-become-pass",
    default=None,
    help="Override whether Ansible prompts for the sudo password.",
)
@click.option("--base-image", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--ssh-public-key", type=click.Path(path_type=Path, dir_okay=False))
@click.pass_obj
def cluster_prepare(
    application: Application,
    installation: str | None,
    inventory: Path | None,
    ask_become_pass: bool | None,
    base_image: Path | None,
    ssh_public_key: Path | None,
) -> None:
    """Create or reconcile the selected Kind or RKE2 cluster."""
    selected = application.repository().select_installation(installation)
    assert selected is not None
    prepare_cluster(
        application,
        selected,
        inventory=inventory,
        ask_become_pass=ask_become_pass,
        base_image=base_image,
        ssh_public_key=ssh_public_key,
    )


@cluster_group.command("destroy")
@click.argument("installation", required=False)
@click.option("--yes", is_flag=True)
@click.option("--base-image", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--ssh-public-key", type=click.Path(path_type=Path, dir_okay=False))
@click.pass_obj
def cluster_destroy(
    application: Application,
    installation: str | None,
    yes: bool,
    base_image: Path | None,
    ssh_public_key: Path | None,
) -> None:
    """Destroy a managed Kind or Terraform/libvirt cluster."""
    if not yes:
        raise AnubisError("cluster destroy requires --yes")
    repository = application.repository()
    selected = repository.select_installation(installation)
    assert selected is not None
    application.console.print(f"Destroying cluster for [bold]{selected.name}[/bold]")
    if selected.cluster_profile == "kind":
        kind_destroy(repository, selected, application.runner)
        return
    if not is_managed_lab(selected):
        raise AnubisError("refusing to destroy externally managed infrastructure")
    _lab(repository, selected, application.runner, base_image, ssh_public_key).destroy()

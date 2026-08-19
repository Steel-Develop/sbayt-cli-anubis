"""Public command-line interface."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import click
from click.shell_completion import get_completion_class
from rich.console import Console

from anubis.application import Application
from anubis.commands.check import check_group
from anubis.commands.cluster import cluster_group
from anubis.commands.product import (
    deploy,
    destroy,
    install,
    start,
    stop,
    update,
)
from anubis.commands.tooling import aws_group, bitwarden_group, config_group
from anubis.process import Runner


def _version() -> str:
    try:
        return importlib.metadata.version("anubis-cli")
    except importlib.metadata.PackageNotFoundError:
        return "0+unknown"


def _print_completion_script(
    context: click.Context,
    _parameter: click.Parameter,
    shell: str | None,
) -> None:
    if shell is None or context.resilient_parsing:
        return
    completion_class = get_completion_class(shell)
    if completion_class is None:  # pragma: no cover - guarded by Click's choice
        raise click.BadParameter(f"unsupported shell: {shell}")
    program = "anubis"
    completion_variable = f"_{program.replace('-', '_').upper()}_COMPLETE"
    completion = completion_class(context.command, {}, program, completion_variable)
    click.echo(completion.source())
    context.exit()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--repository",
    "repository_path",
    type=click.Path(path_type=Path, file_okay=False),
    help="IaC repository root. Auto-detected by default.",
)
@click.option("--verbose", is_flag=True, help="Print native commands before running them.")
@click.option(
    "--print-completion-script",
    type=click.Choice(["bash", "zsh", "fish"]),
    callback=_print_completion_script,
    expose_value=False,
    is_eager=True,
    help="Print a shell completion script and exit.",
)
@click.version_option(version=_version(), prog_name="anubis")
@click.pass_context
def cli(context: click.Context, repository_path: Path | None, verbose: bool) -> None:
    """Operate local tooling and Kubernetes infrastructure."""
    console = Console()
    context.obj = Application(repository_path, Runner(console, verbose=verbose), console)


for command in (
    install,
    deploy,
    update,
    stop,
    start,
    destroy,
    cluster_group,
    check_group,
    config_group,
    bitwarden_group,
    aws_group,
):
    cli.add_command(command)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

from invoke import Collection, task

from anubis.utils import _install_bws_cli, _uninstall_bws_cli


@task
def install_bws_cli(ctx):
    """
    Installs the Bitwarden CLI (bws) into the user's local bin directory.

    This task downloads the Bitwarden CLI binary, unzips it into ~/.local/bin,
    and ensures the directory is added to the PATH environment variable.
    Skips installation if the CLI is already installed.
    """
    _install_bws_cli()


@task
def remove_bws_cli(ctx):
    """
    Removes the Bitwarden CLI (bws) from the local environment.

    This task deletes the bws binary from ~/.local/bin, if it exists.
    """
    _uninstall_bws_cli()


bws_ns = Collection("bws")
bws_ns.add_task(install_bws_cli, name="install-cli")
bws_ns.add_task(remove_bws_cli, name="remove-cli")

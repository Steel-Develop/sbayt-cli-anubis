import logging

from invoke import Collection, task

from anubis.utils import (
    DEFAULT_ENV,
    _check_aws,
    _check_bws,
    _check_curl,
    _check_docker_environment,
    _check_local_bin_exists,
    _check_local_bin_in_path,
    _check_pip,
    _check_security_configuration,
    _check_unzip,
    _check_uv,
)


@task
def check_security(ctx, env=DEFAULT_ENV):
    """
    Task to run a complete security configuration check for the specified environment.

    This includes:
    - Validating the Bitwarden CLI (`bws`) installation
    - Verifying token and secrets access from Bitwarden
    - Checking AWS CLI and Docker ECR authentication

    Args:
        ctx: Invoke context (automatically passed).
        env (str): Environment name (default: 'dev').

    Usage:
        invoke check-security
        invoke check-security --env=prod
    """
    _check_security_configuration()


@task
def check_environment(ctx):
    """
    Validates that the local environment is correctly set up.

    This command verifies:
    - That ~/.local/bin exists and is in the $PATH environment variable.
    - That required CLI tools (aws, bws, pip, uv) are installed.
    - That no global conflicts are detected.

    Usage:
        invoke check.environment

    Example:
        invoke check.environment
    """
    logging.info("🧪 Validating local environment configuration...")

    _check_local_bin_exists()
    _check_local_bin_in_path()
    _check_docker_environment()
    _check_unzip()
    _check_curl()
    _check_aws()
    _check_bws()
    _check_pip()
    _check_uv()


check_ns = Collection("check")
check_ns.add_task(check_security, name="security")
check_ns.add_task(check_environment, name="environment")

import logging
import os
from pathlib import Path

from invoke import Collection, task

from anubis.utils import (
    DEFAULT_ENV,
    DOCKER_COMPOSE_CMD,
    DOCKER_NETWORK,
    _confirm_action,
    _get_env_file,
    _get_profiles_args,
    _launch_services,
)


@task
def create_network(ctx):
    """
    Creates the Docker network if it does not exist.

    Network name is defined by the global constant DOCKER_NETWORK.

    Usage:
        invoke create-network
    """
    try:
        result = ctx.run(
            f"docker network ls | grep {DOCKER_NETWORK}", warn=True, hide=True
        )
        if result.ok:
            logging.info(f"The network '{DOCKER_NETWORK}' already exists.")
        else:
            logging.info(f"Creating Docker network '{DOCKER_NETWORK}'...")
            ctx.run(f"docker network create {DOCKER_NETWORK}", pty=True)
    except Exception as e:
        logging.error(f"Error creating network: {str(e)}")


@task
def remove_network(ctx, yes=False):
    """
    Removes the Docker network if it exists.

    Args:
        ctx: Invoke context.
        yes (bool): If True, skips the confirmation prompt.

    Usage:
        invoke remove-network
        invoke remove-network --yes
    """
    if not _confirm_action(
        "Are you sure you want to remove the Docker network?", yes=yes
    ):
        logging.info("Remove network operation aborted by user.")
        return
    try:
        result = ctx.run(
            f"docker network ls | grep {DOCKER_NETWORK}", warn=True, hide=True
        )
        if result.ok:
            logging.info(f"Removing Docker network '{DOCKER_NETWORK}'...")
            ctx.run(f"docker network rm {DOCKER_NETWORK}", pty=True)
        else:
            logging.info(f"The network '{DOCKER_NETWORK}' does not exist.")
    except Exception as e:
        logging.error(f"Error removing network: {str(e)}")


@task
def clean_environment(ctx, yes=False, env=DEFAULT_ENV):
    """
    Cleans the Docker environment by performing several optional actions:
    - docker compose down
    - remove Docker network
    - prune system, volumes, and networks

    Each step prompts for confirmation unless --yes is used.

    Args:
        ctx: Invoke context.
        yes (bool): Auto-confirm all actions if True.
        env (str): Environment name (default: 'dev').

    Usage:
        invoke clean-environment
        invoke clean-environment --yes
    """
    if _confirm_action(
        "Do you want to stop and remove all services (docker compose down)?", yes=yes
    ):
        down(ctx, yes=yes, env=env)
    if _confirm_action("Do you want to remove the Docker network?", yes=yes):
        remove_network(ctx, yes=yes)
    if _confirm_action(
        "Do you want to remove unused Docker data (docker system prune)?", yes=yes
    ):
        ctx.run("docker system prune -f", pty=True)
    if _confirm_action(
        "Do you want to remove unused Docker volumes (docker volume prune)?", yes=yes
    ):
        ctx.run("docker volume prune -f", pty=True)
    if _confirm_action(
        "Do you want to remove unused Docker networks (docker network prune)?", yes=yes
    ):
        ctx.run("docker network prune -f", pty=True)


@task(create_network)
def up(
    ctx,
    profiles=None,
    env=DEFAULT_ENV,
    load_secrets_from_bws=None,
    skip_ecr_login=False,
    deployment_file=None,
):
    """
    Starts Docker Compose services in interactive (foreground) mode.

    Loads secrets from Bitwarden, authenticates with AWS ECR if needed, and runs
    `docker compose up` with the specified profiles and environment.

    Args:
        ctx: Invoke context.
        profiles (str, optional): Comma-separated list of profiles to activate.
        env (str): Target environment name (default: "dev").
        load_secrets_from_bws (bool, optional): Whether to load Bitwarden secrets.
        skip_ecr_login (bool): If True, skip ECR login.
        deployment_file (str, optional): Path to deployment config file.

    Usage:
        invoke docker.up
        invoke docker.up --profiles=infra,api
        invoke docker.up --env=prod
    """
    _launch_services(
        ctx,
        profiles,
        detach=False,
        env=env,
        load_secrets_from_bws=load_secrets_from_bws,
        skip_ecr_login=skip_ecr_login,
        deployment_file=deployment_file,
    )


@task(create_network)
def up_daemon(
    ctx,
    profiles=None,
    env=DEFAULT_ENV,
    load_secrets_from_bws=None,
    skip_ecr_login=False,
    deployment_file=None,
):
    """
    Starts services using Docker Compose in detached (background) mode.

    Args:
        ctx: Invoke context.
        profiles (str, optional): Comma-separated profiles to activate.
        env (str): Target environment name.
        deployment_file (str, optional): Path to a deployment config file.

    Example:
        invoke up-daemon
        invoke up-daemon --profiles=infra
    """
    _launch_services(
        ctx,
        profiles,
        detach=True,
        env=env,
        load_secrets_from_bws=load_secrets_from_bws,
        skip_ecr_login=skip_ecr_login,
        deployment_file=deployment_file,
    )


@task
def down(ctx, profiles=None, yes=False, env=DEFAULT_ENV, deployment_file=None):
    """
    Stops and removes Docker Compose services.

    Optionally also removes volumes and orphan containers based on user confirmation.

    Args:
        ctx: Invoke context.
        profiles (str, optional): Comma-separated profiles to target.
        yes (bool): If True, skips confirmation prompts.
        env (str): Target environment name.
        deployment_file (str, optional): Path to deployment config file.

    Example:
        invoke down
        invoke down --profiles=api,infra --yes
    """
    if not _confirm_action("Are you sure you want to stop all containers?", yes=yes):
        logging.info("Operation aborted by user.")
        return
    remove_volumes = _confirm_action("Do you also want to remove volumes?", yes=yes)
    remove_orphans = _confirm_action(
        "Do you want to remove orphan containers?", yes=yes
    )
    options = ""
    if remove_volumes:
        options += " --volumes"
    if remove_orphans:
        options += " --remove-orphans"
    env_file = _get_env_file(env)
    ctx.run(
        f"{DOCKER_COMPOSE_CMD} --env-file {env_file} {_get_profiles_args(profiles, deployment_file)} down{options}",
        env={**os.environ, "ENV": env},
        pty=True,
    )


@task
def restart(
    ctx,
    profiles=None,
    yes=False,
    env=DEFAULT_ENV,
    load_secrets_from_bws=None,
    skip_ecr_login=False,
    deployment_file=None,
):
    """
    Restarts services by stopping them (`down`) and then starting them again (`up`).

    Args:
        ctx: Invoke context.
        profiles (str, optional): Comma-separated profiles.
        yes (bool): If True, skip confirmation prompts.
        env (str): Environment name.
        load_secrets_from_bws (bool, optional): Whether to load Bitwarden secrets.
        skip_ecr_login (bool, optional): If True, skip ECR login.
        deployment_file (str, optional): Path to deployment config.

    Example:
        invoke restart
        invoke restart --profiles=infra --env=prod --yes
    """
    logging.info("🔄 Restarting services...")

    down(
        ctx,
        profiles=profiles,
        yes=yes,
        env=env,
        load_secrets_from_bws=load_secrets_from_bws,
        skip_ecr_login=skip_ecr_login,
        deployment_file=deployment_file,
    )
    up(
        ctx,
        profiles=profiles,
        env=env,
        load_secrets_from_bws=load_secrets_from_bws,
        skip_ecr_login=skip_ecr_login,
        deployment_file=deployment_file,
    )


@task
def ps(ctx, profiles=None, env=DEFAULT_ENV, deployment_file=None):
    """
    Displays the status of running containers defined in Docker Compose.

    Args:
        ctx: Invoke context.
        profiles (str, optional): Comma-separated profiles to filter.
        env (str): Target environment name.
        deployment_file (str, optional): Path to deployment config file.

    Example:
        invoke ps
        invoke ps --profiles=infra
    """
    env_file = _get_env_file(env)
    ctx.run(
        f"{DOCKER_COMPOSE_CMD} --env-file {env_file} {_get_profiles_args(profiles, deployment_file)} ps",
        pty=True,
    )


@task
def logs(ctx, service=None, follow=True, tail=250, env=DEFAULT_ENV):
    """
    Displays logs from Docker Compose services.

    Args:
        ctx: Invoke context.
        service (str, optional): Specific service name to filter logs.
        follow (bool): Whether to follow the logs live (default: True).
        tail (int): Number of lines to show from the end of the log (default: 250).
        env (str): Target environment name.

    Example:
        invoke logs
        invoke logs --service=api
        invoke logs --follow=False --tail=100
    """
    flags = f"--tail={tail}"
    if follow:
        flags += " -f"
    cmd = f"{DOCKER_COMPOSE_CMD} --env-file {_get_env_file(env)} logs {flags}"
    if service:
        cmd += f" {service}"

    # Build ephemeral environment by loading .env file plus OS environment
    env_vars = os.environ.copy()
    env_vars["ENV"] = env
    env_file_path = _get_env_file(env)
    if Path(env_file_path).exists():
        with open(env_file_path) as f:
            for line in f:
                if line.strip() and not line.strip().startswith("#") and "=" in line:
                    key, val = line.strip().split("=", 1)
                    env_vars[key] = val

    ctx.run(cmd, env=env_vars, pty=True)


@task
def build(ctx, profiles=None, env=DEFAULT_ENV, deployment_file=None):
    """
    Builds Docker images for the given Compose profiles.

    Args:
        ctx: Invoke context.
        profiles (str, optional): Comma-separated profiles to build.
        env (str): Target environment name.
        deployment_file (str, optional): Path to deployment config file.

    Example:
        invoke build
        invoke build --profiles=api
    """
    env_file = _get_env_file(env)
    ctx.run(
        f"{DOCKER_COMPOSE_CMD} --env-file {env_file} {_get_profiles_args(profiles, deployment_file)} build",
        pty=True,
    )


docker_ns = Collection("docker")
docker_ns.add_task(create_network)
docker_ns.add_task(remove_network)
docker_ns.add_task(clean_environment)
docker_ns.add_task(up)
docker_ns.add_task(up_daemon)
docker_ns.add_task(down)
docker_ns.add_task(restart)
docker_ns.add_task(ps)
docker_ns.add_task(logs)
docker_ns.add_task(build)

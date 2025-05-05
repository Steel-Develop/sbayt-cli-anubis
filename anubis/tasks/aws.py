import logging
import os
from pathlib import Path

from invoke import Collection, Exit, task
from rich.prompt import Confirm, Prompt

from anubis.utils import (
    DEFAULT_DEPLOYMENT_FILE,
    LOAD_SECRETS_FROM_BWS_NAME,
    UV_CONFIG_FILE,
    _ensure_tool_installed,
    _find_tool,
    _get_aws_account_id,
    _get_aws_region,
    _get_cached_config,
    _get_codeartifact_token,
    _install_aws_cli,
    _load_secrets_from_bws,
    _uninstall_aws_cli,
)


@task
def install_aws_cli(ctx):
    """
    Instala el AWS CLI en el directorio local del usuario.

    Este comando realiza una instalación local (sin permisos de root) del AWS CLI
    descargando el instalador oficial, extrayéndolo y configurándolo en ~/.local/aws-cli.

    Uso:
        invoke aws.install-cli

    Ejemplo:
        invoke aws.install-cli
    """
    _install_aws_cli()


@task
def remove_aws_cli(ctx):
    """
    Removes the AWS CLI installed in the local environment.

    This task deletes the local AWS CLI installation from ~/.local/aws-cli
    and removes the aws binary from ~/.local/bin if present.
    """
    _uninstall_aws_cli()


@task
def configure_pip(ctx, load_secrets_from_bws=None, deployment_file=None):
    """
    Configures pip to use a private CodeArtifact repository.

    Retrieves a CodeArtifact token if available and runs `pip config set global.index-url`.
    Mirrors the bash function `configure_pip()`.
    """
    # Check pip installed
    if not _find_tool("pip"):
        logging.error("pip is not installed. Please install it first.")
        raise Exit(code=1)

    # Check AWS CLI installed
    if not _ensure_tool_installed("aws", _install_aws_cli):
        raise Exit(code=1)

    config = _get_cached_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    load_secrets = (
        load_secrets_from_bws
        if load_secrets_from_bws is not None
        else config.get(LOAD_SECRETS_FROM_BWS_NAME, True)
    )

    bws_secrets = {}
    if load_secrets:
        # Load secrets from Bitwarden
        bws_secrets = _load_secrets_from_bws(deployment_file)
        if not bws_secrets:
            logging.warning("⚠️ No secrets found in Bitwarden.")

    # Get all required configuration
    config = _get_cached_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    aws_account_id = _get_aws_account_id(deployment_file)
    aws_region = _get_aws_region(deployment_file)
    domain = config.get("codeartifact_domain")
    repo = config.get("codeartifact_repo")
    codeartifact_token = _get_codeartifact_token(bws_secrets, deployment_file)

    # Validate CodeArtifact configuration
    if not domain:
        logging.error(
            "❌ CodeArtifact domain not configured. Add 'codeartifact_domain' to your deployment.yml"
        )
        raise Exit(code=1)
    if not repo:
        logging.error(
            "❌ CodeArtifact repository not configured. Add 'codeartifact_repo' to your deployment.yml"
        )
        raise Exit(code=1)

    # Run codeartifact login
    repo_url = (
        f"https://aws:{codeartifact_token}@{domain}-{aws_account_id}.d.codeartifact."
        f"{aws_region}.amazonaws.com/pypi/{repo}/simple/"
    )
    ctx.run(f"pip config set global.index-url {repo_url}", pty=True)
    logging.info("✅ pip is now configured to use the private CodeArtifact repository.")


@task
def configure_uv(ctx, load_secrets_from_bws=None, deployment_file=None):
    """
    Configures uv to use the private CodeArtifact repository.

    This task retrieves a CodeArtifact token and writes a configuration
    file for uv at ~/.config/uv/uv.toml.
    """
    if not _find_tool("uv"):
        logging.error("uv is not installed. Please install it first.")
        raise Exit(code=1)

    # Check AWS CLI installed
    if not _ensure_tool_installed("aws", _install_aws_cli):
        raise Exit(code=1)

    config = _get_cached_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    load_secrets = (
        load_secrets_from_bws
        if load_secrets_from_bws is not None
        else config.get(LOAD_SECRETS_FROM_BWS_NAME, True)
    )

    bws_secrets = {}
    if load_secrets:
        bws_secrets = _load_secrets_from_bws(deployment_file)
        if not bws_secrets:
            logging.warning("⚠️ No secrets found in Bitwarden.")

    # Get all required configuration
    config = _get_cached_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    aws_account_id = _get_aws_account_id(deployment_file)
    aws_region = _get_aws_region(deployment_file)
    domain = config.get("codeartifact_domain")
    repo = config.get("codeartifact_repo")
    codeartifact_token = _get_codeartifact_token(bws_secrets, deployment_file)

    # Validate CodeArtifact configuration
    if not domain:
        logging.error(
            "❌ CodeArtifact domain not configured. Add 'codeartifact_domain' to your deployment.yml"
        )
        raise Exit(code=1)
    if not repo:
        logging.error(
            "❌ CodeArtifact repository not configured. Add 'codeartifact_repo' to your deployment.yml"
        )
        raise Exit(code=1)

    # Create config folder if missing
    UV_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Compose repository URL
    repo_url = (
        f"https://aws:{codeartifact_token}@{domain}-{aws_account_id}.d.codeartifact."
        f"{aws_region}.amazonaws.com/pypi/{repo}/simple/"
    )

    # Write config file
    config_content = f"""[[index]]
        url = \"{repo_url}\"
        default = true
        """
    UV_CONFIG_FILE.write_text(config_content)

    logging.info("✅ uv is now configured to use the private CodeArtifact repository.")


@task
def reset_pypi(ctx):
    """
    Resets pip and uv to use the public PyPI, if available.

    Unsets pip's index-url and deletes uv.toml, if those are present.
    """
    # Reset pip if available
    if _find_tool("pip"):
        logging.info("🔁 Resetting pip to use public PyPI...")
        ctx.run("pip config unset global.index-url", warn=True)
    else:
        logging.warning("⚠️ pip not found. Skipping pip reset.")

    # Reset uv if available
    if _find_tool("uv"):
        uv_config_file = Path.home() / ".config" / "uv" / "uv.toml"
        if uv_config_file.exists():
            try:
                uv_config_file.unlink()
                logging.info("🔁 Reset uv by deleting uv.toml config file.")
            except Exception as e:
                logging.error(f"❌ Failed to delete uv config file: {e}")
        else:
            logging.info("✅ uv config file does not exist. Nothing to reset.")
    else:
        logging.warning("⚠️ uv not found. Skipping uv reset.")


@task
def create_ca_env_file(ctx, deployment_file=None):
    """
    Creates a .env.codeartifact file containing the CODEARTIFACT_AUTH_TOKEN retrieved from AWS.

    Args:
        ctx: Invoke context.
        deployment_file (str, optional): Path to deployment config file.

    Usage:
        invoke create-ca-env-file
    """

    output_dir = Prompt.ask(
        "Enter the path where to create .env.codeartifact (leave blank for current directory)",
        default=os.getcwd(),
    )

    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    bws_secrets = _load_secrets_from_bws(deployment_file)
    token = _get_codeartifact_token(bws_secrets, deployment_file)

    if not token:
        logging.error("❌ Failed to retrieve CodeArtifact token.")
        raise Exit(code=1)

    env_file_path = output_path / ".env.codeartifact"
    env_file_path.write_text(f"CODEARTIFACT_AUTH_TOKEN={token}\n")

    print("\n---")
    print("To use the .env.codeartifact file with docker-compose, run:")
    print(f"docker-compose --env-file {env_file_path} up")
    print("---\n")
    logging.info(f"✅ .env.codeartifact created at {env_file_path}.")


@task
def export_ca_token_env_var(ctx, deployment_file=None):
    """
    Exports CODEARTIFACT_AUTH_TOKEN to the current shell environment.

    ⚠️ IMPORTANT: This task MUST be run using `source` or `.` for the environment variable to persist.

    Args:
        ctx: Invoke context.
        deployment_file (str, optional): Path to deployment config file.

    Usage:
        source invoke export-ca-token-env-var
    """

    logging.info("🔐 Exporting CODEARTIFACT_AUTH_TOKEN...")

    bws_secrets = _load_secrets_from_bws(deployment_file)
    token = _get_codeartifact_token(bws_secrets, deployment_file)

    if not token:
        logging.error("❌ Failed to retrieve CodeArtifact token.")
        raise Exit(code=1)

    print("\n---")
    print(f'export CODEARTIFACT_AUTH_TOKEN="{token}"')
    print("# ⚠️ Run this command using 'source' or '.' to persist this variable.")
    print("---\n")

    if Confirm.ask("Would you like to add this export to your shell profile?"):
        shell = os.environ.get("SHELL", "")
        default_profile = "~/.bashrc"
        if "zsh" in shell:
            default_profile = "~/.zshrc"
        profile_path = Path(
            Prompt.ask("Enter path to your shell profile", default=default_profile)
        ).expanduser()

        if profile_path.exists():
            content = profile_path.read_text()
            lines = [
                line
                for line in content.splitlines()
                if not line.startswith("export CODEARTIFACT_AUTH_TOKEN=")
            ]
            lines.append(f'export CODEARTIFACT_AUTH_TOKEN="{token}"')
            profile_path.write_text("\n".join(lines) + "\n")
            logging.info(f"✅ Token export added to {profile_path}")
        else:
            logging.warning(f"⚠️ Shell profile not found: {profile_path}")


aws_ns = Collection("aws")
aws_ns.add_task(install_aws_cli, name="install-cli")
aws_ns.add_task(remove_aws_cli, name="remove-cli")
aws_ns.add_task(configure_pip, name="configure-pip")
aws_ns.add_task(configure_uv, name="configure-uv")
aws_ns.add_task(reset_pypi, name="reset-pypi")
aws_ns.add_task(create_ca_env_file, name="create-ca-env-file")
aws_ns.add_task(export_ca_token_env_var, name="export-ca-token-env-var")

"""
Seshat CLI - Secure Environment Setup & Host Automation Toolkit
---------------------------------------------------------------

This script defines and organizes a set of automated tasks for configuring and
managing development/production environments. It uses `invoke` to structure tasks
and `rich` to enhance the terminal experience.

Main features:
- Local installation and management of essential CLI tools (AWS CLI, Bitwarden CLI).
- Configuration of private repositories (CodeArtifact) for pip and uv.
- Docker services automation (create network, start, stop, clean, build).
- Verification of security and local environment configurations (Bitwarden, AWS ECR, etc.).

Requirements:
- Python 3.8 or higher.
- Dependencies: invoke, rich, yaml (installable via pip).
- A deployment file (default: deployment.yml) to define profiles and credentials.

Basic usage:
    1. View available tasks:
        invoke help
    2. Check your local environment:
        invoke check.environment
    3. Start Docker services with specific profiles:
        invoke docker.up --profiles=infra,api --env=prod
    4. Configure pip for CodeArtifact:
        invoke aws.configure-pip

For more details or additional examples, refer to the documentation of each task
using the `invoke --list` command or review the individual docstrings.
"""

import importlib.metadata
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional, Tuple

import yaml
from invoke import Collection, task
from invoke.exceptions import Exit
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# =============================================================================
# Global configuration and constants
# =============================================================================

# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

console = Console()

# Global variables
VERSION = importlib.metadata.version("seshat-cli")
DEFAULT_ENV = "dev"
DEFAULT_DEPLOYMENT_FILE = "deployment.yml"
LOCAL_BIN_PATH = Path.home() / ".local/bin"
LOAD_SECRETS_FROM_BWS_NAME = "load_secrets_from_bws"
SKIP_ECR_LOGIN_NAME = "skip_ecr_login"

# Docker & Docker Compose
DEFAULT_COMPOSE_FILE = "docker-compose.yml"
DOCKER_COMPOSE_CMD = f"docker compose -f {DEFAULT_COMPOSE_FILE}"
DOCKER_NETWORK = "microservices"
DEFAULT_ENV_FOLDER_TEMPLATE = "conf/{env}/.env"

# BWS
BWS_VERSION = "0.2.1"
BWS_RELEASE_FILENAME = f"bws-x86_64-unknown-linux-gnu-{BWS_VERSION}.zip"
BWS_DOWNLOAD_URL = f"https://github.com/bitwarden/sdk/releases/download/bws-v{BWS_VERSION}/{BWS_RELEASE_FILENAME}"
BWS_ZIP_PATH = LOCAL_BIN_PATH / "bws.zip"

# AWS
# Credential environment variables
AWS_KEY_ID_VARIABLE_NAME = "AWS_ACCESS_KEY_ID"
AWS_SECRET_VARIABLE_NAME = "AWS_SECRET_ACCESS_KEY"
AWS_TOKEN_VARIABLE_NAME = "AWS_SESSION_TOKEN"

# AWS CLI installation
AWS_CLI_VERSION = "2.15.50"
AWS_CLI_ZIP_FILENAME = "awscli-exe-linux-x86_64.zip"
AWS_CLI_DOWNLOAD_URL = f"https://awscli.amazonaws.com/{AWS_CLI_ZIP_FILENAME}"
AWS_CLI_ZIP_PATH = LOCAL_BIN_PATH / "aws.zip"
AWS_CLI_UNZIP_DIR = LOCAL_BIN_PATH / "aws"
AWS_CLI_INSTALL_DIR = Path.home() / ".local/aws-cli"

# AWS - ecr
AWS_ECR_REGISTRY_TEMPLATE = "{account_id}.dkr.ecr.{region}.amazonaws.com"

# uv
UV_CONFIG_FILE = Path.home() / ".config" / "uv" / "uv.toml"

# Create the main collection
ns = Collection()

# =============================================================================
# Métodos auxiliares para Bitwarden
# =============================================================================


def _install_bws_cli():
    """
    Installs the Bitwarden CLI (bws) from GitHub releases if it's not already installed.

    Downloads the ZIP file, unzips it into ~/.local/bin, and updates the PATH environment
    variable for the current process. Cleans up any temporary files afterward.

    Raises:
        subprocess.CalledProcessError: If the download or unzip steps fail.
    """
    if _find_tool("bws"):
        logging.info("✅ Bitwarden CLI (bws) already installed. Skipping installation.")
        return

    logging.info("Installing Bitwarden CLI (bws) locally...")
    LOCAL_BIN_PATH.mkdir(parents=True, exist_ok=True)

    try:
        # Download the installer
        subprocess.run(["curl", "-Lo", str(BWS_ZIP_PATH), BWS_DOWNLOAD_URL], check=True)

        # Extract to ~/.local/bin
        subprocess.run(
            ["unzip", "-d", str(LOCAL_BIN_PATH), str(BWS_ZIP_PATH)], check=True
        )

        # Update PATH so bws is available in the current shell
        os.environ["PATH"] = f"{LOCAL_BIN_PATH}:{os.environ.get('PATH', '')}"
        logging.info("✅ Bitwarden CLI installed and added to PATH.")

    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Failed to install Bitwarden CLI: {e}")
        raise

    finally:
        # Clean up downloaded and extracted temporary files
        try:
            if BWS_ZIP_PATH.exists():
                BWS_ZIP_PATH.unlink()
        except Exception as cleanup_err:
            logging.warning(
                f"⚠️ Failed to clean up Bitwarden temporary files: {cleanup_err}"
            )


def _uninstall_bws_cli():
    """
    Uninstalls the Bitwarden CLI (bws) by removing the binary from ~/.local/bin.
    Does nothing if the file does not exist.
    """
    bws_binary_path = LOCAL_BIN_PATH / "bws"

    if bws_binary_path.exists():
        try:
            bws_binary_path.unlink()
            logging.info(
                "🗑️ Bitwarden CLI (bws) has been uninstalled from ~/.local/bin."
            )
        except Exception as e:
            logging.error(f"❌ Failed to uninstall bws: {e}")
    else:
        logging.info("ℹ️ Bitwarden CLI (bws) is not installed or already removed.")


def _get_bws_token(deployment_file=None) -> Optional[str]:
    """
    Retrieves the Bitwarden access token (BWS_ACCESS_TOKEN) for use with the CLI.

    Search order:
        1. Environment variable: BWS_ACCESS_TOKEN
        2. Deployment config YAML file: 'bws_access_token'

    Args:
        deployment_file (str, optional): Path to the deployment YAML file.

    Returns:
        Optional[str]: The token if found, or None otherwise.

    Example:
        >>> os.environ["BWS_ACCESS_TOKEN"] = "abc123"
        >>> _get_bws_token()
        'abc123'
    """
    # 1) Check environment variable
    token = os.environ.get("BWS_ACCESS_TOKEN")
    if token:
        return token

    # 2) Attempt to read from deployment.yml
    config = _load_deployment_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    token = config.get("bws_access_token")
    if token:
        return token

    return None


def _ensure_bws_token(deployment_file=None):
    """
    Ensures a Bitwarden access token is available for CLI usage.

    First attempts to retrieve it from environment or config.
    If not found, prompts the user to input it interactively.

    Args:
        deployment_file (str, optional): Path to the deployment YAML file.

    Returns:
        Optional[str]: A valid access token, or None if the user skips or cancels.

    Example:
        >>> _ensure_bws_token()
        🔐 Enter your BWS access token:
    """
    token: Optional[str] = _get_bws_token(deployment_file)

    if token is not None:
        return token

    try:
        token = input("🔐 Enter your BWS access token: ").strip()
        if not token:
            logging.warning("No token provided. Skipping Bitwarden secrets loading.")
            return None
        return token
    except (EOFError, KeyboardInterrupt):
        logging.warning("No token provided. Skipping Bitwarden secrets loading.")
        return None


def _load_secrets_from_bws(deployment_file=None) -> dict:
    """
    Loads secrets from the Bitwarden CLI (`bws`) using a valid access token.

    If the CLI is not available, attempts to install it. Secrets are loaded
    using the `bws list secrets` command and returned as a dictionary.

    Args:
        deployment_file (str, optional): Path to the deployment config file.

    Returns:
        dict: Dictionary of secrets in the form {key: value}. Returns an empty
              dictionary if the CLI or token is unavailable.

    Example:
        >>> _load_secrets_from_bws()
        {'DB_PASSWORD': '...', 'AWS_ACCESS_KEY_ID': '...'}
    """
    bws_token = _ensure_bws_token(deployment_file)
    if not bws_token:
        return {}

    if not _ensure_tool_installed("bws", _install_bws_cli):
        return {}

    try:
        result = subprocess.run(
            ["bws", "list", "secrets", "--access-token", bws_token],
            capture_output=True,
            text=True,
            env=_build_env(),
        )
        secrets_list = json.loads(result.stdout)
        secrets_dict = {}
        for secret in secrets_list:
            key = secret.get("key")
            value = secret.get("value")
            if key and value:
                secrets_dict[key] = value
        return secrets_dict
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to retrieve secrets from Bitwarden: {e.stderr}")
    except json.JSONDecodeError:
        logging.error("Failed to parse secrets JSON from Bitwarden output.")

    return {}


# =============================================================================
# Métodos auxiliares para AWS
# =============================================================================


def _install_aws_cli():
    """
    Installs the AWS CLI into ~/.local/bin and ~/.local/aws-cli if it's not already installed.

    This method performs a fully local installation (no sudo required), by downloading
    the official installer, extracting it to a temporary directory, and installing
    the CLI binaries in ~/.local/aws-cli. The aws binary is symlinked to ~/.local/bin/aws.

    Raises:
        subprocess.CalledProcessError: If the download or install steps fail.
    """
    if _find_tool("aws"):
        logging.info("✅ AWS CLI already installed. Skipping installation.")
        return
    logging.info("Installing AWS CLI locally...")

    # Paso 1) Crear directorio temporal
    TMP_DIR = Path.home() / "aws_temp"
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Descargar en TMP_DIR
        zip_path = TMP_DIR / "awscliv2.zip"
        subprocess.run(["curl", "-Lo", str(zip_path), AWS_CLI_DOWNLOAD_URL], check=True)

        # Descomprimir en TMP_DIR
        subprocess.run(["unzip", "-d", str(TMP_DIR), str(zip_path)], check=True)

        # Paso 2) Ejecutar el instalador
        install_script = TMP_DIR / "aws" / "install"
        subprocess.run(
            [
                str(install_script),
                "-i",
                str(AWS_CLI_INSTALL_DIR),
                "-b",
                str(LOCAL_BIN_PATH),
            ],
            check=True,
        )

        # Agregar ~/.local/bin al PATH
        os.environ["PATH"] = f"{LOCAL_BIN_PATH}:{os.environ.get('PATH', '')}"
        logging.info("✅ AWS CLI installed locally in ~/.local/aws-cli")

    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Failed to install AWS CLI: {e}")
        raise
    finally:
        # Paso 3) Limpiar
        try:
            if TMP_DIR.exists():
                shutil.rmtree(TMP_DIR)
        except Exception as cleanup_err:
            logging.warning(f"⚠️ Failed to clean up temporary files: {cleanup_err}")


def _uninstall_aws_cli():
    """
    Uninstalls the AWS CLI installed locally in ~/.local/aws-cli and removes aws symlink in ~/.local/bin.

    This operation is silent if the files do not exist.
    """
    aws_binary_path = LOCAL_BIN_PATH / "aws"
    aws_cli_dir = AWS_CLI_INSTALL_DIR

    # Remove symlink or binary
    if aws_binary_path.exists():
        try:
            aws_binary_path.unlink()
            logging.info("🗑️ Removed AWS CLI binary from ~/.local/bin.")
        except Exception as e:
            logging.error(f"❌ Failed to remove aws binary: {e}")
    else:
        logging.info("ℹ️ AWS binary not found in ~/.local/bin.")

    # Remove install dir
    if aws_cli_dir.exists():
        try:
            shutil.rmtree(aws_cli_dir)
            logging.info("🧹 Removed AWS CLI installation from ~/.local/aws-cli.")
        except Exception as e:
            logging.error(f"❌ Failed to remove AWS CLI directory: {e}")
    else:
        logging.info("ℹ️ AWS CLI installation folder already removed.")


def _get_aws_account_id(deployment_file=None) -> str:
    """
    Retrieves the AWS account ID from the deployment configuration file.

    Args:
        deployment_file (str, optional): Path to the deployment config file.

    Returns:
        str: The AWS account ID.

    Raises:
        Exit: If aws_account_id is not configured in deployment.yml
    """
    config = _load_deployment_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    account_id = config.get("aws_account_id")
    if not account_id:
        logging.error(
            "❌ AWS account ID not configured. Add 'aws_account_id' to your deployment.yml"
        )
        raise Exit(code=1)
    return account_id


def _get_aws_region(deployment_file=None) -> str:
    """
    Retrieves the AWS region from the deployment configuration file.

    Args:
        deployment_file (str, optional): Path to the deployment config file.

    Returns:
        str: The AWS region.

    Raises:
        Exit: If aws_region is not configured in deployment.yml
    """
    config = _load_deployment_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    region = config.get("aws_region")
    if not region:
        logging.error(
            "❌ AWS region not configured. Add 'aws_region' to your deployment.yml"
        )
        raise Exit(code=1)
    return region


def _aws_ecr_login(bws_secrets: dict, deployment_file=None) -> bool:
    """
    Authenticates Docker with AWS Elastic Container Registry (ECR).

    Uses the AWS CLI and credentials from the provided secrets to log in
    to the appropriate ECR registry.

    Args:
        bws_secrets (dict): Dictionary containing:
            - AWS_ACCESS_KEY_ID
            - AWS_SECRET_ACCESS_KEY
            - AWS_SESSION_TOKEN (optional)
        deployment_file (str, optional): Path to the deployment config file.

    Returns:
        bool: True if login was successful, False otherwise.

    Example:
        >>> _aws_ecr_login({'AWS_ACCESS_KEY_ID': '...', 'AWS_SECRET_ACCESS_KEY': '...'})
        True
    """
    if not _ensure_tool_installed("aws", _install_aws_cli):
        logging.error("Cannot log in to ECR.")
        return False

    # Retrieve AWS credentials from secrets dictionary
    aws_account_id = _get_aws_account_id(deployment_file)
    aws_region = _get_aws_region(deployment_file)
    registry = AWS_ECR_REGISTRY_TEMPLATE.format(
        account_id=aws_account_id, region=aws_region
    )

    aws_access_key = _get_config_from_sources(
        key=AWS_KEY_ID_VARIABLE_NAME, bws_secrets=bws_secrets
    )
    aws_secret_key = _get_config_from_sources(
        key=AWS_SECRET_VARIABLE_NAME, bws_secrets=bws_secrets
    )
    aws_session_token = _get_config_from_sources(
        key=AWS_TOKEN_VARIABLE_NAME, bws_secrets=bws_secrets
    )

    if not (aws_access_key and aws_secret_key and aws_region and aws_account_id):
        logging.warning("Missing AWS credentials or configuration. Skipping ECR login.")
        return False

    # Build ephemeral environment for subprocess
    ephemeral_env = _build_env(
        extra_vars={
            AWS_KEY_ID_VARIABLE_NAME: aws_access_key,
            AWS_SECRET_VARIABLE_NAME: aws_secret_key,
            "AWS_REGION": aws_region,
            **(
                {AWS_TOKEN_VARIABLE_NAME: aws_session_token}
                if aws_session_token
                else {}
            ),
        }
    )

    try:
        login_cmd = (
            f"aws ecr get-login-password --region {aws_region} | "
            f"docker login --username AWS --password-stdin {registry}"
        )
        subprocess.run(
            login_cmd,
            capture_output=True,
            shell=True,
            env=ephemeral_env,
        )
        return True
    except subprocess.CalledProcessError as e:
        logging.error("❌ Failed to authenticate Docker with AWS ECR")
        logging.debug(f"Command output: {e.output}")


def _get_codeartifact_token(
    bws_secrets: dict, deployment_file: str = None
) -> tuple[str, str]:
    """
    Retrieves a CodeArtifact authorization token using temporary AWS credentials.

    Args:
        bws_secrets (dict): Dict with AWS credentials.
        deployment_file (str): Optional deployment config file to get region/account.

    Returns:
        str: The authorization token if successful, None otherwise.
    """
    if not _ensure_tool_installed("aws", _install_aws_cli):
        logging.error("Cannot get CodeArtifact token.")
        return None

    aws_account_id = _get_aws_account_id(deployment_file)
    aws_region = _get_aws_region(deployment_file)
    aws_access_key = _get_config_from_sources(
        AWS_KEY_ID_VARIABLE_NAME, bws_secrets=bws_secrets
    )
    aws_secret_key = _get_config_from_sources(
        AWS_SECRET_VARIABLE_NAME, bws_secrets=bws_secrets
    )
    aws_session_token = _get_config_from_sources(
        AWS_TOKEN_VARIABLE_NAME, bws_secrets=bws_secrets
    )

    if not (aws_access_key and aws_secret_key and aws_account_id and aws_region):
        logging.warning(
            "Missing AWS credentials or configuration. Skipping CodeArtifact token retrieval."
        )
        return None

    ephemeral_env = {
        **os.environ,
        AWS_KEY_ID_VARIABLE_NAME: aws_access_key,
        AWS_SECRET_VARIABLE_NAME: aws_secret_key,
        "AWS_REGION": aws_region,
    }
    if aws_session_token:
        ephemeral_env[AWS_TOKEN_VARIABLE_NAME] = aws_session_token

    # Get required configuration from deployment.yml
    config = _load_deployment_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    domain = config.get("codeartifact_domain")
    if not domain:
        logging.error(
            "❌ CodeArtifact domain not configured. Add 'codeartifact_domain' to your deployment.yml"
        )
        raise Exit(code=1)

    try:
        result = subprocess.run(
            [
                "aws",
                "codeartifact",
                "get-authorization-token",
                "--domain",
                domain,
                "--domain-owner",
                aws_account_id,
                "--region",
                aws_region,
                "--output",
                "json",
            ],
            env=ephemeral_env,
            capture_output=True,
            text=True,
            check=True,
        )
        json_result = json.loads(result.stdout)
        token = json_result.get("authorizationToken")
        if not token:
            logging.error("❌ No authorization token in AWS response")
            raise Exit(code=1)
        return token
    except subprocess.CalledProcessError as e:
        logging.error("❌ Failed to get CodeArtifact authorization token.")
        logging.debug(f"Command output: {e.stdout}\n{e.stderr}")
        raise Exit(code=1)


# =============================================================================
# Métodos generales
# =============================================================================


def _get_env_file(env):
    """
    Returns the path to the .env file for a given environment.

    Args:
        env (str): Environment name. Examples: 'dev', 'staging', 'prod'.

    Returns:
        str: Relative path to the corresponding .env file.

    Example:
        >>> _get_env_file("dev")
        'conf/dev/.env'
    """
    return DEFAULT_ENV_FOLDER_TEMPLATE.format(env=env)


def _build_env(env: Optional[str] = None, extra_vars: dict = None) -> dict:
    """
    Builds a clean environment dictionary for subprocesses,
    ensuring ~/.local/bin is in PATH and including ENV and any extra vars.

    Args:
        env (str, optional): Environment name. If provided, sets ENV=env.
        extra_vars (dict, optional): Any additional environment variables to inject.

    Returns:
        dict: Environment dictionary for use in subprocesses or ctx.run()
    """
    base_env = os.environ.copy()

    if env is not None:
        base_env["ENV"] = env

    local_bin = str(LOCAL_BIN_PATH)
    current_path = base_env.get("PATH", "")
    path_entries = current_path.split(":")
    if local_bin not in path_entries:
        base_env["PATH"] = f"{local_bin}:{current_path}"

    if extra_vars:
        base_env.update(extra_vars)

    return base_env


def _confirm_action(message, yes=False):
    """
    Confirms a potentially dangerous action with the user.

    Args:
        message (str): The message to display to the user.
        yes (bool): If True, bypasses confirmation and returns True automatically.

    Returns:
        bool: True if confirmed or yes=True, False otherwise.

    Example:
        >>> _confirm_action("Delete all containers?")
        Delete all containers? [y/N]:
    """
    if yes:
        # If we are forcing, skip confirmation
        return True
    confirm = input(f"{message} [y/N]: ")
    return confirm.lower() == "y"


def _load_deployment_config(path=DEFAULT_DEPLOYMENT_FILE):
    """
    Loads the deployment configuration from a YAML file.

    Args:
        path (str): Path to the deployment configuration file.

    Returns:
        dict: Dictionary containing the deployment configuration.

    Raises:
        FileNotFoundError: If the deployment file does not exist.
        yaml.YAMLError: If the file exists but contains invalid YAML.

    Example:
        >>> _load_deployment_config()
        {'profiles': ['infra'], 'aws_account_id': '123...', ...}
    """
    if not Path(path).exists():
        logging.error(f"❌ Deployment configuration file '{path}' not found.")
        raise Exit(code=1)

    with open(path, "r") as f:
        try:
            return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            logging.error(f"❌ Failed to parse YAML file '{path}': {e}")
            raise


def _get_config_from_sources(
    key: str, bws_secrets: Optional[dict] = None, default: Optional[str] = None
) -> Optional[str]:
    """
    Retrieves a configuration value from:
    1. Environment variable
    2. Bitwarden secrets (if provided)
    3. Default value (if defined)

    Args:
        key (str): The name of the variable to retrieve.
        bws_secrets (dict, optional): Dictionary of secrets from Bitwarden.
        default (str, optional): Fallback value if not found elsewhere.

    Returns:
        str | None: The resolved value or None if not found.
    """
    return os.environ.get(key) or (bws_secrets or {}).get(key) or default


def _get_profiles(profiles=None, deployment_file=None):
    """
    Returns the list of Docker Compose profiles to use, as a comma-separated string.

    Args:
        profiles (str, optional): Comma-separated list of profiles. If provided, overrides config file.
        deployment_file (str, optional): Path to a deployment YAML file. Used only if profiles is not provided.

    Returns:
        str: Comma-separated list of profiles to activate (e.g., 'infra,api').

    Example:
        >>> _get_profiles("infra,api")
        'infra,api'
        >>> _get_profiles(deployment_file="custom-deployment.yml")
        'infra'
    """
    if profiles:
        return ",".join(p.strip() for p in profiles.split(","))
    config = _load_deployment_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    return ",".join(config.get("profiles", ["infra"]))


def _get_profiles_args(profiles=None, deployment_file=None):
    """
    Formats Docker Compose profiles into CLI arguments.

    Args:
        profiles (str, optional): Comma-separated list of profiles to activate.
                                  If provided, overrides the deployment config.
        deployment_file (str, optional): Path to a custom deployment YAML file.
                                         Used only if profiles is not provided.

    Returns:
        str: A string of '--profile <profile>' arguments for Docker Compose.

    Example:
        >>> _get_profiles_args("infra,api")
        '--profile infra --profile api'
        >>> _get_profiles_args(deployment_file="custom-deployment.yml")
        '--profile infra'
    """
    profiles = _get_profiles(profiles, deployment_file)
    return " ".join([f"--profile {p.strip()}" for p in profiles.split(",")])


def _launch_services(
    ctx,
    profiles,
    detach,
    env,
    load_secrets_from_bws=None,
    skip_ecr_login=False,
    deployment_file=None,
):
    """
    Internal helper to start Docker Compose services based on selected profiles.

    Loads secrets from Bitwarden, authenticates with AWS ECR if credentials are available,
    and runs `docker compose up` using the selected mode and environment.

    Args:
        ctx: Invoke context.
        profiles (str): Comma-separated list of profiles to activate.
        detach (bool): Whether to run Docker in detached mode.
        env (str): Environment name (e.g., 'dev', 'prod').
        deployment_file (str, optional): Path to the deployment config file.

    Returns:
        None
    """
    config = _load_deployment_config(path=deployment_file or DEFAULT_DEPLOYMENT_FILE)
    load_secrets = (
        load_secrets_from_bws
        if load_secrets_from_bws is not None
        else config.get(LOAD_SECRETS_FROM_BWS_NAME, True)
    )
    skip_login = skip_ecr_login or config.get(SKIP_ECR_LOGIN_NAME, False)

    bws_secrets = {}
    if load_secrets:
        # Load secrets from Bitwarden
        bws_secrets = _load_secrets_from_bws(deployment_file)
        if not bws_secrets:
            logging.warning("⚠️ No secrets found in Bitwarden. Skipping ECR login.")

    if not skip_login:
        # Secrets may come from env vars even if Bitwarden is disabled
        aws_login_success = _aws_ecr_login(bws_secrets, deployment_file)
        if not aws_login_success:
            logging.warning("⚠️ Docker was not authenticated with AWS ECR")

    # Get the effective profiles
    profiles_args = _get_profiles_args(profiles, deployment_file)
    env_file = _get_env_file(env)
    mode_flag = "-d" if detach else ""
    logging.info(
        f"🔧 Launching services with profiles: {profiles_args} in environment '{env}' "
        f"{'(detached)' if detach else '(interactive)'}..."
    )

    # Merge secrets with OS environment only in memory for the subprocess
    full_env = {**os.environ, **bws_secrets, "ENV": env}

    ctx.run(
        f"{DOCKER_COMPOSE_CMD} --env-file {env_file} {profiles_args} up {mode_flag}".strip(),
        env=full_env,
        pty=True,
    )


def _check_bws_configuration(deployment_file=None) -> Tuple[bool, dict]:
    """
    Checks if Bitwarden CLI is installed and if the BWS access token is available and valid.

    If everything is correct, attempts to load secrets from Bitwarden.

    Args:
        deployment_file (str, optional): Path to the deployment configuration file.

    Returns:
        Tuple[bool, dict]: A tuple containing:
            - True if Bitwarden is correctly configured.
            - A dictionary with loaded secrets (empty if failed or unavailable).

    Example:
        >>> _check_bws_configuration()
        (True, {'AWS_ACCESS_KEY_ID': '...', 'DB_PASSWORD': '...'})
    """
    logging.info("🛡️ BWS Configuration Checklist")

    # 1) Check if bws is installed
    bws_installed = _find_tool("bws") is not None
    logging.info(f"{'✅' if bws_installed else '❌'} Bitwarden CLI (bws) installed")

    # 2) Check if there's a BWS token
    token: Optional[str] = _get_bws_token(deployment_file)
    logging.info(f"{'✅' if token else '❌'} BWS_ACCESS_TOKEN is set")

    if not bws_installed or token is None:
        logging.info("⚠️ Skipping secrets access check (missing CLI or token)")
        return False, {}

    # 3) Check if token is valid by listing secrets
    bws_secrets = _load_secrets_from_bws(deployment_file)
    if bws_secrets:
        logging.info("✅ BWS access token is valid and secrets are accessible")
        return True, bws_secrets
    else:
        logging.info("❌ BWS access token is invalid or expired")
        return False, {}


def _check_aws_configuration(bws_secrets: dict, deployment_file=None):
    """
    Checks if AWS CLI is installed and if credentials from Bitwarden are available.

    If so, attempts to log in to AWS ECR.

    Args:
        bws_secrets (dict): Dictionary containing AWS credentials from Bitwarden.
        deployment_file (str, optional): Path to the deployment configuration file.

    Returns:
        None: Logs results, does not raise exceptions.

    Example:
        >>> _check_aws_configuration({'AWS_ACCESS_KEY_ID': '...', 'AWS_SECRET_ACCESS_KEY': '...'})
    """
    logging.info("🛡️ AWS CLI & Credentials")

    # 1) Check if AWS CLI is installed
    aws_cli_installed = _find_tool("aws") is not None
    logging.info(f"{'✅' if aws_cli_installed else '❌'} AWS CLI installed")

    # 2) Retrieve AWS credentials from Bitwarden secrets
    aws_access_key = bws_secrets.get(AWS_KEY_ID_VARIABLE_NAME)
    aws_secret_key = bws_secrets.get(AWS_SECRET_VARIABLE_NAME)
    aws_session_token = bws_secrets.get(AWS_TOKEN_VARIABLE_NAME)

    # 3) Retrieve region/account from deployment.yml (o defaults)
    aws_account_id = _get_aws_account_id(deployment_file)
    aws_region = _get_aws_region(deployment_file)

    # Print checks
    logging.info(
        f"{'✅' if aws_access_key else '❌'} AWS_KEY_ID_VARIABLE_NAME in Bitwarden"
    )
    logging.info(
        f"{'✅' if aws_secret_key else '❌'} AWS_SECRET_VARIABLE_NAME in Bitwarden"
    )
    logging.info(
        f"{'✅' if aws_account_id else '❌'} AWS_ACCOUNT_ID in deployment.yml or default"
    )
    logging.info(
        f"{'✅' if aws_region else '❌'} AWS_REGION from deployment.yml or default"
    )

    # 4) If everything is set and AWS CLI is installed, try ECR login
    if aws_cli_installed and all(
        [aws_access_key, aws_secret_key, aws_account_id, aws_region]
    ):
        # Llamamos a la función real de login para no duplicar lógica
        aws_login_success = _aws_ecr_login(bws_secrets)
        if aws_login_success:
            logging.info("✅ Docker successfully authenticated with AWS ECR")
        else:
            logging.warning("❌ Docker failed to authenticate with AWS ECR")
    elif aws_cli_installed:
        logging.info(
            "⚠️ Skipping ECR login check (missing AWS credentials in Bitwarden)"
        )
    else:
        logging.info("⚠️ Skipping ECR login check (AWS CLI not installed)")


def _check_security_configuration():
    """
    Performs a global security check including Bitwarden and AWS configuration validation.

    - Checks Bitwarden CLI and token availability.
    - Loads secrets and validates access.
    - If Bitwarden is configured, proceeds to check AWS CLI and ECR authentication.

    Returns:
        None

    Example:
        >>> _check_security_configuration()
    """
    logging.info("🔐 Security Configuration Checklist")

    # 1) Check Bitwarden
    bws_ok, bws_secrets = _check_bws_configuration()

    # 2) If Bitwarden is OK, proceed with AWS checks
    if bws_ok:
        _check_aws_configuration(bws_secrets)
    else:
        logging.info(
            "❌ Skipping AWS checks because Bitwarden is not properly configured."
        )


def _check_local_bin_exists():
    """Checks if ~/.local/bin exists."""
    if not LOCAL_BIN_PATH.exists():
        logging.warning(f"❌ {LOCAL_BIN_PATH} does not exist.")
    else:
        logging.info(f"✅ {LOCAL_BIN_PATH} exists.")


def _check_local_bin_in_path():
    """Checks if ~/.local/bin is in the PATH environment variable."""
    path_entries = os.environ.get("PATH", "").split(":")
    if str(LOCAL_BIN_PATH) not in path_entries:
        logging.warning("❌ ~/.local/bin is not in your PATH environment variable.")
        logging.info(
            "   Add the following to your shell profile (~/.bashrc, ~/.zshrc, etc):"
        )
        logging.info(f'   export PATH="$HOME/.local/bin:$PATH"')
    else:
        logging.info("✅ ~/.local/bin is in your PATH.")


def _check_tool(tool: str, install_hint: str):
    """
    Checks if a CLI tool is available in PATH.

    Args:
        tool (str): Name of the tool, e.g. 'aws' or 'bws'.
        install_hint (str): A command or hint to install the tool if not present.

    Returns:
        bool: True if the tool is found, False otherwise.
    """
    tool_path = _find_tool(tool)
    if tool_path:
        logging.info(f"✅ {tool} CLI is available at {tool_path}")
        return True
    else:
        logging.warning(f"❌ {tool} CLI is not found in PATH.")
        logging.info(f"   Install it by running: {install_hint}")
        return False


def _check_aws():
    """
    Checks the AWS CLI and warns if it is installed globally instead of locally.
    """
    installed = _check_tool("aws", "invoke aws.install-cli")
    if installed:
        tool_path = _find_tool("aws")
        if tool_path.startswith("/usr/local") and str(LOCAL_BIN_PATH) not in tool_path:
            logging.warning(
                "⚠️ AWS CLI is installed globally. Consider removing it for full local isolation."
            )


def _check_bws():
    """Checks the Bitwarden CLI."""
    _check_tool("bws", "invoke bws.install-cli")


def _check_pip():
    """Checks that pip is installed."""
    _check_tool("pip", "Please install pip using your package manager.")


def _check_uv():
    """Checks that uv is installed."""
    _check_tool(
        "uv", "Refer to https://github.com/astral-sh/uv for installation instructions."
    )


def _check_docker_installed() -> bool:
    """Checks that Docker is installed."""
    return _check_tool(
        "docker", "Please install Docker: https://docs.docker.com/get-docker/"
    )


def _check_docker_access() -> bool:
    """Checks if the current user can run Docker commands."""
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        logging.info("✅ Docker is accessible (docker info succeeded).")
        return True
    except subprocess.CalledProcessError as e:
        logging.warning(
            "❌ Docker is installed but not accessible to the current user."
        )
        logging.info(
            "   👉 This usually means your user is not part of the 'docker' group.\n"
            "   ➕ To fix it, run:\n"
            "      sudo usermod -aG docker $USER\n"
            "   🌀 Then log out and log back in, or run:\n"
            "      newgrp docker"
        )
        logging.debug(f"Docker access error: {e}")
        return False
    except FileNotFoundError:
        logging.error("❌ Docker binary not found in PATH.")
        return False


def _check_docker_environment():
    """Performs a complete check for Docker: installed and accessible."""
    installed = _check_docker_installed()
    if installed:
        _check_docker_access()


def _check_unzip():
    """Checks that unzip is installed."""
    _check_tool("unzip", "Please install unzip using your package manager.")


def _check_curl():
    """Checks that curl is installed."""
    _check_tool(
        "curl",
        "Please install curl using your package manager (e.g., apt, brew, pacman, etc).",
    )


def _ensure_tool_installed(tool_name: str, install_function: Callable) -> bool:
    """
    Ensures that a CLI tool is installed. If not found, attempts to install it.

    Args:
        tool_name (str): The name of the CLI tool to check (e.g., 'bws', 'aws').
        install_function (Callable): The function to call to install the tool.

    Returns:
        bool: True if the tool is installed or successfully installed, False otherwise.
    """
    if _find_tool(tool_name):
        logging.info(f"✅ {tool_name} is already installed.")
        return True

    logging.warning(f"{tool_name} not found. Attempting to install...")
    try:
        install_function()
        return True
    except Exception as e:
        logging.error(f"Failed to install {tool_name}: {e}")
        return False


def _find_tool(tool_name: str) -> Optional[str]:
    """
    Attempts to find a CLI tool, first using PATH, then by checking ~/.local/bin manually.

    Args:
        tool_name (str): Tool binary name (e.g. 'bws', 'aws').

    Returns:
        Optional[str]: Path to the tool if found, None otherwise.
    """
    # Try using PATH first
    path = shutil.which(tool_name)
    if path:
        return path

    # Fallback to ~/.local/bin/tool_name
    fallback_path = LOCAL_BIN_PATH / tool_name
    if fallback_path.exists() and os.access(fallback_path, os.X_OK):
        return str(fallback_path)

    return None


# =============================================================================
# Definición de tareas con Invoke
# =============================================================================


# BWS Tasks


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

# Docker Tasks


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

# Check Tasks


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


# Global Tasks


@task
def help(ctx):
    """
    Shows a custom help menu with tasks grouped by category.

    This command groups available tasks into sections such as AWS, Docker,
    Bitwarden, and Check, providing a short description for each one.

    Usage:
        invoke help

    Example:
        invoke help
    """
    # Cabecera
    header = Panel.fit(
        Align.center(
            "[bold blue]🧿 seshat cli[/bold blue]\n"
            "[dim]Secure Environment Setup & Host Automation Toolkit[/dim]\n\n"
            "[green]💡 Run tasks with:[/green] [bold]invoke <task>[/bold]  e.g. [bold]invoke docker.up[/bold]",
            vertical="middle",
        ),
        border_style="bright_blue",
        padding=(1, 4),
        width=80,
    )
    console.print(header)

    def _print_section(title: str, commands: list[tuple[str, str]]):
        console.print(f"\n[bold yellow]{title}[/bold yellow]\n")

        table = Table(
            show_header=True, header_style="bold magenta", box=None, pad_edge=False
        )
        table.add_column(" Task", style="green", min_width=36, no_wrap=True)
        table.add_column("Description", style="white", min_width=40, justify="left")

        for cmd, desc in commands:
            table.add_row(cmd, desc)
        console.print(table)

    _print_section(
        "📦 AWS Tasks",
        [
            (" aws.install-cli", "Install AWS CLI locally"),
            (" aws.remove-cli", "Remove AWS CLI"),
            (" aws.configure-pip", "Configure pip with CodeArtifact"),
            (" aws.configure-uv", "Configure uv with CodeArtifact"),
            (" aws.reset-pypi", "Reset pip/uv to public PyPI"),
            (" aws.create-ca-env-file", "Create .env.codeartifact file with token"),
            (
                " aws.export-ca-token-env-var",
                "⚠️  Export token (must run with 'source')",
            ),
        ],
    )

    _print_section(
        "🔐 Bitwarden Tasks",
        [
            (" bws.install-cli", "Install Bitwarden CLI"),
            (" bws.remove-cli", "Remove Bitwarden CLI"),
        ],
    )

    _print_section(
        "🐳 Docker Tasks",
        [
            (" docker.up", "Start services (foreground)"),
            (" docker.up-daemon", "Start services (detached)"),
            (" docker.down", "Stop and remove services"),
            (" docker.build", "Build images"),
            (" docker.ps", "Show container status"),
            (" docker.logs", "Show logs"),
            (" docker.clean-environment", "Clean Docker environment"),
            (" docker.create-network", "Create Docker network"),
            (" docker.remove-network", "Remove Docker network"),
            (" docker.restart", "Restart services"),
        ],
    )

    _print_section(
        "🧪 Check Tasks",
        [
            (" check.environment", "Check system prerequisites"),
            (" check.security", "Check security configuration"),
        ],
    )

    _print_section(
        "🔧 Miscellaneous",
        [
            (" version", "Show current CLI version"),
            (" help", "Show this help menu"),
        ],
    )

    console.print(
        "\n[dim]💡 Tip: Use [bold]invoke -l[/bold] to list all available tasks[/dim]\n"
    )


@task
def version(ctx):
    """
    Prints the current version of the CLI tool.

    Usage:
        invoke version

    Example:
        invoke version
    """
    print(f"{VERSION}")


# ns.add_collection(aws_ns)
# ns.add_collection(bws_ns)
# ns.add_collection(docker_ns)
# ns.add_collection(check_ns)

import logging
from pathlib import Path

from invoke import task
from rich.align import Align
from rich.panel import Panel
from rich.table import Table

from anubis.utils import (
    DEFAULT_DEPLOYMENT_FILE,
    VERSION,
    _install_deployment_as_global,
    console,
)


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
            "[bold blue]𓁢 anubis cli[/bold blue]\n"
            "[dim]Automated Network & User Base Installation Service[/dim]\n\n"
            "[green]💡 Run tasks with:[/green] [bold]anubis <task>[/bold]  e.g. [bold]anubis docker.up[/bold]",
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
        "🧰 DAGs Tasks",
        [
            (
                "airflow.deploy-dags",
                "Deploy DAGs (and spark jobs associated) configured in deployment.yml",
            ),
            (
                "airflow.remove-dags",
                "Remove-reset DAGs (and spark jobs associated) from infrastructure",
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
            (
                " install-global-config",
                "Install deployment file as global configuration",
            ),
        ],
    )

    console.print(
        "\n[dim]💡 Tip: Use [bold]anubis -l[/bold] to list all available tasks[/dim]\n"
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


@task(
    help={
        "path": "Path to the deployment file to install globally. Defaults to deployment.yml"
    }
)
def install_global_config(ctx, path=DEFAULT_DEPLOYMENT_FILE):
    """
    Installs a deployment configuration file as the global configuration.

    Copies the specified deployment file to ~/.config/anubis/deployment.yml
    so it can be used as a fallback when no local deployment file exists.

    Usage:
        invoke install-global-config
        invoke install-global-config --path=custom-deployment.yml

    Example:
        invoke install-global-config
    """

    source_path = Path(path)

    if not source_path.exists():
        logging.error(f"❌ Source deployment file '{path}' not found.")
        logging.info(
            f"ℹ️ You need to have a '{DEFAULT_DEPLOYMENT_FILE}' file in the current directory"
        )
        logging.info("ℹ️ or specify a valid path with --path parameter.")
        logging.info(
            "ℹ️ Example: anubis install-global-config --path=./my-custom-deployment.yml"
        )
        return

    _install_deployment_as_global(path)

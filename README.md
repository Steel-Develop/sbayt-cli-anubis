<h1 align="center">𓁢 Anubis CLI</h1>

<p align="center">
    <em>Automated Network & User Base Installation Service</em>
</p>

<p align="center">
<a href="https://pypi.org/project/anubis-cli" target="_blank">
    <img src="https://img.shields.io/pypi/v/anubis-cli?color=%2334D058&label=pypi%20package" alt="Package version">
</a>
<a href="https://pypi.org/project/anubis-cli" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/anubis-cli.svg?color=%2334D058" alt="Supported Python versions">
</a>
</p>

---

📖 Read this in other languages:
- [Español](./README.es.md)

---

## Description

This tool defines and organizes a set of automated tasks to configure and manage development/production environments.
It uses `invoke` to structure tasks and `rich` to enhance the terminal experience.

### Main Features

- Local installation and management of essential CLI tools (AWS CLI, Bitwarden CLI).
- Configuration of private repositories (CodeArtifact) for `pip` and `uv`.
- Docker service automation (`create network`, `start`, `stop`, `clean`, `build`).
- Verification of security configurations and local environment (Bitwarden, AWS ECR, etc.).

## Installation & Basic Usage

### Requirements

- [Python](https://www.python.org/downloads/) >= 3.10
- [uv](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) >= 0.7.0
- A deployment file (local or global, default: `deployment.yml`) to define profiles and credentials.

### Global Installation

To install the tool globally, you can use `uv` (**recommended**) or `pipx`.

```bash
# With uv (recommended)
uv tool install anubis-cli
```

```bash
# With pipx
pipx install anubis-cli
```

### Basic Usage

 1. View available tasks:

```bash
anubis help
```

 2. Check your local environment:

```bash
anubis check.environment
```

 3. Start Docker services with specific profiles:

```bash
anubis docker.up --profiles=infra,api --env=prod
```

 4. Configure pip for CodeArtifact:

```bash
anubis aws.configure-pip
```

Enable autocompletion for `anubis`:

```bash
# For bash
anubis --print-completion-script bash > ~/.anubis-completion.bash
echo "source ~/.anubis-completion.bash" >> ~/.bashrc
source ~/.bashrc

# For zsh
anubis --print-completion-script zsh > ~/.anubis-completion.zsh
echo "source ~/.anubis-completion.zsh" >> ~/.zshrc
source ~/.zshrc
```

For more details or additional examples, check each task’s documentation using
`anubis --list` or review the individual docstrings.

## Development Environment Setup

### Requirements

- [Python](https://www.python.org/downloads/) >= 3.10
- [uv](https://github.com/astral-sh/uv?tab=readme-ov-file#installation) >= 0.7.0

### Setup

1. Create the virtual environment:

```bash
uv sync
```

2. Verify the virtual environment was created correctly:

```bash
uv pip check
uv tree
```

3. Use the virtual environment:

   With `uv` as package manager, you can use the environment in two ways:

   - (**Recommended**) Run commands inside the virtual environment with `uv run <command>`:

```bash
uv run anubis
uv run pytest -m unit
```

   - Activate the virtual environment:

```bash
source .venv/bin/activate
```

## Dependency Management

Using `uv` as package manager, you can easily handle project dependencies.
When a dependency is installed, it is stored in `uv.lock` to reproduce the environment elsewhere, and added to `pyproject.toml`.

- Install or update a dependency:

```bash
uv add <package>
```

- Add development dependencies:

```bash
uv add --dev <package>
```

- Remove a dependency:

```bash
uv remove <package>
uv remove --dev <package>
```

- Export dependencies to `requirements.txt`:

```bash
uv export --no-hashes -o requirements.txt
```

## Creating a New Package

1. Build the package:

```bash
uv build
```

2. A `dist` folder will be created with the package and its wheel.

3. Install the package in another project’s virtual environment:

```bash
uv tool install --from dist/anubis_cli-{version}-py3-none-any.whl anubis-cli
```

## Contributing

For a complete guide on how to contribute to the project, please review the [Contribution Guide](https://github.com/Steel-Develop/sbayt-internal-agreements/blob/master/CONTRIBUTING.md).

### Reporting Issues

If you believe you've found a defect in this project or its documentation, open an issue in [Jira](https://steeldevelop.atlassian.net/) so we can address it.

If you're unsure whether it's a bug, feel free to discuss it in our forums or internal chat—someone will be happy to help.

## Code of Conduct

See the [Code of Conduct](https://github.com/Steel-Develop/sbayt-internal-agreements/blob/master/code-of-conduct.md).

## License

See the [LICENSE](./LICENSE) file.

# Anubis CLI

Anubis provides a small command-line interface for local developer tooling and
Kubernetes infrastructure operations. It delegates to the native tools and
does not replace Terraform, Ansible, Helmfile or kubectl.

[Leer en español](README.es.md)

## Installation

Anubis requires Python 3.12 or newer. Install the public package with either:

```bash
uv tool install anubis-cli
# or
pipx install anubis-cli
```

Run `anubis --help` to inspect the available commands.

On Linux x86_64 and arm64, each workflow installs or updates the user CLIs it
needs under `~/.local/bin`. This includes Helm, Helmfile, kubectl, Kind,
Terraform, helm-diff, uv, BWS and AWS CLI.

Python 3.12+, Docker, SSH, sudo, KVM and libvirt are system capabilities, so
Anubis validates them when relevant but never installs or configures them.
Ansible Core is installed with Anubis; compatible IaC repositories provide
their playbooks, roles and collection requirements.

Enable shell completion once after installation:

```bash
# zsh
anubis --print-completion-script zsh > ~/.anubis-completion.zsh
echo 'source ~/.anubis-completion.zsh' >> ~/.zshrc

# bash
anubis --print-completion-script bash > ~/.anubis-completion.bash
echo 'source ~/.anubis-completion.bash' >> ~/.bashrc
```

Start a new shell or source the generated file to activate it immediately.

## Kubernetes workflow

From a compatible IaC repository:

```bash
anubis install internal/local
anubis stop
anubis start
anubis update
anubis destroy --yes
```

`install` prepares the cluster and deploys the product. Use the individual
commands when only one stage is needed. Advanced cluster operations are
grouped under `anubis cluster`.

An installation may be referenced by its logical name, its directory or its
`installation.yaml` path. Anubis remembers the last explicit selection in the
repository's ignored `.work/anubis/active-installation` file, so later commands
may omit it. Passing another installation switches the active selection.
`--repository PATH` is only needed when Anubis cannot discover the repository
from the current directory.

RKE2 installations may set `provisioning.askBecomePass: true` to request the
sudo password interactively without storing it. The command-line options
`--ask-become-pass` and `--no-ask-become-pass` override that setting for one run.

`stop` scales product processes to zero but keeps databases, Kafka, operators
and volumes available. `start`, `deploy` or `update` resume the declared
replicas. `destroy --yes` irreversibly removes the product and its Kubernetes
data while preserving the cluster; `cluster destroy --yes` also removes a
managed Kind or Terraform/libvirt cluster.

`deploy` forces reconciliation of every release and is useful for an initial
deployment or for correcting manual cluster drift. `update` is the routine
maintenance operation: it shows the diff and applies only releases whose
declared configuration changed.

### Optional repository configuration

A repository may contain an optional `anubis.yaml` with shared, non-secret
configuration. Exact IaC client versions and Bitwarden bindings can be kept
together:

```yaml
toolchain:
  helm: 4.2.4
  helmfile: 1.7.4
  kubectl: 1.36.4
  kind: 0.33.0
  terraform: 1.16.1
  helm-diff: 3.15.12

bitwarden:
  bindings:
    runtime.bootstrapUsers.mongodb: MONGO_INITDB_ROOT_USERNAME
```

The file is not required. Anubis uses supported default tool versions and a
complete installation manifest can be operated without it. User defaults such
as AWS and CodeArtifact coordinates can also be stored in
`~/.config/anubis/config.toml` through `anubis config init`.

Binding paths target the temporary resolved manifest. Repositories can reserve
an internal namespace such as `runtime` without exposing it in the public
installation schema.

A repository may also provide `installations/schema.json`. When present,
Anubis validates the original `installation.yaml` against that JSON Schema
before resolving secrets or starting an operation. Repositories without a
schema keep the existing behavior.

Set `BWS_ACCESS_TOKEN` or enter it at the hidden prompt. Tokens and passwords
are never written to configuration or the repository. Local installation
context is stored under the repository's ignored `.work/anubis/` directory.

## Retained developer tooling

```bash
anubis bitwarden install
anubis bitwarden remove
anubis aws install
anubis aws configure-pip
anubis aws configure-uv
anubis aws token
anubis check environment [INSTALLATION]
```

`check environment` is strictly read-only. Without an installation it checks
the retained developer tooling; with one it reports the required tool, path,
expected version, detected version and status for that deployment workflow.
Normal operations automatically repair missing or incompatible managed CLIs.

AWS settings come from command options, `ANUBIS_*` environment variables, the
optional repository configuration or the user configuration. AWS credentials
may come from the standard environment or the selected Bitwarden project.
`anubis aws configure-uv` replaces `~/.config/uv/uv.toml`; `anubis aws reset`
removes that Anubis-managed file.

## Development

```bash
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run anubis --help
uv build
```

The package uses only public PyPI dependencies. Build artifacts must not
contain deployment manifests, credentials or organization-specific runtime
configuration.

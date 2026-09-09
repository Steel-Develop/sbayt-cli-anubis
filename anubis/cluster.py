"""Kind, Terraform/libvirt and RKE2 cluster operations."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from anubis.errors import AnubisError
from anubis.kubernetes import kubeconfig_path
from anubis.process import Runner
from anubis.repository import Installation, Repository
from anubis.tools import download_verified, ensure_project_tools, file_sha256


def _require(*tools: str) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise AnubisError(f"missing tools: {', '.join(missing)}")


def _bundled_tool(name: str) -> Path:
    executable = Path(sys.executable).with_name(name)
    if not executable.is_file():
        raise AnubisError(f"Anubis installation does not provide {name}; reinstall anubis-cli")
    return executable


def _kind_name(installation: Installation) -> str:
    return installation.kube_context.removeprefix("kind-")


_KIND_NODE_SYSCTLS = {
    "fs.inotify.max_user_instances": "8192",
    "fs.inotify.max_user_watches": "1048576",
}


def configure_kind_node(installation: Installation, runner: Runner) -> None:
    """Apply node-level limits required by cluster-wide log collection."""
    cluster = _kind_name(installation)
    nodes = runner.run(
        ["kind", "get", "nodes", "--name", cluster], capture=True
    ).stdout.splitlines()
    if len(nodes) != 1:
        raise AnubisError("the Kind development profile requires exactly one node")
    for name, value in _KIND_NODE_SYSCTLS.items():
        runner.run(
            ["docker", "exec", nodes[0], "sysctl", "-w", f"{name}={value}"],
            capture=True,
        )


def kind_prepare(repository: Repository, installation: Installation, runner: Runner) -> Path:
    ensure_project_tools(runner, repository.config, "kind", "kubectl")
    _require("docker")
    runner.run(["docker", "info"], capture=True)
    cluster = _kind_name(installation)
    work = repository.work / "kind" / cluster
    work.mkdir(parents=True, exist_ok=True)
    kubeconfig = work / "kubeconfig"
    clusters = runner.run(["kind", "get", "clusters"], capture=True).stdout.splitlines()
    if cluster not in clusters:
        runner.run(
            [
                "kind",
                "create",
                "cluster",
                "--name",
                cluster,
                "--config",
                repository.root / "kubernetes/kind.yaml",
                "--kubeconfig",
                kubeconfig,
                "--wait",
                "120s",
            ]
        )
    runner.run(["kind", "export", "kubeconfig", "--name", cluster, "--kubeconfig", kubeconfig])
    configure_kind_node(installation, runner)
    kind_check(repository, installation, runner)
    return kubeconfig


def kind_check(repository: Repository, installation: Installation, runner: Runner) -> None:
    kubeconfig = kubeconfig_path(repository, installation)
    command = ["kubectl", "--kubeconfig", kubeconfig]
    runner.run([*command, "wait", "--for=condition=Ready", "node", "--all", "--timeout=120s"])
    nodes = runner.run([*command, "get", "nodes", "-o", "name"], capture=True).stdout.splitlines()
    if len(nodes) != 1:
        raise AnubisError("the Kind development profile requires exactly one node")
    runner.run(
        [
            *command,
            "-n",
            "kube-system",
            "wait",
            "--for=condition=Available",
            "deployment",
            "--all",
            "--timeout=120s",
        ]
    )
    runner.run([*command, "get", "storageclass", "standard"], capture=True)


def kind_destroy(repository: Repository, installation: Installation, runner: Runner) -> None:
    ensure_project_tools(runner, repository.config, "kind")
    cluster = _kind_name(installation)
    kubeconfig = repository.work / "kind" / cluster / "kubeconfig"
    runner.run(["kind", "delete", "cluster", "--name", cluster, "--kubeconfig", kubeconfig])


@dataclass(frozen=True)
class TerraformLab:
    repository: Repository
    installation: Installation
    runner: Runner
    base_image: Path
    ssh_public_key: Path

    @property
    def inputs(self) -> Path:
        return self.installation.path.parent / "terraform.tfvars"

    @property
    def root(self) -> Path:
        return self.repository.root / "terraform/roots/libvirt-dev"

    @property
    def work(self) -> Path:
        return self.repository.work / "terraform" / self.installation.path.parent.name

    @property
    def data(self) -> Path:
        return self.work / "data"

    @property
    def state(self) -> Path:
        return self.work / "terraform.tfstate"

    @property
    def plan_file(self) -> Path:
        return self.work / "terraform.tfplan"

    @property
    def inventory(self) -> Path:
        return self.work / "inventory.yml"

    @property
    def known_hosts(self) -> Path:
        return self.work / "known_hosts"

    @property
    def environment(self) -> dict[str, str]:
        return {"TF_DATA_DIR": str(self.data)}

    def init(self) -> None:
        ensure_project_tools(self.runner, self.repository.config, "terraform")
        if not self.inputs.is_file():
            raise AnubisError(f"Terraform inputs not found: {self.inputs}")
        self.work.mkdir(parents=True, exist_ok=True)
        self.runner.run(
            [
                "terraform",
                f"-chdir={self.root}",
                "init",
                "-input=false",
                "-reconfigure",
                f"-backend-config=path={self.state}",
            ],
            env=self.environment,
        )

    def plan(self) -> None:
        self.init()
        if not self.base_image.is_file():
            raise AnubisError(f"Ubuntu image not found: {self.base_image}")
        if not self.ssh_public_key.is_file():
            raise AnubisError(f"SSH public key not found: {self.ssh_public_key}")
        self.runner.run(
            [
                "terraform",
                f"-chdir={self.root}",
                "plan",
                "-input=false",
                f"-var-file={self.inputs}",
                f"-var=base_image_path={self.base_image}",
                f"-var=ssh_public_key_path={self.ssh_public_key}",
                f"-out={self.plan_file}",
            ],
            env=self.environment,
        )

    def apply(self) -> None:
        self.plan()
        self.runner.run(
            ["terraform", f"-chdir={self.root}", "apply", "-input=false", self.plan_file],
            env=self.environment,
        )
        inventory = self.runner.run(
            ["terraform", f"-chdir={self.root}", "output", "-raw", "ansible_inventory"],
            env=self.environment,
            capture=True,
        ).stdout
        self.inventory.write_text(inventory, encoding="utf-8")
        self.inventory.chmod(0o600)
        self.known_hosts.touch(mode=0o600, exist_ok=True)

    def destroy(self) -> None:
        self.init()
        self.runner.run(
            [
                "terraform",
                f"-chdir={self.root}",
                "destroy",
                f"-var-file={self.inputs}",
                f"-var=base_image_path={self.base_image}",
                f"-var=ssh_public_key_path={self.ssh_public_key}",
            ],
            env=self.environment,
        )


def default_base_image(repository: Repository) -> Path:
    catalog = yaml.safe_load(
        (repository.root / "release/catalog.yaml").read_text(encoding="utf-8")
    )
    image = catalog["files"]["ubuntu-noble-amd64"]
    return repository.work / "images" / Path(image["source"]).name


def ensure_base_image(repository: Repository, runner: Runner, destination: Path) -> None:
    catalog = yaml.safe_load(
        (repository.root / "release/catalog.yaml").read_text(encoding="utf-8")
    )
    image = catalog["files"]["ubuntu-noble-amd64"]
    expected = image["sha256"]
    if destination.is_file() and file_sha256(destination) == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    download_verified(image["source"], destination, expected, "Ubuntu image")


def rke2_inventory(
    repository: Repository, installation: Installation, explicit: Path | None
) -> Path:
    if explicit:
        candidate = explicit.expanduser().resolve()
    elif (installation.path.parent / "inventory.yaml").is_file():
        candidate = installation.path.parent / "inventory.yaml"
    else:
        candidate = repository.work / "terraform" / installation.path.parent.name / "inventory.yml"
    if not candidate.is_file():
        raise AnubisError(f"RKE2 inventory not found: {candidate}")
    return candidate


def rke2(
    repository: Repository,
    installation: Installation,
    runner: Runner,
    *,
    inventory: Path | None = None,
    check: bool = False,
    ask_become_pass: bool = False,
) -> None:
    _require("ssh")
    selected_inventory = rke2_inventory(repository, installation, inventory)
    collections = repository.root / ".cache/ansible/collections"
    collections.mkdir(parents=True, exist_ok=True)
    environment: dict[str, str] = {
        "ANSIBLE_CONFIG": str(repository.root / "ansible/ansible.cfg"),
        "ANSIBLE_COLLECTIONS_PATH": str(collections),
        "RKE2_KUBECONFIG": str(
            repository.work / "rke2" / installation.kube_context / "kubeconfig"
        ),
    }
    generated = repository.work / "terraform" / installation.path.parent.name / "inventory.yml"
    if selected_inventory.resolve() == generated.resolve():
        known_hosts = generated.parent / "known_hosts"
        environment["ANSIBLE_SSH_COMMON_ARGS"] = (
            f"-o UserKnownHostsFile={known_hosts} -o StrictHostKeyChecking=accept-new"
        )
    runner.run(
        [
            _bundled_tool("ansible-galaxy"),
            "collection",
            "install",
            "-r",
            "ansible/requirements.yml",
            "-p",
            collections,
        ],
        cwd=repository.root,
        env=environment,
    )
    command = [
        _bundled_tool("ansible-playbook"),
        "-i",
        selected_inventory,
        "ansible/playbooks/rke2.yml",
    ]
    if check:
        command.extend(["--check", "--diff"])
    if ask_become_pass:
        command.append("--ask-become-pass")
    runner.run(command, cwd=repository.root, env=environment)


def is_managed_lab(installation: Installation) -> bool:
    return (installation.path.parent / "terraform.tfvars").is_file()

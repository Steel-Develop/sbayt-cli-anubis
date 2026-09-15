import subprocess
from pathlib import Path

from anubis.cluster import TerraformLab, configure_kind_node, rke2
from anubis.repository import Installation, Repository


class KindRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command, **_kwargs):
        rendered = [str(value) for value in command]
        self.commands.append(rendered)
        output = "serquet-dev-control-plane\n" if rendered[:3] == ["kind", "get", "nodes"] else ""
        return subprocess.CompletedProcess(rendered, 0, output, "")


def test_given_kind_cluster_when_node_is_configured_then_inotify_limits_are_raised(
    tmp_path: Path,
) -> None:
    installation = Installation(
        tmp_path / "installation.yaml",
        {
            "name": "local",
            "clusterProfile": "kind",
            "kubeContext": "kind-serquet-dev",
        },
    )
    runner = KindRunner()

    configure_kind_node(installation, runner)  # type: ignore[arg-type]

    assert runner.commands == [
        ["kind", "get", "nodes", "--name", "serquet-dev"],
        [
            "docker",
            "exec",
            "serquet-dev-control-plane",
            "sysctl",
            "-w",
            "fs.inotify.max_user_instances=8192",
        ],
        [
            "docker",
            "exec",
            "serquet-dev-control-plane",
            "sysctl",
            "-w",
            "fs.inotify.max_user_watches=1048576",
        ],
    ]


def test_given_rke2_installation_when_prepared_then_bundled_ansible_is_used(
    tmp_path: Path, monkeypatch
) -> None:
    installation_path = tmp_path / "installations/internal/cpd/installation.yaml"
    installation_path.parent.mkdir(parents=True)
    inventory = installation_path.parent / "inventory.yaml"
    inventory.write_text("all: {}\n", encoding="utf-8")
    installation = Installation(
        installation_path,
        {
            "name": "cpd",
            "clusterProfile": "rke2-single-node",
            "kubeContext": "serquet-cpd",
        },
    )
    runner = KindRunner()
    monkeypatch.setattr("anubis.cluster._require", lambda *_tools: None)
    monkeypatch.setattr("anubis.cluster._bundled_tool", lambda name: Path("/anubis/bin") / name)

    rke2(Repository(tmp_path, {}), installation, runner)

    assert runner.commands == [
        [
            "/anubis/bin/ansible-galaxy",
            "collection",
            "install",
            "-r",
            "ansible/requirements.yml",
            "-p",
            str(tmp_path / ".cache/ansible/collections"),
        ],
        [
            "/anubis/bin/ansible-playbook",
            "-i",
            str(inventory),
            "ansible/playbooks/rke2.yml",
        ],
    ]


def test_given_managed_lab_when_destroyed_then_stale_host_keys_are_removed(
    tmp_path: Path, monkeypatch
) -> None:
    installation_path = tmp_path / "installations/internal/rke2-ha-dev/installation.yaml"
    installation = Installation(
        installation_path,
        {
            "name": "rke2-ha-dev",
            "clusterProfile": "rke2-ha",
            "kubeContext": "serquet-rke2-ha-dev",
        },
    )
    runner = KindRunner()
    lab = TerraformLab(
        Repository(tmp_path, {}),
        installation,
        runner,  # type: ignore[arg-type]
        tmp_path / "ubuntu.img",
        tmp_path / "id_ed25519.pub",
    )
    lab.work.mkdir(parents=True)
    lab.known_hosts.write_text("stale host key\n", encoding="utf-8")
    monkeypatch.setattr(TerraformLab, "init", lambda _self: None)

    lab.destroy()

    assert not lab.known_hosts.exists()
    assert runner.commands == [
        [
            "terraform",
            f"-chdir={lab.root}",
            "destroy",
            f"-var-file={lab.inputs}",
            f"-var=base_image_path={lab.base_image}",
            f"-var=ssh_public_key_path={lab.ssh_public_key}",
        ]
    ]

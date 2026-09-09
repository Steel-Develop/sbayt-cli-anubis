import subprocess
from pathlib import Path

from anubis.cluster import configure_kind_node, rke2
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

import subprocess
from pathlib import Path

from anubis.cluster import configure_kind_node
from anubis.repository import Installation


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

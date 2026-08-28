import json
import subprocess
from pathlib import Path

import pytest
import yaml

from anubis.errors import AnubisError
from anubis.kubernetes import Kubernetes
from anubis.repository import Installation, Repository


class LifecycleRunner:
    def __init__(
        self,
        *,
        claims=None,
        claims_by_namespace=None,
        volumes=None,
        namespace="serquet",
        observability_namespace=None,
    ):
        self.claims = claims or []
        self.claims_by_namespace = claims_by_namespace or {}
        self.volumes = volumes or []
        self.namespace = namespace
        self.observability_namespace = observability_namespace
        self.commands = []

    def run(self, command, **kwargs):
        command = [str(value) for value in command]
        self.commands.append(command)
        output = ""
        if command[:3] == ["helm", "plugin", "list"]:
            output = "NAME VERSION TYPE APIVERSION PROVENANCE SOURCE\ndiff 3.13.0 cli/v1 legacy unknown unknown\n"
        elif command[0] == "kubectl":
            if "namespace" in command and command[-1] == "json":
                selector = command[command.index("-l") + 1]
                namespace = (
                    self.observability_namespace
                    if selector == "serquet.io/scope=observability"
                    else self.namespace
                )
                items = [] if namespace is None else [{"metadata": {"name": namespace}}]
                output = json.dumps({"items": items})
            elif "persistentvolumeclaim" in command and "json" in command:
                namespace = command[command.index("-n") + 1]
                claims = self.claims_by_namespace.get(
                    namespace, self.claims if namespace == self.namespace else []
                )
                output = json.dumps({"items": claims})
            elif "persistentvolume" in command and command[-1] == "json":
                output = json.dumps({"items": self.volumes})
            elif "persistentvolume" in command and command[-2:] == ["-o", "name"]:
                output = f"persistentvolume/{command[-3]}\n"
            elif "deployment" in command and command[-2:] == ["-o", "name"]:
                output = "deployment.apps/frontend\ndeployment.apps/users\n"
            elif "statefulset" in command and command[-2:] == ["-o", "name"]:
                output = "statefulset.apps/sbayt-edge\n"
        return subprocess.CompletedProcess(command, 0, output, "")


def _lifecycle(tmp_path: Path, runner: LifecycleRunner) -> Kubernetes:
    values = {
        "name": "local",
        "clusterProfile": "kind",
        "kubeContext": "kind-local",
    }
    installation = Installation(tmp_path / "installation.yaml", values)
    installation.path.write_text(yaml.safe_dump(values), encoding="utf-8")
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.touch()
    return Kubernetes(
        Repository(tmp_path, {}), installation, installation.path, kubeconfig, runner
    )


def test_given_running_product_when_stopped_then_processes_and_gateway_are_removed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("anubis.kubernetes.shutil.which", lambda _tool: "/bin/tool")
    runner = LifecycleRunner()

    _lifecycle(tmp_path, runner).stop()

    assert any(
        "deployment" in command and "!strimzi.io/cluster" in command for command in runner.commands
    )
    assert any(
        "deployment.apps/frontend" in command and "--replicas=0" in command
        for command in runner.commands
    )
    assert any(
        "statefulset.apps/sbayt-edge" in command and "--replicas=0" in command
        for command in runner.commands
    )
    assert any(
        "gateway.gateway.networking.k8s.io" in command and "--all" in command
        for command in runner.commands
    )


def test_given_observability_when_stopped_then_gateway_is_preserved(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("anubis.kubernetes.shutil.which", lambda _tool: "/bin/tool")
    runner = LifecycleRunner(observability_namespace="monitoring")

    _lifecycle(tmp_path, runner).stop()

    assert not any(
        "gateway.gateway.networking.k8s.io" in command and "delete" in command
        for command in runner.commands
    )


def test_given_delete_policy_volumes_when_destroyed_then_namespace_precedes_platform(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("anubis.kubernetes.shutil.which", lambda _tool: "/bin/tool")
    claims = [
        {
            "metadata": {"name": "mongo-data"},
            "spec": {"volumeName": "pv-mongo", "storageClassName": "longhorn"},
        }
    ]
    volumes = [
        {
            "metadata": {"name": "pv-mongo"},
            "spec": {"persistentVolumeReclaimPolicy": "Delete"},
        }
    ]
    runner = LifecycleRunner(claims=claims, volumes=volumes)

    _lifecycle(tmp_path, runner).destroy()

    product_destroy = next(
        index
        for index, command in enumerate(runner.commands)
        if command[0] == "helmfile" and "product.yaml.gotmpl" in " ".join(command)
    )
    namespace_delete = next(
        index
        for index, command in enumerate(runner.commands)
        if command[:4] == ["kubectl", "--kubeconfig", str(tmp_path / "kubeconfig"), "delete"]
        and "namespace" in command
    )
    platform_destroy = next(
        index
        for index, command in enumerate(runner.commands)
        if command[0] == "helmfile" and "platform.yaml.gotmpl" in " ".join(command)
    )
    assert product_destroy < namespace_delete < platform_destroy
    assert any(
        "--for=delete" in command and "persistentvolume/pv-mongo" in command
        for command in runner.commands
    )


def test_given_product_namespace_already_absent_when_destroyed_then_platform_is_removed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("anubis.kubernetes.shutil.which", lambda _tool: "/bin/tool")
    runner = LifecycleRunner(namespace=None)

    _lifecycle(tmp_path, runner).destroy()

    helmfile_commands = [command for command in runner.commands if command[0] == "helmfile"]
    assert len(helmfile_commands) == 2
    assert "product.yaml.gotmpl" in " ".join(helmfile_commands[0])
    assert "platform.yaml.gotmpl" in " ".join(helmfile_commands[1])
    assert not any(
        command[0] == "kubectl" and "delete" in command and "namespace" in command
        for command in runner.commands
    )


def test_given_observability_volumes_when_destroyed_then_monitoring_data_is_removed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("anubis.kubernetes.shutil.which", lambda _tool: "/bin/tool")
    monitoring_claim = {
        "metadata": {"name": "prometheus-data"},
        "spec": {"volumeName": "pv-prometheus", "storageClassName": "longhorn"},
    }
    volumes = [
        {
            "metadata": {"name": "pv-prometheus"},
            "spec": {"persistentVolumeReclaimPolicy": "Delete"},
        }
    ]
    runner = LifecycleRunner(
        claims_by_namespace={"monitoring": [monitoring_claim]},
        volumes=volumes,
        observability_namespace="monitoring",
    )

    _lifecycle(tmp_path, runner).destroy()

    assert any(
        "delete" in command and "namespace" in command and "monitoring" in command
        for command in runner.commands
    )
    assert any(
        "--for=delete" in command and "persistentvolume/pv-prometheus" in command
        for command in runner.commands
    )


def test_given_retain_policy_volume_when_destroyed_then_operation_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("anubis.kubernetes.shutil.which", lambda _tool: "/bin/tool")
    claims = [
        {
            "metadata": {"name": "timescaledb-data"},
            "spec": {"volumeName": "pv-timescaledb", "storageClassName": "external"},
        }
    ]
    volumes = [
        {
            "metadata": {"name": "pv-timescaledb"},
            "spec": {"persistentVolumeReclaimPolicy": "Retain"},
        }
    ]
    runner = LifecycleRunner(claims=claims, volumes=volumes)

    with pytest.raises(AnubisError, match="cannot guarantee data removal"):
        _lifecycle(tmp_path, runner).destroy()

    assert not any(command[0] == "helmfile" for command in runner.commands)


def test_given_deploy_command_when_product_is_converged_then_every_release_is_synced(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("anubis.kubernetes.shutil.which", lambda _tool: "/bin/tool")
    runner = LifecycleRunner()

    _lifecycle(tmp_path, runner).deploy()

    helmfile_commands = [command for command in runner.commands if command[0] == "helmfile"]
    assert len(helmfile_commands) == 2
    assert all("sync" in command for command in helmfile_commands)


def test_given_update_command_when_product_is_converged_then_only_changes_are_applied(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("anubis.kubernetes.shutil.which", lambda _tool: "/bin/tool")
    runner = LifecycleRunner()

    _lifecycle(tmp_path, runner).deploy(apply=True)

    helmfile_commands = [command for command in runner.commands if command[0] == "helmfile"]
    assert len(helmfile_commands) == 2
    assert all("apply" in command for command in helmfile_commands)

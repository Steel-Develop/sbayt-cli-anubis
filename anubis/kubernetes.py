"""Helmfile and Kubernetes product operations."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import yaml

from anubis.bitwarden import access_token
from anubis.config import get_path
from anubis.errors import AnubisError
from anubis.process import Runner
from anubis.repository import Installation, Repository


def kubeconfig_path(
    repository: Repository, installation: Installation, explicit: Path | None = None
) -> Path:
    if explicit:
        path = explicit.expanduser().resolve()
    elif installation.cluster_profile == "kind":
        cluster = installation.kube_context.removeprefix("kind-")
        path = repository.work / "kind" / cluster / "kubeconfig"
    else:
        path = repository.work / "rke2" / installation.kube_context / "kubeconfig"
    if not path.is_file():
        raise AnubisError(f"kubeconfig not found: {path}")
    return path


class Kubernetes:
    def __init__(
        self,
        repository: Repository,
        installation: Installation,
        manifest: Path,
        kubeconfig: Path,
        runner: Runner,
    ):
        self.repository = repository
        self.installation = installation
        self.manifest = manifest
        self.kubeconfig = kubeconfig
        self.runner = runner
        self.platform_helmfile = repository.root / "kubernetes/helmfile/platform.yaml.gotmpl"
        self.product_helmfile = repository.root / "kubernetes/helmfile/product.yaml.gotmpl"

    @property
    def environment(self) -> dict[str, str | None]:
        return {
            "SERQUET_REPOSITORY": str(self.repository.root),
            "SERQUET_INSTALLATION_FILE": str(self.manifest),
            "BWS_ACCESS_TOKEN": None,
        }

    def _require(self, *tools: str) -> None:
        missing = [tool for tool in tools if shutil.which(tool) is None]
        if missing:
            raise AnubisError(f"missing tools: {', '.join(missing)}")

    def _helmfile(
        self,
        state: Path,
        action: str,
        *,
        component: str | None = None,
        selector: str | None = None,
        state_values: dict[str, str] | None = None,
        arguments: list[str] | None = None,
        capture: bool = False,
    ):
        command = [
            "helmfile",
            "--kubeconfig",
            str(self.kubeconfig),
            "--file",
            str(state),
        ]
        if component:
            command.extend(["-l", f"component={component}"])
        if selector:
            command.extend(["-l", selector])
        for key, value in (state_values or {}).items():
            command.extend(["--state-values-set", f"{key}={value}"])
        command.append(action)
        if arguments:
            command.extend(arguments)
        return self.runner.run(
            command,
            cwd=self.repository.root,
            env=self.environment,
            capture=capture,
        )

    def _kubectl(
        self,
        arguments: list[str],
        *,
        capture: bool = False,
        check: bool = True,
        input_text: str | None = None,
        sensitive: bool = False,
    ):
        return self.runner.run(
            ["kubectl", "--kubeconfig", self.kubeconfig, *arguments],
            env={"BWS_ACCESS_TOKEN": None},
            capture=capture,
            check=check,
            input_text=input_text,
            sensitive=sensitive,
        )

    def product_namespace(self, *, required: bool = True) -> str | None:
        result = self._kubectl(
            [
                "get",
                "namespace",
                "-l",
                "serquet.io/scope=product",
                "-o",
                "jsonpath={.items[0].metadata.name}",
            ],
            capture=True,
        )
        namespace = result.stdout.strip()
        if not namespace and required:
            raise AnubisError("product namespace not found")
        return namespace or None

    def _scale_to_zero(self, namespace: str, resource: str, selector: str | None = None) -> None:
        arguments = ["-n", namespace, "get", resource]
        if selector:
            arguments.extend(["-l", selector])
        arguments.extend(["-o", "name"])
        names = self._kubectl(arguments, capture=True).stdout.splitlines()
        if names:
            self._kubectl(["-n", namespace, "scale", *names, "--replicas=0"])

    def stop(self) -> None:
        """Stop product processes while leaving stateful data services available."""
        self._require("kubectl")
        namespace = self.product_namespace()
        assert namespace is not None
        self._scale_to_zero(namespace, "deployment", selector="!strimzi.io/cluster")
        self._scale_to_zero(
            namespace,
            "statefulset",
            selector="app.kubernetes.io/component=edge",
        )
        self._kubectl(
            [
                "-n",
                namespace,
                "delete",
                "gateway.gateway.networking.k8s.io",
                "--all",
                "--ignore-not-found=true",
                "--wait=true",
            ]
        )

    def deploy(self, *, component: str | None = None, apply: bool = False) -> None:
        self._require("helm", "helmfile", "kubectl")
        action = "apply" if apply else "sync"
        if apply:
            plugins = self.runner.run(["helm", "plugin", "list"], capture=True)
            installed = {
                line.split()[0] for line in plugins.stdout.splitlines()[1:] if line.split()
            }
            if "diff" not in installed:
                raise AnubisError("update requires the helm-diff plugin")
        self._helmfile(self.platform_helmfile, action)
        self.bootstrap_bitwarden()
        self.validate_bootstrap_identities()
        arguments = None
        if component:
            arguments = ["--include-transitive-needs", "--enforce-needs-are-installed"]
        self._helmfile(
            self.product_helmfile,
            action,
            component=component,
            arguments=arguments,
        )

    def destroy(self) -> None:
        self._require("helmfile", "kubectl")
        namespace = self.product_namespace(required=False)
        volumes = self._persistent_volumes(namespace) if namespace else []
        self._helmfile(self.product_helmfile, "destroy")
        if namespace:
            self._kubectl(
                [
                    "delete",
                    "namespace",
                    namespace,
                    "--wait=true",
                    "--timeout=20m",
                ]
            )
            for volume in volumes:
                existing = self._kubectl(
                    ["get", "persistentvolume", volume, "-o", "name"],
                    capture=True,
                    check=False,
                )
                if existing.stdout.strip():
                    self._kubectl(
                        [
                            "wait",
                            "--for=delete",
                            f"persistentvolume/{volume}",
                            "--timeout=20m",
                        ]
                    )
        self._helmfile(self.platform_helmfile, "destroy")

    def _persistent_volumes(self, namespace: str) -> list[str]:
        claims = self._json_items(
            self._kubectl(
                ["-n", namespace, "get", "persistentvolumeclaim", "-o", "json"],
                capture=True,
            ).stdout,
            "persistent volume claims",
        )
        bound = {
            item.get("spec", {}).get("volumeName"): {
                "claim": item.get("metadata", {}).get("name", "unknown"),
                "storageClass": item.get("spec", {}).get("storageClassName", "unknown"),
            }
            for item in claims
            if item.get("spec", {}).get("volumeName")
        }
        if not bound:
            return []

        persistent_volumes = self._json_items(
            self._kubectl(["get", "persistentvolume", "-o", "json"], capture=True).stdout,
            "persistent volumes",
        )
        observed = {
            item.get("metadata", {}).get("name"): item
            for item in persistent_volumes
            if item.get("metadata", {}).get("name") in bound
        }
        missing = sorted(set(bound) - set(observed))
        if missing:
            raise AnubisError(
                "cannot verify persistent volumes before destroy: " + ", ".join(missing)
            )

        retained = []
        for volume, claim in bound.items():
            policy = observed[volume].get("spec", {}).get("persistentVolumeReclaimPolicy")
            if policy != "Delete":
                retained.append(
                    f"{claim['claim']} ({volume}, {claim['storageClass']}, {policy or 'unknown'})"
                )
        if retained:
            raise AnubisError(
                "destroy cannot guarantee data removal for PVCs backed by a non-Delete "
                "reclaim policy: " + ", ".join(retained)
            )
        return sorted(bound)

    @staticmethod
    def _json_items(payload: str, description: str) -> list[dict]:
        try:
            value = json.loads(payload)
            items = value["items"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise AnubisError(f"cannot read {description} from Kubernetes") from error
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise AnubisError(f"cannot read {description} from Kubernetes")
        return items

    def bootstrap_bitwarden(self) -> None:
        namespace = self.product_namespace()
        assert namespace is not None
        provider = self._kubectl(
            [
                "get",
                "namespace",
                namespace,
                "-o",
                "jsonpath={.metadata.labels.serquet\\.io/secret-provider}",
            ],
            capture=True,
        ).stdout.strip()
        if provider != "bitwarden-secrets-manager":
            return

        self._helmfile(
            self.product_helmfile,
            "template",
            component="secrets",
            arguments=["--skip-deps"],
            capture=True,
        )
        existing = (
            self._kubectl(
                [
                    "-n",
                    "external-secrets",
                    "get",
                    "secret",
                    "bitwarden-access-token",
                    "-o",
                    "jsonpath={.data.token}",
                ],
                capture=True,
                check=False,
            ).stdout.strip()
            != ""
        )
        token = os.environ.get("BWS_ACCESS_TOKEN", "").strip()
        if not token and existing:
            self._kubectl(
                [
                    "-n",
                    "external-secrets",
                    "label",
                    "secret",
                    "bitwarden-access-token",
                    "app.kubernetes.io/managed-by=anubis",
                    "--overwrite",
                ]
            )
            return
        if not token:
            token = access_token() or ""
        if not token:
            raise AnubisError("set BWS_ACCESS_TOKEN for the first deployment")

        secret = self._kubectl(
            [
                "-n",
                "external-secrets",
                "create",
                "secret",
                "generic",
                "bitwarden-access-token",
                "--from-file=token=/dev/stdin",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture=True,
            input_text=token,
            sensitive=True,
        )
        resource = yaml.safe_load(secret.stdout)
        metadata = resource.setdefault("metadata", {})
        metadata["labels"] = {
            "app.kubernetes.io/name": "bitwarden-access-token",
            "app.kubernetes.io/part-of": "serquet",
            "app.kubernetes.io/managed-by": "anubis",
            "serquet.io/scope": "platform",
        }
        self._kubectl(
            ["apply", "--server-side", "--field-manager=anubis", "-f", "-"],
            input_text=yaml.safe_dump(resource),
            sensitive=True,
        )

    def _manifest_values(self) -> dict:
        try:
            values = yaml.safe_load(self.manifest.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise AnubisError(f"cannot read resolved installation: {error}") from error
        if not isinstance(values, dict):
            raise AnubisError("resolved installation must be a YAML mapping")
        return values

    def validate_bootstrap_identities(self) -> None:
        """Reject owner changes that database operators cannot apply safely."""
        namespace = self.product_namespace()
        assert namespace is not None
        values = self._manifest_values()
        identities = [
            (
                "MongoDB",
                "mongodbcommunity/mongo",
                "{.spec.users[0].name}",
                "data.mongodb.username",
            ),
            (
                "TimescaleDB",
                "cluster/timescaledb",
                "{.spec.bootstrap.initdb.owner}",
                "data.timescaledb.username",
            ),
            (
                "Keycloak database",
                "cluster/keycloak-db",
                "{.spec.bootstrap.initdb.owner}",
                "identity.database.username",
            ),
        ]
        for label, resource, jsonpath, path in identities:
            expected = get_path(values, path)
            if not isinstance(expected, str) or not expected:
                continue
            result = self._kubectl(
                ["-n", namespace, "get", resource, "-o", f"jsonpath={jsonpath}"],
                capture=True,
                check=False,
            )
            current = result.stdout.strip()
            if result.returncode == 0 and current and current != expected:
                raise AnubisError(
                    f"{label} bootstrap username would change from {current!r} to "
                    f"{expected!r}; migrate the database manually before deploying"
                )

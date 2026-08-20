"""IaC repository and installation discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from anubis.config import load_repository_config
from anubis.errors import AnubisError


@dataclass(frozen=True)
class Installation:
    path: Path
    values: dict[str, Any]

    @property
    def name(self) -> str:
        value = self.values.get("name")
        if not isinstance(value, str) or not value:
            raise AnubisError(f"installation.name is required: {self.path}")
        return value

    @property
    def cluster_profile(self) -> str:
        value = self.values.get("clusterProfile")
        if not isinstance(value, str) or not value:
            raise AnubisError(f"installation.clusterProfile is required: {self.path}")
        return value

    @property
    def kube_context(self) -> str:
        value = self.values.get("kubeContext")
        if not isinstance(value, str) or not value:
            raise AnubisError(f"installation.kubeContext is required: {self.path}")
        return value

    @property
    def ask_become_pass(self) -> bool:
        provisioning = self.values.get("provisioning", {})
        if not isinstance(provisioning, dict):
            raise AnubisError(f"installation.provisioning must be a mapping: {self.path}")
        value = provisioning.get("askBecomePass", False)
        if not isinstance(value, bool):
            raise AnubisError(
                f"installation.provisioning.askBecomePass must be a boolean: {self.path}"
            )
        return value


@dataclass(frozen=True)
class Repository:
    root: Path
    config: dict[str, Any]

    @classmethod
    def discover(cls, explicit: Path | None = None, start: Path | None = None) -> Repository:
        if explicit:
            root = explicit.expanduser().resolve()
            if not root.is_dir():
                raise AnubisError(f"repository directory not found: {root}")
            return cls(root, load_repository_config(root))

        candidate = (start or Path.cwd()).resolve()
        for directory in (candidate, *candidate.parents):
            if (directory / "installations").is_dir() and (
                (directory / "helmfile.yaml.gotmpl").is_file()
                or (directory / "anubis.yaml").is_file()
            ):
                return cls(directory, load_repository_config(directory))
        raise AnubisError("IaC repository not found; pass --repository")

    @property
    def work(self) -> Path:
        return self.root / ".work"

    @property
    def active_installation_path(self) -> Path:
        return self.work / "anubis" / "active-installation"

    def select_installation(
        self,
        reference: str | Path | None,
        *,
        required: bool = True,
    ) -> Installation | None:
        """Resolve and remember an explicit installation, or reuse the active one."""
        if reference is not None:
            installation = self.installation(reference)
            self._write_active_installation(installation)
            return installation

        source = self.active_installation_path
        if not source.is_file():
            if required:
                raise AnubisError(
                    "installation is required; pass it once to select it for this repository"
                )
            return None
        try:
            active = source.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise AnubisError(f"cannot read active installation: {source}: {error}") from error
        if not active:
            raise AnubisError(
                f"active installation is empty: {source}; pass an installation explicitly"
            )
        try:
            return self.installation(active)
        except AnubisError as error:
            raise AnubisError(
                f"active installation is no longer valid: {active}; "
                "pass an installation explicitly"
            ) from error

    def _write_active_installation(self, installation: Installation) -> None:
        installations = self.root / "installations"
        try:
            reference = installation.path.parent.relative_to(installations).as_posix()
        except ValueError as error:
            raise AnubisError(
                f"installation must be inside {installations}: {installation.path}"
            ) from error
        destination = self.active_installation_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(f"{reference}\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, destination)

    def installation(self, reference: str | Path) -> Installation:
        requested = Path(reference).expanduser()
        candidates: list[Path] = []
        if requested.is_absolute():
            candidates.append(requested)
        else:
            candidates.extend(
                [
                    Path.cwd() / requested,
                    self.root / requested,
                    self.root / "installations" / requested,
                ]
            )

        for candidate in candidates:
            source = candidate / "installation.yaml" if candidate.is_dir() else candidate
            if source.is_file():
                return _load_installation(source.resolve())

        pattern = f"**/{requested.name}/installation.yaml"
        matches = list((self.root / "installations").glob(pattern))
        if len(matches) == 1:
            return _load_installation(matches[0].resolve())
        if len(matches) > 1:
            raise AnubisError(f"installation name is ambiguous: {reference}")
        raise AnubisError(f"installation not found: {reference}")


def _load_installation(path: Path) -> Installation:
    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise AnubisError(f"cannot read installation: {path}: {error}") from error
    if not isinstance(values, dict):
        raise AnubisError(f"installation must be a YAML mapping: {path}")
    return Installation(path=path, values=values)

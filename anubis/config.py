"""Optional user and repository configuration."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import tomli_w
import yaml

from anubis.errors import AnubisError


def config_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "anubis" / "config.toml"


def _mapping(value: object, source: Path) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AnubisError(f"configuration must be a mapping: {source}")
    return value


def load_global_config(path: Path | None = None) -> dict[str, Any]:
    source = path or config_path()
    if not source.is_file():
        return {}
    try:
        return _mapping(tomllib.loads(source.read_text(encoding="utf-8")), source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise AnubisError(f"cannot read configuration: {source}: {error}") from error


def write_global_config(values: Mapping[str, Any], path: Path | None = None) -> Path:
    destination = path or config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(tomli_w.dumps(dict(values)), encoding="utf-8")
    destination.chmod(0o600)
    return destination


def load_repository_config(repository: Path) -> dict[str, Any]:
    source = repository / "anubis.yaml"
    if not source.is_file():
        return {}
    try:
        return _mapping(yaml.safe_load(source.read_text(encoding="utf-8")), source)
    except (OSError, yaml.YAMLError) as error:
        raise AnubisError(f"cannot read repository configuration: {source}: {error}") from error


def merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def get_path(values: Mapping[str, Any], path: str, default: Any = None) -> Any:
    current: Any = values
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def set_path(values: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = values
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise AnubisError(f"cannot set {path}: {part} is not a mapping")
        current = child
    current[parts[-1]] = value

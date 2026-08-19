"""Shared CLI context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from anubis.config import load_global_config, merge
from anubis.errors import AnubisError
from anubis.process import Runner
from anubis.repository import Repository


@dataclass
class Application:
    repository_path: Path | None
    runner: Runner
    console: Console

    def repository(self) -> Repository:
        return Repository.discover(self.repository_path)

    def configuration(self) -> dict[str, Any]:
        global_values = load_global_config()
        try:
            repository_values = self.repository().config
        except AnubisError as error:
            if self.repository_path is not None or not str(error).startswith(
                "IaC repository not found"
            ):
                raise
            repository_values = {}
        return merge(global_values, repository_values)

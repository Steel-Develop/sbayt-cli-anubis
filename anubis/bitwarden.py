"""Bitwarden Secrets Manager integration."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import sys
from collections.abc import Mapping
from typing import Any

from anubis.errors import AnubisError
from anubis.process import Runner

_prompted_access_token: str | None = None


def access_token(*, prompt: bool = True) -> str | None:
    global _prompted_access_token
    token = os.environ.get("BWS_ACCESS_TOKEN", "").strip()
    if token:
        return token
    if _prompted_access_token:
        return _prompted_access_token
    if not prompt or not sys.stdin.isatty():
        return None
    value = getpass.getpass("Bitwarden machine access token: ").strip()
    _prompted_access_token = value or None
    return _prompted_access_token


class BitwardenClient:
    def __init__(self, runner: Runner, token: str):
        if not token:
            raise AnubisError("Bitwarden access token is empty")
        if shutil.which("bws") is None:
            raise AnubisError("bws is required; run 'anubis bitwarden install'")
        self.runner = runner
        self.token = token

    @property
    def environment(self) -> dict[str, str]:
        return {"BWS_ACCESS_TOKEN": self.token}

    def _json(self, arguments: list[str]) -> Any:
        result = self.runner.run(
            ["bws", *arguments, "--output", "json"],
            env=self.environment,
            capture=True,
            sensitive=True,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AnubisError("bws returned invalid JSON") from error

    def projects(self) -> list[dict[str, str]]:
        value = self._json(["list", "projects"])
        required = ("id", "organizationId", "name")
        if not isinstance(value, list) or any(
            not isinstance(project, dict)
            or not all(isinstance(project.get(field), str) for field in required)
            for project in value
        ):
            raise AnubisError("bws returned an unexpected project list")
        return value

    def secrets(self, project_id: str) -> dict[str, str]:
        value = self._json(["list", "secrets", project_id])
        if not isinstance(value, list):
            raise AnubisError("bws returned an unexpected secret list")
        resolved: dict[str, str] = {}
        duplicates: set[str] = set()
        for item in value:
            if not isinstance(item, Mapping):
                continue
            key = item.get("key")
            secret = item.get("value")
            if not isinstance(key, str) or not isinstance(secret, str):
                continue
            if key in resolved:
                duplicates.add(key)
            resolved[key] = secret
        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise AnubisError(f"duplicate Bitwarden keys in selected project: {names}")
        return resolved


def select_project(projects: list[dict[str, str]], selector: str | None = None) -> dict[str, str]:
    if not projects:
        raise AnubisError("the Bitwarden machine account has no accessible projects")
    if selector:
        matches = [project for project in projects if selector in (project["id"], project["name"])]
        if len(matches) != 1:
            raise AnubisError(f"Bitwarden project not found or ambiguous: {selector}")
        return matches[0]
    if len(projects) == 1:
        return projects[0]
    if not sys.stdin.isatty():
        raise AnubisError("multiple Bitwarden projects are accessible; pass --project")

    for index, project in enumerate(projects, start=1):
        print(f"  {index}. {project['name']}")
    while True:
        choice = input("Project number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(projects):
            return projects[int(choice) - 1]
        print(f"Choose a number from 1 to {len(projects)}.")

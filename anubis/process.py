"""Safe subprocess execution shared by all integrations."""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from rich.console import Console

from anubis.errors import AnubisError


class Runner:
    """Execute argument arrays without a shell or implicit secret logging."""

    def __init__(self, console: Console | None = None, *, verbose: bool = False):
        self.console = console or Console(stderr=True)
        self.verbose = verbose

    def run(
        self,
        arguments: Sequence[str | Path],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str | None] | None = None,
        input_text: str | None = None,
        capture: bool = False,
        check: bool = True,
        sensitive: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(argument) for argument in arguments]
        if not command:
            raise ValueError("command cannot be empty")
        if self.verbose:
            rendered = f"{command[0]} …" if sensitive else shlex.join(command)
            self.console.print(f"[dim]$ {rendered}[/dim]")

        process_env = os.environ.copy()
        if env:
            for key, value in env.items():
                if value is None:
                    process_env.pop(key, None)
                else:
                    process_env[key] = value

        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=process_env,
                input=input_text,
                text=True,
                capture_output=capture,
                check=False,
            )
        except OSError as error:
            raise AnubisError(f"cannot execute {command[0]}: {error}") from error
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            message = f"command failed ({result.returncode}): {command[0]}"
            if detail and not sensitive:
                message = f"{message}\n{detail}"
            raise AnubisError(message)
        return result

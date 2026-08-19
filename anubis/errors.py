"""Expected operator-facing errors."""

from __future__ import annotations

import click


class AnubisError(click.ClickException):
    """An expected error that should not produce a traceback."""

    exit_code = 2

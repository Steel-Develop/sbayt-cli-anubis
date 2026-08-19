"""Local installation of the external CLIs retained from Anubis legacy."""

from __future__ import annotations

import platform
import shutil
import tempfile
from pathlib import Path

from anubis.errors import AnubisError
from anubis.process import Runner

BWS_VERSION = "0.2.1"
LOCAL_BIN = Path.home() / ".local" / "bin"
AWS_INSTALLATION = Path.home() / ".local" / "aws-cli"


def install_bws(runner: Runner) -> None:
    if shutil.which("bws"):
        return
    architecture = {"x86_64": "x86_64", "aarch64": "aarch64"}.get(platform.machine())
    if architecture is None or platform.system() != "Linux":
        raise AnubisError("automatic bws installation supports Linux x86_64/aarch64")
    filename = f"bws-{architecture}-unknown-linux-gnu-{BWS_VERSION}.zip"
    url = f"https://github.com/bitwarden/sdk/releases/download/bws-v{BWS_VERSION}/{filename}"
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="anubis-bws-") as directory:
        archive = Path(directory) / filename
        runner.run(["curl", "-fsSL", "-o", archive, url])
        runner.run(["unzip", "-q", archive, "-d", LOCAL_BIN])
    (LOCAL_BIN / "bws").chmod(0o755)


def remove_bws() -> None:
    (LOCAL_BIN / "bws").unlink(missing_ok=True)


def install_aws(runner: Runner) -> None:
    if shutil.which("aws"):
        return
    architecture = {"x86_64": "x86_64", "aarch64": "aarch64"}.get(platform.machine())
    if architecture is None or platform.system() != "Linux":
        raise AnubisError("automatic AWS CLI installation supports Linux x86_64/aarch64")
    suffix = "" if architecture == "x86_64" else "-aarch64"
    url = f"https://awscli.amazonaws.com/awscli-exe-linux-{architecture}.zip"
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="anubis-aws-") as directory:
        root = Path(directory)
        archive = root / f"awscliv2{suffix}.zip"
        runner.run(["curl", "-fsSL", "-o", archive, url])
        runner.run(["unzip", "-q", archive, "-d", root])
        runner.run([root / "aws" / "install", "-i", AWS_INSTALLATION, "-b", LOCAL_BIN])


def remove_aws() -> None:
    (LOCAL_BIN / "aws").unlink(missing_ok=True)
    (LOCAL_BIN / "aws_completer").unlink(missing_ok=True)
    if AWS_INSTALLATION.exists():
        shutil.rmtree(AWS_INSTALLATION)

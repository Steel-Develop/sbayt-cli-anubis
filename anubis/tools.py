"""User-local toolchain management for Anubis workflows."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from anubis.errors import AnubisError
from anubis.process import Runner

DEFAULT_TOOLCHAIN = {
    "helm": "4.2.0",
    "helmfile": "1.7.1",
    "kubectl": "1.35.0",
    "kind": "0.31.0",
    "terraform": "1.13.5",
    "helm-diff": "3.15.10",
}
BWS_VERSION = "1.0.0"
UV_INSTALL_VERSION = "0.11.29"
UV_MINIMUM_VERSION = (0, 11, 0)
LOCAL_BIN = Path.home() / ".local" / "bin"
AWS_INSTALLATION = Path.home() / ".local" / "aws-cli"


@dataclass(frozen=True)
class ToolRelease:
    name: str
    version: str
    url: str
    checksum_url: str
    filename: str
    archive: str = "raw"
    member: str | None = None


@dataclass(frozen=True)
class ToolStatus:
    name: str
    expected: str
    path: Path | None
    version: str | None
    ready: bool


def project_toolchain(configuration: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Merge optional repository pins with Anubis' supported defaults."""
    values = dict(DEFAULT_TOOLCHAIN)
    configured = (configuration or {}).get("toolchain", {})
    if configured is None:
        return values
    if not isinstance(configured, Mapping):
        raise AnubisError("anubis.yaml toolchain must be a mapping")
    if any(not isinstance(name, str) for name in configured):
        raise AnubisError("anubis.yaml toolchain keys must be tool names")
    unknown = sorted(set(configured) - set(DEFAULT_TOOLCHAIN))
    if unknown:
        raise AnubisError(f"unknown anubis.yaml toolchain entries: {', '.join(unknown)}")
    for name, version in configured.items():
        if not isinstance(version, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", version):
            raise AnubisError(f"anubis.yaml toolchain.{name} must use x.y.z")
        values[name] = version.removeprefix("v")
    return values


def _linux_architecture() -> str:
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if architecture is None or platform.system() != "Linux":
        raise AnubisError("automatic tool installation supports Linux x86_64/aarch64")
    return architecture


def _release(name: str, version: str, architecture: str) -> ToolRelease:
    if name == "helm":
        filename = f"helm-v{version}-linux-{architecture}.tar.gz"
        return ToolRelease(
            name,
            version,
            f"https://get.helm.sh/{filename}",
            f"https://get.helm.sh/{filename}.sha256sum",
            filename,
            "tar",
            f"linux-{architecture}/helm",
        )
    if name == "helmfile":
        filename = f"helmfile_{version}_linux_{architecture}.tar.gz"
        base = f"https://github.com/helmfile/helmfile/releases/download/v{version}"
        return ToolRelease(
            name,
            version,
            f"{base}/{filename}",
            f"{base}/helmfile_{version}_checksums.txt",
            filename,
            "tar",
            "helmfile",
        )
    if name == "kubectl":
        filename = "kubectl"
        base = f"https://dl.k8s.io/release/v{version}/bin/linux/{architecture}"
        return ToolRelease(
            name, version, f"{base}/{filename}", f"{base}/{filename}.sha256", filename
        )
    if name == "kind":
        filename = f"kind-linux-{architecture}"
        base = f"https://kind.sigs.k8s.io/dl/v{version}"
        return ToolRelease(
            name, version, f"{base}/{filename}", f"{base}/{filename}.sha256sum", filename
        )
    if name == "terraform":
        filename = f"terraform_{version}_linux_{architecture}.zip"
        base = f"https://releases.hashicorp.com/terraform/{version}"
        return ToolRelease(
            name,
            version,
            f"{base}/{filename}",
            f"{base}/terraform_{version}_SHA256SUMS",
            filename,
            "zip",
            "terraform",
        )
    if name == "uv":
        target = {
            "amd64": "x86_64-unknown-linux-gnu",
            "arm64": "aarch64-unknown-linux-gnu",
        }[architecture]
        filename = f"uv-{target}.tar.gz"
        base = f"https://github.com/astral-sh/uv/releases/download/{version}"
        return ToolRelease(
            name,
            version,
            f"{base}/{filename}",
            f"{base}/{filename}.sha256",
            filename,
            "tar",
            f"uv-{target}/uv",
        )
    if name == "bws":
        target = {
            "amd64": "x86_64-unknown-linux-gnu",
            "arm64": "aarch64-unknown-linux-gnu",
        }[architecture]
        filename = f"bws-{target}-{version}.zip"
        base = f"https://github.com/bitwarden/sdk-sm/releases/download/bws-v{version}"
        return ToolRelease(
            name,
            version,
            f"{base}/{filename}",
            f"{base}/bws-sha256-checksums-{version}.txt",
            filename,
            "zip",
            "bws",
        )
    raise AnubisError(f"unsupported managed tool: {name}")


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "anubis-cli"})
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            destination.open("wb") as stream,
        ):
            shutil.copyfileobj(response, stream)
    except (OSError, urllib.error.URLError) as error:
        raise AnubisError(f"cannot download {url}: {error}") from error


def file_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_checksum(source: Path, filename: str) -> str:
    for line in source.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) == 1 and re.fullmatch(r"[0-9a-fA-F]{64}", fields[0]):
            return fields[0].lower()
        if (
            len(fields) >= 2
            and PurePosixPath(fields[-1].lstrip("*")).name == filename
            and re.fullmatch(r"[0-9a-fA-F]{64}", fields[0])
        ):
            return fields[0].lower()
    raise AnubisError(f"published checksum does not contain {filename}")


def _verify(source: Path, expected: str, name: str) -> None:
    if file_sha256(source) != expected:
        raise AnubisError(f"downloaded {name} checksum does not match")


def download_verified(url: str, destination: Path, expected: str, name: str) -> None:
    """Download a catalog-pinned file and replace the destination atomically."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}-", dir=destination.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        _download(url, temporary)
        _verify(temporary, expected, name)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _publish(source: Path, name: str) -> None:
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}-", dir=LOCAL_BIN)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination, source.open("rb") as current:
            shutil.copyfileobj(current, destination)
        temporary.chmod(0o755)
        os.replace(temporary, LOCAL_BIN / name)
    finally:
        temporary.unlink(missing_ok=True)


def _extract(release: ToolRelease, source: Path, destination: Path) -> None:
    try:
        if release.archive == "tar":
            with tarfile.open(source, "r:gz") as bundle:
                member = bundle.extractfile(release.member or release.name)
                if member is None:
                    raise KeyError(release.member)
                with destination.open("wb") as stream:
                    shutil.copyfileobj(member, stream)
        elif release.archive == "zip":
            with (
                zipfile.ZipFile(source) as bundle,
                bundle.open(release.member or release.name) as member,
                destination.open("wb") as stream,
            ):
                shutil.copyfileobj(member, stream)
        else:
            shutil.copyfile(source, destination)
    except (KeyError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise AnubisError(f"cannot extract {release.name} from downloaded archive") from error


def _install_release(release: ToolRelease) -> None:
    with tempfile.TemporaryDirectory(prefix=f"anubis-{release.name}-") as directory:
        root = Path(directory)
        source = root / release.filename
        checksums = root / "checksums"
        _download(release.url, source)
        _download(release.checksum_url, checksums)
        _verify(source, _expected_checksum(checksums, release.filename), release.name)
        binary = (
            source
            if release.archive == "raw" and source.name == release.name
            else root / release.name
        )
        if binary != source:
            _extract(release, source, binary)
        _publish(binary, release.name)


def _prepend_local_bin() -> None:
    search_path = [
        entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry != str(LOCAL_BIN)
    ]
    os.environ["PATH"] = os.pathsep.join([str(LOCAL_BIN), *search_path])


def _version_command(name: str) -> list[str]:
    return {
        "helm": ["helm", "version", "--short"],
        "helmfile": ["helmfile", "version", "-o", "short"],
        "kubectl": ["kubectl", "version", "--client", "-o", "json"],
        "kind": ["kind", "version"],
        "terraform": ["terraform", "version", "-json"],
        "uv": ["uv", "--version"],
        "bws": ["bws", "--version"],
        "aws": ["aws", "--version"],
    }[name]


def tool_version(name: str, runner: Runner) -> tuple[str | None, Path | None]:
    """Return the executable's semantic version without changing local state."""
    _prepend_local_bin()
    executable = shutil.which(name)
    if executable is None:
        return None, None
    result = runner.run(_version_command(name), capture=True, check=False)
    if result.returncode != 0:
        return None, Path(executable)
    output = f"{result.stdout}\n{result.stderr}"
    if name == "kubectl":
        try:
            value = json.loads(result.stdout)["clientVersion"]["gitVersion"]
        except (KeyError, TypeError, json.JSONDecodeError):
            return None, Path(executable)
        return str(value).removeprefix("v"), Path(executable)
    if name == "terraform":
        try:
            value = json.loads(result.stdout)["terraform_version"]
        except (KeyError, TypeError, json.JSONDecodeError):
            return None, Path(executable)
        return str(value).removeprefix("v"), Path(executable)
    patterns = {
        "helm": r"v?(\d+\.\d+\.\d+)",
        "helmfile": r"v?(\d+\.\d+\.\d+)",
        "kind": r"v?(\d+\.\d+\.\d+)",
        "uv": r"uv\s+v?(\d+\.\d+\.\d+)",
        "bws": r"(?:bws\s+)?v?(\d+\.\d+\.\d+)",
        "aws": r"aws-cli/(\d+\.\d+\.\d+)",
    }
    match = re.search(patterns[name], output)
    return (match.group(1) if match else None), Path(executable)


def inspect_exact_tool(name: str, version: str, runner: Runner) -> ToolStatus:
    found, path = tool_version(name, runner)
    return ToolStatus(name, version, path, found, found == version)


def ensure_project_tools(
    runner: Runner,
    configuration: Mapping[str, Any] | None,
    *names: str,
) -> None:
    versions = project_toolchain(configuration)
    for name in names:
        if name == "helm-diff":
            raise AnubisError("helm-diff must be prepared with ensure_helm_diff")
        expected = versions[name]
        status = inspect_exact_tool(name, expected, runner)
        if status.ready:
            continue
        runner.console.print(f"Installing {name} {expected}")
        _install_release(_release(name, expected, _linux_architecture()))
        installed = inspect_exact_tool(name, expected, runner)
        if not installed.ready:
            raise AnubisError(f"installed {name} does not report version {expected}")


def _helm_diff_version(runner: Runner) -> str | None:
    if shutil.which("helm") is None:
        return None
    result = runner.run(["helm", "plugin", "list"], capture=True, check=False)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if fields and fields[0] == "diff" and len(fields) > 1:
            match = re.search(r"v?(\d+\.\d+\.\d+)", fields[1])
            return match.group(1) if match else None
    return None


def inspect_helm_diff(configuration: Mapping[str, Any] | None, runner: Runner) -> ToolStatus:
    expected = project_toolchain(configuration)["helm-diff"]
    found = _helm_diff_version(runner)
    helm = shutil.which("helm")
    return ToolStatus(
        "helm-diff", expected, Path(helm) if helm else None, found, found == expected
    )


def ensure_helm_diff(runner: Runner, configuration: Mapping[str, Any] | None = None) -> None:
    expected = project_toolchain(configuration)["helm-diff"]
    current = _helm_diff_version(runner)
    if current == expected:
        return
    if current is not None:
        runner.run(["helm", "plugin", "uninstall", "diff"])
    runner.console.print(f"Installing helm-diff {expected}")
    command = [
        "helm",
        "plugin",
        "install",
        "https://github.com/databus23/helm-diff",
        "--version",
        f"v{expected}",
    ]
    helm_version, _ = tool_version("helm", runner)
    if helm_version and helm_version.split(".", 1)[0] == "4":
        command.append("--verify=false")
    runner.run(command)
    if _helm_diff_version(runner) != expected:
        raise AnubisError(f"installed helm-diff does not report version {expected}")


def ensure_uv(runner: Runner) -> None:
    version, _ = tool_version("uv", runner)
    if version and version_tuple(version) >= UV_MINIMUM_VERSION:
        return
    runner.console.print(f"Installing uv {UV_INSTALL_VERSION}")
    _install_release(_release("uv", UV_INSTALL_VERSION, _linux_architecture()))
    installed, _ = tool_version("uv", runner)
    if installed is None or version_tuple(installed) < UV_MINIMUM_VERSION:
        raise AnubisError("installed uv does not satisfy >=0.11")


def version_tuple(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


def install_bws(runner: Runner) -> None:
    status = inspect_exact_tool("bws", BWS_VERSION, runner)
    if status.ready:
        return
    runner.console.print(f"Installing bws {BWS_VERSION}")
    _install_release(_release("bws", BWS_VERSION, _linux_architecture()))
    if not inspect_exact_tool("bws", BWS_VERSION, runner).ready:
        raise AnubisError(f"installed bws does not report version {BWS_VERSION}")


def remove_bws() -> None:
    (LOCAL_BIN / "bws").unlink(missing_ok=True)


def _safe_extract_zip(source: Path, destination: Path) -> None:
    root = destination.resolve()
    try:
        with zipfile.ZipFile(source) as bundle:
            for member in bundle.infolist():
                target = (destination / member.filename).resolve()
                if root not in target.parents and target != root:
                    raise AnubisError("downloaded archive contains an unsafe path")
            bundle.extractall(destination)
    except (OSError, zipfile.BadZipFile) as error:
        raise AnubisError("cannot extract downloaded AWS CLI archive") from error


def install_aws(runner: Runner) -> None:
    version, _ = tool_version("aws", runner)
    if version and version_tuple(version)[0] == 2:
        return
    architecture = _linux_architecture()
    aws_architecture = "x86_64" if architecture == "amd64" else "aarch64"
    url = f"https://awscli.amazonaws.com/awscli-exe-linux-{aws_architecture}.zip"
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="anubis-aws-") as directory:
        root = Path(directory)
        archive = root / "awscliv2.zip"
        _download(url, archive)
        _safe_extract_zip(archive, root)
        command = [root / "aws" / "install", "-i", AWS_INSTALLATION, "-b", LOCAL_BIN]
        if AWS_INSTALLATION.exists():
            command.append("--update")
        runner.run(command)
    installed, _ = tool_version("aws", runner)
    if installed is None or version_tuple(installed)[0] != 2:
        raise AnubisError("installed AWS CLI is not version 2")


def remove_aws() -> None:
    (LOCAL_BIN / "aws").unlink(missing_ok=True)
    (LOCAL_BIN / "aws_completer").unlink(missing_ok=True)
    if AWS_INSTALLATION.exists():
        shutil.rmtree(AWS_INSTALLATION)

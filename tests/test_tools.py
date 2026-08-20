import hashlib
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from anubis import tools
from anubis.errors import AnubisError


class ToolRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    class Console:
        def print(self, _message: str) -> None:
            pass

    console = Console()

    def run(
        self,
        arguments: list[str],
        *,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(argument) for argument in arguments]
        self.commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")


def test_given_optional_toolchain_when_resolved_then_defaults_and_overrides_are_merged() -> None:
    result = tools.project_toolchain({"toolchain": {"helm": "9.8.7"}})

    assert result["helm"] == "9.8.7"
    assert result["kubectl"] == tools.DEFAULT_TOOLCHAIN["kubectl"]


def test_given_unknown_toolchain_entry_when_resolved_then_configuration_is_rejected() -> None:
    with pytest.raises(AnubisError, match="unknown.*entries"):
        tools.project_toolchain({"toolchain": {"unknown": "1.0.0"}})


def test_given_invalid_toolchain_version_when_resolved_then_configuration_is_rejected() -> None:
    with pytest.raises(AnubisError, match="x.y.z"):
        tools.project_toolchain({"toolchain": {"helm": "latest"}})


def test_given_wrong_tool_version_when_ensured_then_declared_release_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter(
        [
            tools.ToolStatus("helm", "4.2.0", Path("/usr/bin/helm"), "3.0.0", False),
            tools.ToolStatus("helm", "4.2.0", tools.LOCAL_BIN / "helm", "4.2.0", True),
        ]
    )
    installed: list[tools.ToolRelease] = []
    monkeypatch.setattr(tools, "inspect_exact_tool", lambda *_args: next(states))
    monkeypatch.setattr(tools, "_linux_architecture", lambda: "amd64")
    monkeypatch.setattr(tools, "_install_release", installed.append)

    tools.ensure_project_tools(ToolRunner(), None, "helm")  # type: ignore[arg-type]

    assert [(release.name, release.version) for release in installed] == [("helm", "4.2.0")]


def test_given_corrupt_tool_download_when_verified_then_installation_is_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tool"
    source.write_bytes(b"unexpected")

    with pytest.raises(AnubisError, match="checksum does not match"):
        tools._verify(source, "invalid", "tool")


def test_given_valid_tool_archive_when_installed_then_binary_is_published_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binary = tmp_path / "helm"
    binary.write_bytes(b"executable")
    archive = tmp_path / "helm.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(binary, arcname="linux-amd64/helm")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum_file = tmp_path / "checksums"
    checksum_file.write_text(f"{checksum}  helm.tar.gz\n", encoding="utf-8")
    destination = tmp_path / "bin"
    monkeypatch.setattr(tools, "LOCAL_BIN", destination)

    def download(url: str, target: Path) -> None:
        shutil.copyfile(checksum_file if url.endswith("checksums") else archive, target)

    monkeypatch.setattr(tools, "_download", download)
    release = tools.ToolRelease(
        "helm",
        "1.0.0",
        "https://example.com/helm.tar.gz",
        "https://example.com/checksums",
        "helm.tar.gz",
        "tar",
        "linux-amd64/helm",
    )

    tools._install_release(release)

    assert (destination / "helm").read_bytes() == b"executable"
    assert (destination / "helm").stat().st_mode & 0o111


def test_given_direct_binary_when_installed_then_it_is_published_without_copying_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "kubectl"
    source.write_bytes(b"executable")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    checksum_file = tmp_path / "checksum"
    checksum_file.write_text(checksum, encoding="utf-8")
    destination = tmp_path / "bin"
    monkeypatch.setattr(tools, "LOCAL_BIN", destination)

    def download(url: str, target: Path) -> None:
        shutil.copyfile(checksum_file if url.endswith("sha256") else source, target)

    monkeypatch.setattr(tools, "_download", download)
    release = tools.ToolRelease(
        "kubectl",
        "1.35.0",
        "https://example.com/kubectl",
        "https://example.com/kubectl.sha256",
        "kubectl",
    )

    tools._install_release(release)

    assert (destination / "kubectl").read_bytes() == b"executable"


def test_given_missing_diff_plugin_when_ensured_then_helm_four_compatible_plugin_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = ToolRunner()
    versions = iter([None, "3.15.10"])
    monkeypatch.setattr(tools, "_helm_diff_version", lambda _runner: next(versions))
    monkeypatch.setattr(tools, "tool_version", lambda *_args: ("4.2.0", Path("/bin/helm")))

    tools.ensure_helm_diff(runner)  # type: ignore[arg-type]

    assert runner.commands[-1] == [
        "helm",
        "plugin",
        "install",
        "https://github.com/databus23/helm-diff",
        "--version",
        "v3.15.10",
        "--verify=false",
    ]


def test_given_newer_compatible_uv_when_ensured_then_it_is_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tools, "tool_version", lambda *_args: ("0.12.5", Path("/bin/uv")))
    monkeypatch.setattr(
        tools,
        "_install_release",
        lambda _release: pytest.fail("compatible uv should not be reinstalled"),
    )

    tools.ensure_uv(ToolRunner())  # type: ignore[arg-type]

from pathlib import Path

import pytest
from rich.console import Console

from anubis.application import Application
from anubis.commands.cluster import prepare_cluster
from anubis.process import Runner
from anubis.repository import Installation


@pytest.mark.parametrize(
    ("configured", "override", "expected"),
    [
        (True, None, True),
        (False, True, True),
        (True, False, False),
    ],
)
def test_given_become_configuration_when_cluster_is_prepared_then_cli_override_has_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured: bool,
    override: bool | None,
    expected: bool,
) -> None:
    received: dict[str, bool] = {}

    def capture_rke2(*_args: object, **kwargs: object) -> None:
        received["ask_become_pass"] = bool(kwargs["ask_become_pass"])

    monkeypatch.setattr("anubis.commands.cluster.rke2", capture_rke2)
    installation = Installation(
        tmp_path / "installation.yaml",
        {
            "name": "cpd",
            "clusterProfile": "rke2-single-node",
            "kubeContext": "serquet-cpd",
            "provisioning": {"askBecomePass": configured},
        },
    )
    application = Application(tmp_path, Runner(), Console())

    prepare_cluster(application, installation, ask_become_pass=override)

    assert received["ask_become_pass"] is expected

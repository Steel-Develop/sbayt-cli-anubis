from pathlib import Path

import yaml

from anubis.config import load_repository_config, merge
from anubis.repository import Repository


def test_given_repository_without_config_when_discovered_then_config_is_optional(
    tmp_path: Path,
) -> None:
    (tmp_path / "installations" / "internal" / "local").mkdir(parents=True)
    (tmp_path / "helmfile.yaml.gotmpl").touch()
    installation = tmp_path / "installations" / "internal" / "local" / "installation.yaml"
    installation.write_text(
        yaml.safe_dump(
            {
                "name": "local",
                "clusterProfile": "kind",
                "productProfile": "full",
                "kubeContext": "kind-local",
            }
        ),
        encoding="utf-8",
    )

    repository = Repository.discover(tmp_path)

    assert repository.config == {}
    assert repository.installation("local").path == installation


def test_given_repository_and_global_config_when_merged_then_repository_values_override_global(
    tmp_path: Path,
) -> None:
    (tmp_path / "anubis.yaml").write_text("aws:\n  region: eu-west-1\n", encoding="utf-8")

    values = merge(
        {"aws": {"region": "eu-central-1", "accountID": "example"}},
        load_repository_config(tmp_path),
    )

    assert values == {"aws": {"region": "eu-west-1", "accountID": "example"}}

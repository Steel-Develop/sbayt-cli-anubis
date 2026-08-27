import json
from pathlib import Path

import pytest
import yaml

from anubis.errors import AnubisError
from anubis.repository import Repository


def _installation(root: Path, reference: str, name: str) -> Path:
    destination = root / "installations" / reference / "installation.yaml"
    destination.parent.mkdir(parents=True)
    destination.write_text(
        yaml.safe_dump(
            {
                "name": name,
                "clusterProfile": "kind",
                "kubeContext": f"kind-{name}",
            }
        ),
        encoding="utf-8",
    )
    return destination


def _schema(root: Path, schema: dict) -> Path:
    destination = root / "installations" / "schema.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(schema), encoding="utf-8")
    return destination


def test_given_explicit_installation_when_selected_then_it_becomes_active(
    tmp_path: Path,
) -> None:
    local = _installation(tmp_path, "internal/local", "local")
    repository = Repository(tmp_path, {})

    selected = repository.select_installation("internal/local")

    assert selected is not None
    assert selected.path == local
    assert repository.active_installation_path.read_text(encoding="utf-8") == "internal/local\n"
    assert repository.select_installation(None) == selected


def test_given_active_installation_when_another_is_selected_then_new_one_becomes_active(
    tmp_path: Path,
) -> None:
    _installation(tmp_path, "internal/local", "local")
    cpd = _installation(tmp_path, "internal/cpd", "cpd")
    repository = Repository(tmp_path, {})
    repository.select_installation("internal/local")

    selected = repository.select_installation("internal/cpd")

    assert selected is not None
    assert selected.path == cpd
    assert repository.select_installation(None) == selected


def test_given_no_active_installation_when_selected_implicitly_then_reference_is_required(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path, {})

    with pytest.raises(AnubisError, match="pass it once"):
        repository.select_installation(None)

    assert repository.select_installation(None, required=False) is None


def test_given_stale_active_installation_when_selected_then_replacement_is_required(
    tmp_path: Path,
) -> None:
    repository = Repository(tmp_path, {})
    repository.active_installation_path.parent.mkdir(parents=True)
    repository.active_installation_path.write_text("internal/missing\n", encoding="utf-8")

    with pytest.raises(AnubisError, match="no longer valid"):
        repository.select_installation(None)


def test_given_no_provisioning_setting_when_read_then_become_prompt_defaults_to_false(
    tmp_path: Path,
) -> None:
    source = _installation(tmp_path, "internal/local", "local")

    installation = Repository(tmp_path, {}).installation(source)

    assert installation.ask_become_pass is False


def test_given_boolean_provisioning_setting_when_read_then_become_prompt_is_returned(
    tmp_path: Path,
) -> None:
    source = _installation(tmp_path, "internal/cpd", "cpd")
    values = yaml.safe_load(source.read_text(encoding="utf-8"))
    values["provisioning"] = {"askBecomePass": True}
    source.write_text(yaml.safe_dump(values), encoding="utf-8")

    installation = Repository(tmp_path, {}).installation(source)

    assert installation.ask_become_pass is True


def test_given_invalid_provisioning_setting_when_read_then_configuration_is_rejected(
    tmp_path: Path,
) -> None:
    source = _installation(tmp_path, "internal/cpd", "cpd")
    values = yaml.safe_load(source.read_text(encoding="utf-8"))
    values["provisioning"] = {"askBecomePass": "yes"}
    source.write_text(yaml.safe_dump(values), encoding="utf-8")
    installation = Repository(tmp_path, {}).installation(source)

    with pytest.raises(AnubisError, match="askBecomePass must be a boolean"):
        _ = installation.ask_become_pass


def test_given_repository_schema_and_valid_manifest_when_loaded_then_it_is_accepted(
    tmp_path: Path,
) -> None:
    source = _installation(tmp_path, "internal/local", "local")
    _schema(
        tmp_path,
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"const": "local"}},
        },
    )

    installation = Repository(tmp_path, {}).installation(source)

    assert installation.name == "local"


def test_given_repository_schema_and_invalid_manifest_when_loaded_then_path_is_reported(
    tmp_path: Path,
) -> None:
    source = _installation(tmp_path, "internal/local", "local")
    _schema(
        tmp_path,
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "capacity": {
                    "type": "object",
                    "properties": {"compute": {"type": "object"}},
                    "required": ["compute"],
                }
            },
            "required": ["capacity"],
        },
    )

    with pytest.raises(AnubisError, match=r"<root>: 'capacity' is a required property"):
        Repository(tmp_path, {}).installation(source)


def test_given_malformed_repository_schema_when_loaded_then_it_is_rejected(
    tmp_path: Path,
) -> None:
    source = _installation(tmp_path, "internal/local", "local")
    schema = tmp_path / "installations" / "schema.json"
    schema.write_text("{", encoding="utf-8")

    with pytest.raises(AnubisError, match="cannot read installation schema"):
        Repository(tmp_path, {}).installation(source)


def test_given_invalid_repository_schema_when_loaded_then_it_is_rejected(
    tmp_path: Path,
) -> None:
    source = _installation(tmp_path, "internal/local", "local")
    _schema(tmp_path, {"type": 123})

    with pytest.raises(AnubisError, match="invalid installation schema"):
        Repository(tmp_path, {}).installation(source)


def test_given_repository_without_schema_when_loaded_then_behavior_is_unchanged(
    tmp_path: Path,
) -> None:
    source = _installation(tmp_path, "internal/local", "local")
    values = yaml.safe_load(source.read_text(encoding="utf-8"))
    values["repositorySpecificOption"] = True
    source.write_text(yaml.safe_dump(values), encoding="utf-8")

    installation = Repository(tmp_path, {}).installation(source)

    assert installation.values["repositorySpecificOption"] is True

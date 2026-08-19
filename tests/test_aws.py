from pathlib import Path

from anubis import aws
from anubis.aws import AwsSettings, configure_uv, shell_export


def test_given_arbitrary_token_when_shell_export_is_built_then_value_is_quoted() -> None:
    assert shell_export("TOKEN", "value'with space") == ("export TOKEN='value'\"'\"'with space'")


def test_given_existing_uv_config_when_configured_then_file_is_replaced(
    tmp_path: Path,
    monkeypatch,
) -> None:
    destination = tmp_path / "uv.toml"
    destination.write_text('[[index]]\nurl = "https://old.example/simple"\n', encoding="utf-8")
    destination.chmod(0o664)
    monkeypatch.setattr(aws, "UV_CONFIG", destination)
    monkeypatch.setattr(aws.shutil, "which", lambda _executable: "/usr/bin/uv")
    monkeypatch.setattr(aws, "codeartifact_token", lambda *_args, **_kwargs: "new-token")

    configure_uv(
        object(),
        AwsSettings(
            region="eu-west-1",
            account_id="123456789012",
            domain="example",
            repository="python",
        ),
    )

    content = destination.read_text(encoding="utf-8")
    assert content.startswith(aws.UV_MARKER)
    assert "new-token" in content
    assert "old.example" not in content
    assert destination.stat().st_mode & 0o777 == 0o600

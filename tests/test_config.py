import textwrap
from pathlib import Path

import pytest

from manga_scanlation.config import ConfigError, load


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def test_minimal_config_uses_defaults(tmp_path):
    cfg_path = write(tmp_path / "config.yaml", """
        engine:
          type: passthrough
        source:
          type: local
    """)
    config = load(cfg_path)
    # Relative defaults are resolved against the config file's directory.
    assert config.paths.data == (tmp_path / "data").resolve()
    assert config.paths.source == (tmp_path / "data" / "source").resolve()
    assert config.paths.state == (tmp_path / "data" / "state.json").resolve()
    assert config.engine_type == "passthrough"
    assert config.translation.translator == "openai"
    assert config.translation.target_lang == "CHS"
    assert config.batch.limit == 0
    assert config.batch.fail_fast is False


def test_absolute_paths_and_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("MSCAN_TEST_ROOT", str(tmp_path / "elsewhere"))
    absolute_inbox = tmp_path / "absolute-inbox"
    cfg_path = write(tmp_path / "config.yaml", f"""
        engine:
          type: passthrough
        paths:
          data: $MSCAN_TEST_ROOT/data
          inbox: {absolute_inbox.as_posix()}
    """)
    config = load(cfg_path)
    assert config.paths.data == (tmp_path / "elsewhere" / "data")
    assert config.paths.inbox == absolute_inbox


def test_missing_config_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        load(tmp_path / "nope.yaml")


def test_unknown_source_type_is_rejected(tmp_path):
    cfg_path = write(tmp_path / "config.yaml", """
        engine:
          type: passthrough
        source:
          type: ftp
    """)
    with pytest.raises(ConfigError, match="source.type"):
        load(cfg_path)


def test_bad_format_is_rejected(tmp_path):
    cfg_path = write(tmp_path / "config.yaml", """
        engine:
          type: mit
          mit:
            format: gif
    """)
    with pytest.raises(ConfigError, match="format"):
        load(cfg_path)


def test_missing_engine_python_is_reported(tmp_path):
    cfg_path = write(tmp_path / "config.yaml", """
        engine:
          type: mit
          mit:
            root: ./vendor/manga-image-translator
            python: ./missing/python
            base_config: ./config/mit-config.json
    """)
    with pytest.raises(ConfigError) as excinfo:
        load(cfg_path)
    message = str(excinfo.value)
    assert "engine.mit.python" in message
    assert "engine.mit.root" in message


def test_batch_values_are_validated(tmp_path):
    cfg_path = write(tmp_path / "config.yaml", """
        engine:
          type: passthrough
        batch:
          retries: -1
    """)
    with pytest.raises(ConfigError, match="batch.retries"):
        load(cfg_path)


def test_documented_shipped_example_parses():
    """config.example.yaml must stay loadable as a template."""
    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / "config.example.yaml"
    import yaml

    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert data["engine"]["type"] == "mit"
    assert data["source"]["type"] in {"local", "gallerydl"}
    assert "translation" in data

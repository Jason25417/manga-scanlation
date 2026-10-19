"""Translation engines.

The only engine that does real work is a thin, explicit wrapper around
`manga-image-translator`: we generate its config files from ours, build the
command line, and stream its output. Nothing about a particular model, API
vendor or gallery is baked in here.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import Config, MITConfig
from .util import Console, stream_command

# Environment variables each manga-image-translator backend reads (see its
# translators/keys.py). Used to translate our config fields into env vars so a
# user does not have to export anything by hand.
BACKEND_ENV: dict[str, dict[str, str | None]] = {
    "openai": {"key": "OPENAI_API_KEY", "model": "OPENAI_MODEL", "base": "OPENAI_API_BASE"},
    "custom_openai": {
        "key": "CUSTOM_OPENAI_API_KEY",
        "model": "CUSTOM_OPENAI_MODEL",
        "base": "CUSTOM_OPENAI_API_BASE",
    },
    "ollama": {
        "key": "CUSTOM_OPENAI_API_KEY",
        "model": "CUSTOM_OPENAI_MODEL",
        "base": "CUSTOM_OPENAI_API_BASE",
    },
    "deepseek": {"key": "DEEPSEEK_API_KEY", "model": "DEEPSEEK_MODEL", "base": "DEEPSEEK_API_BASE"},
    "gemini": {"key": "GEMINI_API_KEY", "model": "GEMINI_MODEL", "base": None},
    "groq": {"key": "GROQ_API_KEY", "model": "GROQ_MODEL", "base": None},
    "sakura": {"key": None, "model": None, "base": "SAKURA_API_BASE"},
}


class EngineError(Exception):
    """Raised when the engine cannot be prepared or started."""


@dataclass(frozen=True)
class EngineRun:
    returncode: int
    command: tuple[str, ...]


class PassthroughEngine:
    """Copies pages through untouched. Useful for testing paths without a model."""

    name = "passthrough"

    def __init__(self, config: Config) -> None:
        self.config = config

    def prepare(self, console: Console) -> None:
        return None

    def run(self, source: Path, dest: Path, console: Console, log_path: Path) -> EngineRun:
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        for item in sorted(source.iterdir()):
            if item.is_file():
                shutil.copy2(item, dest / item.name)
                copied += 1
        console.debug(f"passthrough engine copied {copied} files")
        return EngineRun(returncode=0, command=("passthrough",))


class MITEngine:
    """Runs `python -m manga_translator local` inside the upstream checkout."""

    name = "mit"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.mit: MITConfig = config.mit
        self.generated_dir = config.paths.work / "generated"
        self.config_path = self.generated_dir / "mit-config.json"
        self.gpt_path = self.generated_dir / "gpt-config.yaml"

    # -- preparation --------------------------------------------------------
    def prepare(self, console: Console) -> None:
        if not self.mit.python.is_file():
            raise EngineError(f"engine python not found: {self.mit.python}")
        if not self.mit.root.is_dir():
            raise EngineError(f"manga-image-translator checkout not found: {self.mit.root}")
        if not self.mit.base_config.is_file():
            raise EngineError(
                f"base config not found: {self.mit.base_config}\n"
                "Copy config/mit-config.example.json to config/mit-config.json."
            )
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self._write_gpt_config(console)
        self._write_mit_config(console)

    def _load_base_config(self) -> dict[str, Any]:
        try:
            data = json.loads(self.mit.base_config.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise EngineError(f"{self.mit.base_config} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise EngineError(f"{self.mit.base_config} must contain a JSON object")
        # Strip the documentation keys we ship in the example file ("_..._hint",
        # "_comment"). Upstream ignores unknown keys, but keeping the generated
        # file clean makes it easier to read when debugging.
        return {k: v for k, v in data.items() if not str(k).startswith("_")}

    def _write_mit_config(self, console: Console) -> None:
        data = self._load_base_config()
        translator = data.setdefault("translator", {})
        if not isinstance(translator, dict):
            raise EngineError("'translator' in the base config must be an object")
        translator["translator"] = self.config.translation.translator
        translator["target_lang"] = self.config.translation.target_lang
        # Point at the generated file only when there is one; otherwise leave it
        # unset so upstream falls back to its own defaults.
        translator["gpt_config"] = str(self.gpt_path) if self.gpt_path.exists() else None

        self.config_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        console.debug(f"generated {self.config_path}")

    def _write_gpt_config(self, console: Console) -> None:
        layer: dict[str, Any] = {}
        user_config = self.config.translation.gpt_config
        if user_config is not None:
            if not user_config.is_file():
                raise EngineError(f"translation.gpt_config not found: {user_config}")
            loaded = yaml.safe_load(user_config.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, dict):
                raise EngineError(f"{user_config} must contain a mapping at the top level")
            layer = loaded

        prompt = self.config.translation.prompt
        if prompt is not None:
            if not prompt.is_file():
                raise EngineError(f"translation.prompt not found: {prompt}")
            layer["chat_system_template"] = prompt.read_text(encoding="utf-8")

        if not layer:
            if self.gpt_path.exists():
                self.gpt_path.unlink()
            # An absent gpt_config makes upstream fall back to its own defaults,
            # which is a valid setup for backends that need no YAML at all.
            return

        self.gpt_path.write_text(
            yaml.safe_dump(layer, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        console.debug(f"generated {self.gpt_path}")

    # -- execution ----------------------------------------------------------
    def command(self, source: Path, dest: Path) -> list[str]:
        tr = self.config.translation
        argv: list[str] = [
            str(self.mit.python),
            "-m", "manga_translator",
            "local",                      # global flags must come *after* this
        ]
        if self.mit.gpu:
            argv.append("--use-gpu")
        if self.mit.verbose:
            argv.append("-v")
        argv += [
            "--attempts", str(self.mit.attempts),
            "--context-size", str(self.mit.context_size),
        ]
        if self.mit.font is not None and self.mit.font.is_file():
            argv += ["--font-path", str(self.mit.font)]
        if tr.pre_dict is not None and tr.pre_dict.is_file():
            argv += ["--pre-dict", str(tr.pre_dict)]
        if tr.post_dict is not None and tr.post_dict.is_file():
            argv += ["--post-dict", str(tr.post_dict)]
        argv += [
            "-i", str(source),
            "-o", str(dest),
            # PNG on purpose: the engine offers no lossless quality control for
            # WebP, and lossy output is produced afterwards by compress.py.
            "-f", "png",
            "--config-file", str(self.config_path),
        ]
        argv += list(self.mit.extra_args)
        return argv

    def environment(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")

        tr = self.config.translation
        mapping = BACKEND_ENV.get(tr.translator, {})
        if tr.model and mapping.get("model"):
            env[str(mapping["model"])] = tr.model
        if tr.base_url and mapping.get("base"):
            env[str(mapping["base"])] = tr.base_url
        if tr.api_key_env:
            key = os.environ.get(tr.api_key_env)
            if key and mapping.get("key"):
                env[str(mapping["key"])] = key
            elif not key:
                # Not fatal here: some local servers ignore the key entirely.
                env.setdefault("MSCAN_MISSING_KEY_WARN", tr.api_key_env)
        return env

    def run(self, source: Path, dest: Path, console: Console, log_path: Path) -> EngineRun:
        dest.mkdir(parents=True, exist_ok=True)
        argv = self.command(source, dest)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        code = stream_command(argv, cwd=self.mit.root, env=self.environment(), console=console)
        return EngineRun(returncode=code, command=tuple(argv))


def build(config: Config) -> MITEngine | PassthroughEngine:
    if config.engine_type == "mit":
        return MITEngine(config)
    return PassthroughEngine(config)

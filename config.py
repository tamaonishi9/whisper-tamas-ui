from copy import deepcopy
import sys
import tomllib
from pathlib import Path

from app_logging import get_logger


logger = get_logger(__name__)


DEFAULT_CONFIG = {
    "hotkey": {
        "markdown": "alt+q",
        "plain_text": "alt+w",
        "exit": "",
    },
    "whisper": {
        "model_size": "small",
        "language": "ja",
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": None,
        "num_workers": 1,
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "float32",
        "min_record_seconds": 0.2,
    },
    "output": {
        "markdown_newlines": 1,
    },
    "text_rules": {
        "filler_phrases": [
            "えーと、",
            "えーと",
            "えっと、",
            "えっと",
            "あの、",
            "あの",
        ],
        "markdown_title_patterns": [
            "タイトル",
            "title",
        ],
        "markdown_heading_patterns": [
            "見出し",
            "heading",
        ],
    },
    "tray": {
        "enabled": True,
        "tooltip": "whisper-tamas-ui",
    },
}


# config.tomlを読み込みデフォルト設定にマージして返す。読み込み失敗時はデフォルトを返す
def load_config(path: str = "config.toml") -> dict:
    config_path = resolve_config_path(path)

    if not config_path.exists():
        logger.warning("config.toml not found. Using default config.")
        return deepcopy(DEFAULT_CONFIG)

    try:
        config_text = config_path.read_text(encoding="utf-8-sig")
        user_config = tomllib.loads(config_text)
    except Exception as e:
        logger.exception("Failed to load config.toml: %s", e)
        return deepcopy(DEFAULT_CONFIG)

    return merge_config(deepcopy(DEFAULT_CONFIG), user_config)


# 凍結実行ファイルとスクリプト起動の両方に対応した設定ファイルパスを解決
def resolve_config_path(path: str) -> Path:
    config_path = Path(path)
    if config_path.is_absolute():
        return config_path

    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent

    return base_dir / config_path


# デフォルト設定にユーザー設定を再帰的に上書きマージ
def merge_config(default: dict, override: dict) -> dict:
    result = default.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value

    return result

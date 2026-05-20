from copy import deepcopy
import sys
import tomllib
from pathlib import Path


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
    "tray": {
        "enabled": True,
        "tooltip": "whisper-tamas-ui",
    },
}


def load_config(path: str = "config.toml") -> dict:
    config_path = resolve_config_path(path)

    if not config_path.exists():
        print("[config] config.toml not found. Using default config.")
        return deepcopy(DEFAULT_CONFIG)

    try:
        with open(config_path, "rb") as f:
            user_config = tomllib.load(f)
    except Exception as e:
        print(f"[config] load error: {e}")
        return deepcopy(DEFAULT_CONFIG)

    return merge_config(deepcopy(DEFAULT_CONFIG), user_config)


def resolve_config_path(path: str) -> Path:
    config_path = Path(path)
    if config_path.is_absolute():
        return config_path

    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent

    return base_dir / config_path


def merge_config(default: dict, override: dict) -> dict:
    result = default.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value

    return result

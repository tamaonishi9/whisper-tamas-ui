from copy import deepcopy
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {
    "hotkey": {
        "obsidian": "alt+q",
        "prompt": "alt+w",
        "exit": "esc",
    },
    "whisper": {
        "model_size": "small",
        "language": "ja",
        "device": "cpu",
        "compute_type": "int8",
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "dtype": "float32",
        "min_record_seconds": 0.2,
    },
    "output": {
        "obsidian_newlines": 1,
    },
    "tray": {
        "enabled": True,
        "tooltip": "whisper-tamas-ui",
    },
}


def load_config(path: str = "config.toml") -> dict:
    config_path = Path(path)

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


def merge_config(default: dict, override: dict) -> dict:
    result = default.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value

    return result

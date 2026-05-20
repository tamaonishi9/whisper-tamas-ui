import ctypes
import os
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace

from app_logging import get_logger, setup_logging
from app_controller import AppController
from config import load_config
from datas import AppState
from recorder import PushToTalkRecorder
from text_rules import TextRules
from tray import TrayController


logger = get_logger(__name__)


def install_faster_whisper_av_stub() -> None:
    if "av" in sys.modules:
        return

    av_stub = ModuleType("av")

    class InvalidDataError(Exception):
        pass

    av_stub.error = SimpleNamespace(InvalidDataError=InvalidDataError)
    sys.modules["av"] = av_stub


def configure_ctranslate2_runtime() -> None:
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def get_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def configure_frozen_dll_directories() -> None:
    if not getattr(sys, "frozen", False):
        return

    base_dir = get_app_base_dir()
    internal_dir = base_dir / "_internal"
    dll_dirs = [
        internal_dir / "ctranslate2",
        internal_dir / "numpy.libs",
        internal_dir / "onnxruntime" / "capi",
    ]

    for dll_dir in dll_dirs:
        if dll_dir.is_dir():
            os.add_dll_directory(str(dll_dir))
            logger.info("Added DLL directory: %s", dll_dir)

    preload_dlls = [
        internal_dir / "ctranslate2" / "libiomp5md.dll",
        internal_dir / "ctranslate2" / "ctranslate2.dll",
    ]

    for dll_path in preload_dlls:
        if dll_path.is_file():
            ctypes.WinDLL(str(dll_path))
            logger.info("Preloaded DLL: %s", dll_path.name)


def normalize_optional_hotkey(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized or normalized.lower() == "none":
        return None
    return normalized


def create_model(
    model_size: str,
    device: str,
    compute_type: str,
    cpu_threads: int | None,
    num_workers: int,
):
    logger.info("About to import faster_whisper")
    try:
        configure_frozen_dll_directories()
        install_faster_whisper_av_stub()
        logger.info("Installed av stub for faster_whisper")
        from faster_whisper import WhisperModel
    except Exception as error:
        logger.exception("faster_whisper import failed: %s", error)
        return None

    logger.info("faster_whisper import completed")
    logger.info("About to create WhisperModel")

    try:
        configure_ctranslate2_runtime()
        logger.info(
            "CTranslate2 runtime configured: cpu_threads=%s, num_workers=%s, OMP_NUM_THREADS=%s",
            cpu_threads,
            num_workers,
            os.environ.get("OMP_NUM_THREADS"),
        )

        model_kwargs = {
            "device": device,
            "compute_type": compute_type,
            "num_workers": num_workers,
        }
        if cpu_threads is not None:
            model_kwargs["cpu_threads"] = cpu_threads

        model = WhisperModel(model_size, **model_kwargs)
    except Exception as error:
        logger.exception("WhisperModel creation failed: %s", error)
        return None

    logger.info("WhisperModel creation completed")
    return model


def main() -> None:
    setup_logging(get_app_base_dir())
    config = load_config()
    logger.info("Application start")

    hotkey_markdown = normalize_optional_hotkey(config["hotkey"]["markdown"])
    hotkey_plain_text = normalize_optional_hotkey(config["hotkey"]["plain_text"])
    exit_hotkey = normalize_optional_hotkey(config["hotkey"]["exit"])

    sample_rate = config["audio"]["sample_rate"]
    channels = config["audio"]["channels"]
    dtype = config["audio"]["dtype"]
    min_record_seconds = config["audio"]["min_record_seconds"]

    model_size = config["whisper"]["model_size"]
    language = config["whisper"]["language"]
    device = config["whisper"]["device"]
    compute_type = config["whisper"]["compute_type"]
    cpu_threads = config["whisper"].get("cpu_threads")
    num_workers = config["whisper"]["num_workers"]

    markdown_newlines = config["output"]["markdown_newlines"]
    tray_enabled = config["tray"]["enabled"]
    tray_tooltip = config["tray"]["tooltip"]

    logger.info(
        "Config whisper settings: model_size=%s, language=%s, device=%s, compute_type=%s, cpu_threads=%s, num_workers=%s",
        model_size,
        language,
        device,
        compute_type,
        cpu_threads,
        num_workers,
    )

    if hotkey_markdown is None and hotkey_plain_text is None:
        logger.error(
            "Configuration error: either the Markdown or Plain Text hotkey must be configured"
        )
        return

    logger.info("Loading model...")
    model = create_model(model_size, device, compute_type, cpu_threads, num_workers)
    if model is None:
        return
    logger.info("Model loaded")

    text_rules = TextRules.from_config(config)
    recorder = PushToTalkRecorder(
        sample_rate=sample_rate,
        channels=channels,
        dtype=dtype,
    )
    app_state = AppState(enabled=tray_enabled)
    tray = TrayController(app_state, tooltip=tray_tooltip)

    tray_thread = threading.Thread(target=tray.start, daemon=True)
    tray_thread.start()

    controller = AppController(
        recorder=recorder,
        model=model,
        app_state=app_state,
        tray=tray,
        text_rules=text_rules,
        hotkey_markdown=hotkey_markdown,
        hotkey_plain_text=hotkey_plain_text,
        exit_hotkey=exit_hotkey,
        language=language,
        min_record_seconds=min_record_seconds,
        markdown_newlines=markdown_newlines,
    )
    controller.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        setup_logging(get_app_base_dir())
        logger.exception("Unhandled exception: %s", error)
        raise

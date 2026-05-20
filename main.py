import ctypes
import faulthandler
import os
from pathlib import Path
import sys
import threading
import traceback
from types import ModuleType, SimpleNamespace

from app_controller import AppController
from config import load_config
from datas import AppState
from recorder import PushToTalkRecorder
from text_rules import TextRules
from tray import TrayController


config = load_config()

HOTKEY_MARKDOWN_RAW = config["hotkey"]["markdown"]
HOTKEY_PLAIN_TEXT_RAW = config["hotkey"]["plain_text"]
EXIT_HOTKEY_RAW = config["hotkey"]["exit"]

SAMPLE_RATE = config["audio"]["sample_rate"]
CHANNELS = config["audio"]["channels"]
DTYPE = config["audio"]["dtype"]
MIN_RECORD_SECONDS = config["audio"]["min_record_seconds"]

MODEL_SIZE = config["whisper"]["model_size"]
LANGUAGE = config["whisper"]["language"]
DEVICE = config["whisper"]["device"]
COMPUTE_TYPE = config["whisper"]["compute_type"]
CPU_THREADS = config["whisper"].get("cpu_threads")
NUM_WORKERS = config["whisper"]["num_workers"]

MARKDOWN_NEWLINES = config["output"]["markdown_newlines"]

DIAGNOSTIC_LOG_PATH = None
FAULT_LOG_PATH = None
_DIAGNOSTIC_STREAM = None


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
            log_diagnostic(f"Added DLL directory: {dll_dir}")

    preload_dlls = [
        internal_dir / "ctranslate2" / "libiomp5md.dll",
        internal_dir / "ctranslate2" / "ctranslate2.dll",
    ]

    for dll_path in preload_dlls:
        if dll_path.is_file():
            ctypes.WinDLL(str(dll_path))
            log_diagnostic(f"Preloaded DLL: {dll_path.name}")


def log_diagnostic(message: str) -> None:
    global _DIAGNOSTIC_STREAM

    import time

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)

    if _DIAGNOSTIC_STREAM is None:
        return

    try:
        _DIAGNOSTIC_STREAM.write(line + "\n")
        _DIAGNOSTIC_STREAM.flush()
    except Exception:
        pass


def setup_diagnostics() -> None:
    global DIAGNOSTIC_LOG_PATH, FAULT_LOG_PATH, _DIAGNOSTIC_STREAM

    if _DIAGNOSTIC_STREAM is not None:
        return

    base_dir = get_app_base_dir()
    DIAGNOSTIC_LOG_PATH = base_dir / "startup.log"
    FAULT_LOG_PATH = base_dir / "fault.log"

    _DIAGNOSTIC_STREAM = open(DIAGNOSTIC_LOG_PATH, "a", encoding="utf-8")
    fault_stream = open(FAULT_LOG_PATH, "a", encoding="utf-8")

    faulthandler.enable(file=fault_stream, all_threads=True)
    log_diagnostic(f"Diagnostics enabled: {DIAGNOSTIC_LOG_PATH}")
    log_diagnostic(f"Fault handler enabled: {FAULT_LOG_PATH}")
    log_diagnostic(f"Python executable: {sys.executable}")
    log_diagnostic(f"Frozen: {getattr(sys, 'frozen', False)}")


def normalize_optional_hotkey(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized or normalized.lower() == "none":
        return None
    return normalized


def create_model():
    log_diagnostic("About to import faster_whisper")
    try:
        configure_frozen_dll_directories()
        install_faster_whisper_av_stub()
        log_diagnostic("Installed av stub for faster_whisper")
        from faster_whisper import WhisperModel
    except Exception as error:
        log_diagnostic(f"faster_whisper import failed: {error}")
        log_diagnostic(traceback.format_exc())
        print(f"faster_whisper import error: {error}")
        return None

    log_diagnostic("faster_whisper import completed")
    log_diagnostic("About to create WhisperModel")

    try:
        configure_ctranslate2_runtime()
        log_diagnostic(
            f"CTranslate2 runtime configured: cpu_threads={CPU_THREADS}, num_workers={NUM_WORKERS}, OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')}"
        )

        model_kwargs = {
            "device": DEVICE,
            "compute_type": COMPUTE_TYPE,
            "num_workers": NUM_WORKERS,
        }
        if CPU_THREADS is not None:
            model_kwargs["cpu_threads"] = CPU_THREADS

        model = WhisperModel(MODEL_SIZE, **model_kwargs)
    except Exception as error:
        log_diagnostic(f"WhisperModel creation failed: {error}")
        log_diagnostic(traceback.format_exc())
        print(f"Model load error: {error}")
        return None

    log_diagnostic("WhisperModel creation completed")
    return model


def main() -> None:
    setup_diagnostics()
    log_diagnostic("Application start")
    log_diagnostic(
        f"Config whisper settings: model_size={MODEL_SIZE}, language={LANGUAGE}, device={DEVICE}, compute_type={COMPUTE_TYPE}"
    )

    hotkey_markdown = normalize_optional_hotkey(HOTKEY_MARKDOWN_RAW)
    hotkey_plain_text = normalize_optional_hotkey(HOTKEY_PLAIN_TEXT_RAW)
    exit_hotkey = normalize_optional_hotkey(EXIT_HOTKEY_RAW)

    if hotkey_markdown is None and hotkey_plain_text is None:
        print(
            "Configuration error: either the Markdown or Plain Text hotkey must be configured"
        )
        return

    print("Loading model...")
    model = create_model()
    if model is None:
        return
    print("Model loaded")

    text_rules = TextRules.from_config(config)
    recorder = PushToTalkRecorder(
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
    )
    app_state = AppState()
    tray = TrayController(app_state)

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
        language=LANGUAGE,
        min_record_seconds=MIN_RECORD_SECONDS,
        markdown_newlines=MARKDOWN_NEWLINES,
    )
    controller.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        setup_diagnostics()
        log_diagnostic(f"Unhandled exception: {error}")
        log_diagnostic(traceback.format_exc())
        raise

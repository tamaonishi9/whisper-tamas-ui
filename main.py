import faulthandler
import ctypes
import os
from pathlib import Path
import re
import sys
import threading
import time
import traceback
from types import ModuleType, SimpleNamespace
from typing import Any, List

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
import winsound

from config import load_config

from datas import AppState
from tray import TrayController

# =========================
# 設定
# =========================
config = load_config()

HOTKEY_MARKDOWN_RAW = config["hotkey"]["markdown"]
HOTKEY_PLAIN_TEXT_RAW = config["hotkey"]["plain_text"]
EXIT_HOTKEY_RAW = config["hotkey"]["exit"]

SAMPLE_RATE = config["audio"]["sample_rate"]
CHANNELS = config["audio"]["channels"]
DTYPE = config["audio"]["dtype"]

MODEL_SIZE = config["whisper"]["model_size"]
LANGUAGE = config["whisper"]["language"]
DEVICE = config["whisper"]["device"]
COMPUTE_TYPE = config["whisper"]["compute_type"]
CPU_THREADS = config["whisper"].get("cpu_threads")
NUM_WORKERS = config["whisper"]["num_workers"]

MIN_RECORD_SECONDS = config["audio"]["min_record_seconds"]
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


def get_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def log_diagnostic(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)

    if _DIAGNOSTIC_STREAM is None:
        log_diagnostic("Startup aborted: no hotkeys configured")
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


# =========================
# 録音クラス
# =========================
class PushToTalkRecorder:
    def __init__(self, sample_rate: int, channels: int, dtype: str) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype

        self._frames: List[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self.is_recording = False

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            print(f"[録音警告] {status}")
        with self._lock:
            self._frames.append(indata.copy())

    def start(self) -> None:
        if self.is_recording:
            return

        with self._lock:
            self._frames = []

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._callback,
        )
        self._stream.start()
        self.is_recording = True

    def stop(self) -> np.ndarray | None:
        if not self.is_recording:
            return None

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        finally:
            self._stream = None
            self.is_recording = False

        with self._lock:
            if not self._frames:
                return None
            audio = np.concatenate(self._frames, axis=0)

        return audio


# =========================
# 整形
# =========================
def normalize_text(text: str) -> str:
    text = text.strip()
    text = text.replace("\n", " ")
    text = " ".join(text.split())
    return text


# =========================
# 文字起こし
# =========================
def transcribe_audio(model: Any, audio: np.ndarray) -> str:
    if audio.ndim == 2:
        audio = audio[:, 0]

    segments, info = model.transcribe(
        audio,
        language=LANGUAGE,
    )

    text = "".join(segment.text for segment in segments)
    return normalize_text(text)


def normalize_optional_hotkey(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.lower() == "none":
        return None
    return normalized


HOTKEY_MARKDOWN = normalize_optional_hotkey(HOTKEY_MARKDOWN_RAW)
HOTKEY_PLAIN_TEXT = normalize_optional_hotkey(HOTKEY_PLAIN_TEXT_RAW)
EXIT_HOTKEY = normalize_optional_hotkey(EXIT_HOTKEY_RAW)


# =========================
# mode別の整形
# =========================
def format_text_by_mode(text: str, mode: str | None) -> str:
    if mode == "markdown":
        return format_markdown_text(text)
    if mode == "plain_text":
        return text
    return text


def format_markdown_text(text: str) -> str:
    text = strip_filler(text)
    text = text.strip()

    if not text:
        return ""

    patterns = [
        (r"^(?:タイトル|title)\s*[：:]?\s*(.+)$", "# {}"),
        (r"^(?:見出し|heading)\s*[：:]?\s*(.+)$", "## {}"),
    ]

    for pattern, template in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            content = match.group(1).strip()
            if content:
                return template.format(content)

    return f"- {text}"


def strip_filler(text: str) -> str:
    fillers = [
        "えーっと、",
        "えーっと",
        "えーと、",
        "えーと",
        "えっと、",
        "えっと",
        "あのー",
        "あのー、",
        "あの、",
        "あの",
        "えー、",
        "えー",
    ]

    text = text.strip()

    for f in fillers:
        if text.startswith(f):
            text = text[len(f) :].strip()

    return text


def add_output_spacing(text: str, mode: str | None) -> str:
    if mode == "markdown":
        try:
            newline_count = max(0, int(MARKDOWN_NEWLINES))
        except (TypeError, ValueError):
            newline_count = 1
        return text + ("\n" * newline_count)
    if mode == "plain_text":
        return text
    return text


def get_hotkey_for_mode(mode: str | None) -> str | None:
    if mode == "markdown":
        return HOTKEY_MARKDOWN
    if mode == "plain_text":
        return HOTKEY_PLAIN_TEXT
    return None


# =========================
# サウンド
# =========================
def play_sound_sequence_async(sequence: list[tuple[int, int]]) -> None:
    def worker() -> None:
        try:
            for frequency, duration in sequence:
                winsound.Beep(frequency, duration)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def play_start_sound() -> None:
    play_sound_sequence_async([(880, 100)])


def play_done_sound() -> None:
    play_sound_sequence_async([(440, 150)])


def play_error_sound() -> None:
    play_sound_sequence_async([(300, 120), (200, 120)])


def begin_recording(
    recorder: PushToTalkRecorder,
    app_state: AppState,
    tray: TrayController,
    mode: str,
) -> float | None:
    try:
        play_start_sound()
        recorder.start()
    except Exception as e:
        print(f"録音開始エラー: {e}")
        play_error_sound()
        return None

    record_start = time.time()

    with app_state.lock:
        app_state.is_recording = True
        app_state.current_mode = mode

    tray.refresh()
    print("録音開始")
    return record_start


def finish_recording(
    recorder: PushToTalkRecorder,
    model: Any,
    app_state: AppState,
    tray: TrayController,
    record_mode: str | None,
    record_start: float,
) -> None:
    audio = recorder.stop()
    record_seconds = time.time() - record_start

    with app_state.lock:
        app_state.is_recording = False

    tray.refresh()
    print(f"録音終了 ({record_seconds:.2f}秒)")

    if audio is None:
        print("音声が取得できませんでした")
        play_error_sound()
        return

    if record_seconds < MIN_RECORD_SECONDS:
        print("短すぎるのでスキップ")
        play_error_sound()
        return

    print("文字起こし中...")
    t0 = time.time()

    try:
        text = transcribe_audio(model, audio)
    except Exception as e:
        print(f"文字起こしエラー: {e}")
        play_error_sound()
        return

    elapsed = time.time() - t0

    if not text:
        print("結果が空でした")
        play_error_sound()
        return

    try:
        text = format_text_by_mode(text, record_mode)
        text = add_output_spacing(text, record_mode)
        pyperclip.copy(text)
        copied = True
        play_done_sound()
    except Exception as e:
        print(f"クリップボードコピー失敗: {e}")
        play_error_sound()
        copied = False

    print("")
    print("--- 結果 ---")
    print(text)
    print("------------")
    print(f"文字起こし時間: {elapsed:.2f}秒")
    if copied:
        print("クリップボードにコピーしました")
    print("")

    with app_state.lock:
        app_state.current_mode = record_mode

    tray.refresh()


def restart_recording(
    recorder: PushToTalkRecorder,
    app_state: AppState,
    tray: TrayController,
    mode: str,
) -> float | None:
    recorder.stop()

    with app_state.lock:
        app_state.is_recording = False
        app_state.current_mode = None

    tray.refresh()
    print("録音を破棄して再開します")
    return begin_recording(recorder, app_state, tray, mode)


# =========================
# メイン
# =========================
def main() -> None:
    setup_diagnostics()
    log_diagnostic("Application start")
    log_diagnostic(
        f"Config whisper settings: model_size={MODEL_SIZE}, language={LANGUAGE}, device={DEVICE}, compute_type={COMPUTE_TYPE}"
    )
    if HOTKEY_MARKDOWN is None and HOTKEY_PLAIN_TEXT is None:
        print(
            "設定エラー: Markdown用またはPlain Text用のどちらかのホットキーは必須です"
        )
        return

    print("モデルロード中...")
    log_diagnostic("About to import faster_whisper")
    try:
        configure_frozen_dll_directories()
        install_faster_whisper_av_stub()
        log_diagnostic("Installed av stub for faster_whisper")
        from faster_whisper import WhisperModel
    except Exception as e:
        log_diagnostic(f"faster_whisper import failed: {e}")
        log_diagnostic(traceback.format_exc())
        print(f"faster_whisper import error: {e}")
        return

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
    except Exception as e:
        log_diagnostic(f"WhisperModel creation failed: {e}")
        log_diagnostic(traceback.format_exc())
        print(f"モデルロードエラー: {e}")
        return
    log_diagnostic("WhisperModel creation completed")
    print("モデルロード完了")

    recorder = PushToTalkRecorder(
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
    )
    app_state = AppState()
    tray = TrayController(app_state)

    tray_thread = threading.Thread(target=tray.start, daemon=True)
    tray_thread.start()

    print("")
    print("待機中...")
    if HOTKEY_MARKDOWN is not None:
        print(f"[{HOTKEY_MARKDOWN}] Markdown用で録音")
    if HOTKEY_PLAIN_TEXT is not None:
        print(f"[{HOTKEY_PLAIN_TEXT}] Plain Text用で録音")
    if EXIT_HOTKEY is not None:
        print(f"[{EXIT_HOTKEY}] 終了")
    print("")

    pressed_mode = None
    record_mode = None
    record_start = 0.0
    prev_markdown_pressed = False
    prev_plain_text_pressed = False

    try:
        while True:
            with app_state.lock:
                if app_state.should_exit:
                    print("終了します")
                    break
                enabled = app_state.enabled
                input_mode = app_state.input_mode

            if EXIT_HOTKEY is not None and keyboard.is_pressed(EXIT_HOTKEY):
                print("終了します")
                break

            if recorder.is_recording and not enabled:
                recorder.stop()
                record_mode = None

                with app_state.lock:
                    app_state.is_recording = False
                    app_state.current_mode = None

                tray.refresh()
                print("無効化されたため録音を中止しました")
                time.sleep(0.05)
                continue

            if not enabled:
                time.sleep(0.05)
                continue

            # 音声出力モードのホットキー押下判定
            markdown_pressed = HOTKEY_MARKDOWN is not None and keyboard.is_pressed(
                HOTKEY_MARKDOWN
            )
            plain_text_pressed = HOTKEY_PLAIN_TEXT is not None and keyboard.is_pressed(
                HOTKEY_PLAIN_TEXT
            )

            if markdown_pressed:
                pressed_mode = "markdown"
            elif plain_text_pressed:
                pressed_mode = "plain_text"
            else:
                pressed_mode = None

            markdown_just_pressed = markdown_pressed and not prev_markdown_pressed
            plain_text_just_pressed = plain_text_pressed and not prev_plain_text_pressed

            # 入力モードで分岐
            if input_mode == "p2t":
                active_hotkey = get_hotkey_for_mode(record_mode)

                if pressed_mode is not None and not recorder.is_recording:
                    started_at = begin_recording(
                        recorder, app_state, tray, pressed_mode
                    )
                    if started_at is None:
                        time.sleep(0.1)
                        prev_markdown_pressed = markdown_pressed
                        prev_plain_text_pressed = plain_text_pressed
                        continue

                    record_mode = pressed_mode
                    record_start = started_at

                elif (
                    recorder.is_recording
                    and active_hotkey is not None
                    and not keyboard.is_pressed(active_hotkey)
                ):
                    finish_recording(
                        recorder,
                        model,
                        app_state,
                        tray,
                        record_mode,
                        record_start,
                    )
                    record_mode = None

            elif input_mode == "toggle":
                just_pressed_mode = None
                if markdown_just_pressed:
                    just_pressed_mode = "markdown"
                elif plain_text_just_pressed:
                    just_pressed_mode = "plain_text"

                if just_pressed_mode is not None:
                    if not recorder.is_recording:
                        started_at = begin_recording(
                            recorder, app_state, tray, just_pressed_mode
                        )
                        if started_at is not None:
                            record_mode = just_pressed_mode
                            record_start = started_at
                        else:
                            time.sleep(0.1)
                    elif just_pressed_mode == record_mode:
                        finish_recording(
                            recorder,
                            model,
                            app_state,
                            tray,
                            record_mode,
                            record_start,
                        )
                        record_mode = None
                    else:
                        restarted_at = restart_recording(
                            recorder,
                            app_state,
                            tray,
                            just_pressed_mode,
                        )
                        if restarted_at is not None:
                            record_mode = just_pressed_mode
                            record_start = restarted_at
                        else:
                            record_mode = None
                            time.sleep(0.1)

            prev_markdown_pressed = markdown_pressed
            prev_plain_text_pressed = plain_text_pressed

            time.sleep(0.02)

    except KeyboardInterrupt:
        print("Ctrl+C で終了しました")
    finally:
        with app_state.lock:
            app_state.should_exit = True
            app_state.is_recording = False
            app_state.current_mode = None

        if recorder.is_recording:
            recorder.stop()

        tray.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        setup_diagnostics()
        log_diagnostic(f"Unhandled exception: {e}")
        log_diagnostic(traceback.format_exc())
        raise

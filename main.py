import re
import time
import threading
from typing import List

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
import winsound

from faster_whisper import WhisperModel

from config import load_config

from datas import AppState
from tray import TrayController

# =========================
# 設定
# =========================
config = load_config()

HOTKEY_OBSIDIAN = config["hotkey"]["obsidian"]
HOTKEY_PROMPT = config["hotkey"]["prompt"]
EXIT_HOTKEY = config["hotkey"]["exit"]

SAMPLE_RATE = config["audio"]["sample_rate"]
CHANNELS = config["audio"]["channels"]
DTYPE = config["audio"]["dtype"]

MODEL_SIZE = config["whisper"]["model_size"]
LANGUAGE = config["whisper"]["language"]
DEVICE = config["whisper"]["device"]
COMPUTE_TYPE = config["whisper"]["compute_type"]

MIN_RECORD_SECONDS = config["audio"]["min_record_seconds"]
OBSIDIAN_NEWLINES = config["output"]["obsidian_newlines"]


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
def transcribe_audio(model: WhisperModel, audio: np.ndarray) -> str:
    if audio.ndim == 2:
        audio = audio[:, 0]

    segments, info = model.transcribe(
        audio,
        language=LANGUAGE,
    )

    text = "".join(segment.text for segment in segments)
    return normalize_text(text)


# =========================
# mode別の整形
# =========================
def format_text_by_mode(text: str, mode: str | None) -> str:
    if mode == "obsidian":
        return format_obsidian_text(text)
    if mode == "prompt":
        return text
    return text


def format_obsidian_text(text: str) -> str:
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
    if mode == "obsidian":
        try:
            newline_count = max(0, int(OBSIDIAN_NEWLINES))
        except (TypeError, ValueError):
            newline_count = 1
        return text + ("\n" * newline_count)
    if mode == "prompt":
        return text
    return text


def get_hotkey_for_mode(mode: str | None) -> str | None:
    if mode == "obsidian":
        return HOTKEY_OBSIDIAN
    if mode == "prompt":
        return HOTKEY_PROMPT
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
    model: WhisperModel,
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


# =========================
# メイン
# =========================
def main() -> None:
    print("モデルロード中...")
    try:
        model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )
    except Exception as e:
        print(f"モデルロードエラー: {e}")
        return
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
    print(f"[{HOTKEY_OBSIDIAN}] Obsidian用で録音")
    print(f"[{HOTKEY_PROMPT}] Prompt用で録音")
    print(f"[{EXIT_HOTKEY}] 終了")
    print("")

    pressed_mode = None
    record_mode = None
    record_start = 0.0
    prev_obsidian_pressed = False
    prev_prompt_pressed = False

    try:
        while True:
            with app_state.lock:
                if app_state.should_exit:
                    print("終了します")
                    break
                enabled = app_state.enabled
                input_mode = app_state.input_mode

            if keyboard.is_pressed(EXIT_HOTKEY):
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

            obsidian_pressed = keyboard.is_pressed(HOTKEY_OBSIDIAN)
            prompt_pressed = keyboard.is_pressed(HOTKEY_PROMPT)

            if obsidian_pressed:
                pressed_mode = "obsidian"
            elif prompt_pressed:
                pressed_mode = "prompt"
            else:
                pressed_mode = None

            obsidian_just_pressed = obsidian_pressed and not prev_obsidian_pressed
            prompt_just_pressed = prompt_pressed and not prev_prompt_pressed

            if input_mode == "p2t":
                active_hotkey = get_hotkey_for_mode(record_mode)

                if pressed_mode is not None and not recorder.is_recording:
                    started_at = begin_recording(recorder, app_state, tray, pressed_mode)
                    if started_at is None:
                        time.sleep(0.1)
                        prev_obsidian_pressed = obsidian_pressed
                        prev_prompt_pressed = prompt_pressed
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
                if obsidian_just_pressed:
                    just_pressed_mode = "obsidian"
                elif prompt_just_pressed:
                    just_pressed_mode = "prompt"

                if just_pressed_mode is not None:
                    if not recorder.is_recording:
                        started_at = begin_recording(recorder, app_state, tray, just_pressed_mode)
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
                        finish_recording(
                            recorder,
                            model,
                            app_state,
                            tray,
                            record_mode,
                            record_start,
                        )
                        record_mode = None

            prev_obsidian_pressed = obsidian_pressed
            prev_prompt_pressed = prompt_pressed

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
    main()

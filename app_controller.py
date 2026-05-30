import queue
import sys
import threading
import time
from typing import Any

import keyboard
import pyperclip

from app_logging import get_logger
from audio_feedback import play_done_sound, play_error_sound, play_start_sound
from datas import AppState
from recorder import PushToTalkRecorder
from text_rules import TextRules
from tray import TrayController


logger = get_logger(__name__)


class AppController:
    def __init__(
        self,
        recorder: PushToTalkRecorder,
        model: Any,
        app_state: AppState,
        tray: TrayController,
        text_rules: TextRules,
        hotkey_markdown: str | None,
        hotkey_plain_text: str | None,
        exit_hotkey: str | None,
        language: str,
        min_record_seconds: float,
        markdown_newlines: int,
        llm_client: Any = None,
    ) -> None:
        self.recorder = recorder
        self.model = model
        self.app_state = app_state
        self.tray = tray
        self.text_rules = text_rules
        self.hotkey_markdown = hotkey_markdown
        self.hotkey_plain_text = hotkey_plain_text
        self.exit_hotkey = exit_hotkey
        self.language = language
        self.min_record_seconds = min_record_seconds
        self.markdown_newlines = markdown_newlines
        self.llm_client = llm_client

        # 単一ワーカーで直列処理するキューとスレッドを起動
        self._queue: queue.Queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    # キューから録音データを取り出して順番に処理するワーカー
    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            # Noneは終了シグナル
            if item is None:
                break
            audio, record_mode = item
            try:
                self._process_recording(audio, record_mode)
            except Exception as error:
                logger.exception("Unexpected worker error: %s", error)

    # キー入力を監視して録音の開始・停止を制御するメインループ
    def run(self) -> None:
        logger.info("")
        logger.info("Idle...")
        if self.hotkey_markdown is not None:
            logger.info("[%s] Start recording in Markdown mode", self.hotkey_markdown)
        if self.hotkey_plain_text is not None:
            logger.info(
                "[%s] Start recording in Plain Text mode", self.hotkey_plain_text
            )
        if self.exit_hotkey is not None:
            logger.info("[%s] Exit", self.exit_hotkey)
        logger.info("")

        # 状態変数初期化
        pressed_mode = None
        record_mode = None
        record_start = 0.0
        prev_markdown_pressed = False
        prev_plain_text_pressed = False

        try:
            while True:
                # 終了要求・有効状態の確認
                with self.app_state.lock:
                    if self.app_state.should_exit:
                        logger.info("Exiting")
                        break
                    enabled = self.app_state.enabled
                    input_mode = self.app_state.input_mode

                # 終了ホットキーチェック
                if self.exit_hotkey is not None and keyboard.is_pressed(self.exit_hotkey):
                    logger.info("Exiting")
                    break

                # 無効化中に録音中だった場合は強制停止
                if self.recorder.is_recording and not enabled:
                    self.recorder.stop()
                    record_mode = None

                    with self.app_state.lock:
                        self.app_state.is_recording = False
                        self.app_state.current_mode = None

                    self.tray.refresh()
                    logger.info("Recording stopped because voice input was disabled")
                    time.sleep(0.05)
                    continue

                if not enabled:
                    time.sleep(0.05)
                    continue

                # キー押下状態を取得
                markdown_pressed = (
                    self.hotkey_markdown is not None
                    and keyboard.is_pressed(self.hotkey_markdown)
                )
                plain_text_pressed = (
                    self.hotkey_plain_text is not None
                    and keyboard.is_pressed(self.hotkey_plain_text)
                )

                if markdown_pressed:
                    pressed_mode = "markdown"
                elif plain_text_pressed:
                    pressed_mode = "plain_text"
                else:
                    pressed_mode = None

                markdown_just_pressed = markdown_pressed and not prev_markdown_pressed
                plain_text_just_pressed = plain_text_pressed and not prev_plain_text_pressed

                # P2Tモード: 押している間録音、離したら停止
                if input_mode == "p2t":
                    active_hotkey = self.get_hotkey_for_mode(record_mode)

                    if pressed_mode is not None and not self.recorder.is_recording:
                        started_at = self.begin_recording(pressed_mode)
                        if started_at is None:
                            time.sleep(0.1)
                            prev_markdown_pressed = markdown_pressed
                            prev_plain_text_pressed = plain_text_pressed
                            continue

                        record_mode = pressed_mode
                        record_start = started_at

                    elif (
                        self.recorder.is_recording
                        and active_hotkey is not None
                        and not keyboard.is_pressed(active_hotkey)
                    ):
                        self.finish_recording(record_mode, record_start)
                        record_mode = None

                # Toggleモード: キー押下で録音開始/停止をトグル
                elif input_mode == "toggle":
                    just_pressed_mode = None
                    if markdown_just_pressed:
                        just_pressed_mode = "markdown"
                    elif plain_text_just_pressed:
                        just_pressed_mode = "plain_text"

                    if just_pressed_mode is not None:
                        if not self.recorder.is_recording:
                            started_at = self.begin_recording(just_pressed_mode)
                            if started_at is not None:
                                record_mode = just_pressed_mode
                                record_start = started_at
                            else:
                                time.sleep(0.1)
                        elif just_pressed_mode == record_mode:
                            self.finish_recording(record_mode, record_start)
                            record_mode = None
                        else:
                            restarted_at = self.restart_recording(just_pressed_mode)
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
            logger.info("Exited with Ctrl+C")
        finally:
            # ワーカーへ終了シグナルを送信し、処理中タスクの完了を待つ
            self._queue.put(None)
            self._worker_thread.join(timeout=30.0)

            # 終了処理: AppState更新・ストリーム停止・トレイ停止
            with self.app_state.lock:
                self.app_state.should_exit = True
                self.app_state.is_recording = False
                self.app_state.current_mode = None

            if self.recorder.is_recording:
                self.recorder.stop()

            self.tray.stop()

    # サウンド再生→ストリーム開始→AppState更新。失敗時はNoneを返す
    def begin_recording(self, mode: str) -> float | None:
        try:
            play_start_sound()
            self.recorder.start()
        except Exception as error:
            logger.exception("Recording start error: %s", error)
            play_error_sound()
            return None

        record_start = time.time()

        with self.app_state.lock:
            self.app_state.is_recording = True
            self.app_state.current_mode = mode

        self.tray.refresh()
        logger.info("Recording started")
        return record_start

    # 録音停止・最低時間チェックをメインスレッドで実行し、重い処理をキューへ投入
    def finish_recording(self, record_mode: str | None, record_start: float) -> None:
        audio = self.recorder.stop()
        record_seconds = time.time() - record_start

        with self.app_state.lock:
            self.app_state.is_recording = False

        self.tray.refresh()
        logger.info("Recording stopped (%.2fs)", record_seconds)

        if audio is None:
            logger.warning("No audio was captured")
            play_error_sound()
            return

        if record_seconds < self.min_record_seconds:
            logger.info("Recording too short, skipping")
            play_error_sound()
            return

        # Whisper文字起こしとLLM後処理はバックグラウンドワーカーへ投入
        self._queue.put((audio, record_mode))

    # 文字起こし→前処理→LLM後処理→整形→クリップボード出力
    def _process_recording(self, audio, record_mode: str | None) -> None:
        logger.info("Transcribing...")
        started_at = time.time()

        try:
            raw_text = self.transcribe_audio(audio)
        except Exception as error:
            logger.exception("Transcription error: %s", error)
            play_error_sound()
            return

        elapsed = time.time() - started_at

        if not raw_text:
            logger.warning("Transcription result was empty")
            play_error_sound()
            return

        # LLM前処理: filler除去（全モード共通、LLM有効時のノイズ抑制も兼ねる）
        text = self.text_rules.strip_filler(raw_text)

        # 直接実行時のみLLM前テキストをデバッグ出力（frozen実行では非表示）
        if not getattr(sys, "frozen", False):
            logger.info("--- Before LLM ---\n%s\n-----------------", text)

        # LLM後処理（enabled=trueかつmodel設定済みの場合のみ）
        if self.llm_client is not None:
            logger.info("Running LLM post-processing...")
            llm_result = self.llm_client.process(text)
            if llm_result is not None:
                text = llm_result
            else:
                logger.info("LLM post-processing failed, using Whisper result")

        # 出力モード別整形とクリップボード出力
        try:
            text = self.text_rules.format_text_by_mode(text, record_mode)
            text = self.add_output_spacing(text, record_mode)
            pyperclip.copy(text)
            copied = True
            play_done_sound()
        except Exception as error:
            logger.exception("Clipboard copy failed: %s", error)
            play_error_sound()
            copied = False

        logger.info("")
        logger.info("--- Result ---\n%s\n------------", text)
        logger.info("Transcription time: %.2fs", elapsed)
        if copied:
            logger.info("Copied to clipboard")
        logger.info("")

        with self.app_state.lock:
            self.app_state.current_mode = record_mode
        # バックグラウンドワーカーからtray.refresh()は呼ばない（pystrayスレッド安全性のため）

    # 現在の録音を破棄して別モードで録音を再開
    def restart_recording(self, mode: str) -> float | None:
        self.recorder.stop()

        with self.app_state.lock:
            self.app_state.is_recording = False
            self.app_state.current_mode = None

        self.tray.refresh()
        logger.info("Discarding current recording and starting over")
        return self.begin_recording(mode)

    # ステレオ音声をモノラルに変換してWhisperで文字起こし
    def transcribe_audio(self, audio) -> str:
        if audio.ndim == 2:
            audio = audio[:, 0]

        segments, _info = self.model.transcribe(audio, language=self.language)
        text = "".join(segment.text for segment in segments)
        return self.text_rules.normalize_text(text)

    # Markdownモード時のみ末尾に指定行数の改行を付加
    def add_output_spacing(self, text: str, mode: str | None) -> str:
        if mode == "markdown":
            return text + ("\n" * max(0, self.markdown_newlines))
        return text

    # モード名に対応するホットキー文字列を返す
    def get_hotkey_for_mode(self, mode: str | None) -> str | None:
        if mode == "markdown":
            return self.hotkey_markdown
        if mode == "plain_text":
            return self.hotkey_plain_text
        return None

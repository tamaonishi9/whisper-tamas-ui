import time
from typing import Any

import keyboard
import pyperclip

from audio_feedback import play_done_sound, play_error_sound, play_start_sound
from datas import AppState
from recorder import PushToTalkRecorder
from text_rules import TextRules
from tray import TrayController


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

    def run(self) -> None:
        print("")
        print("Idle...")
        if self.hotkey_markdown is not None:
            print(f"[{self.hotkey_markdown}] Start recording in Markdown mode")
        if self.hotkey_plain_text is not None:
            print(f"[{self.hotkey_plain_text}] Start recording in Plain Text mode")
        if self.exit_hotkey is not None:
            print(f"[{self.exit_hotkey}] Exit")
        print("")

        pressed_mode = None
        record_mode = None
        record_start = 0.0
        prev_markdown_pressed = False
        prev_plain_text_pressed = False

        try:
            while True:
                with self.app_state.lock:
                    if self.app_state.should_exit:
                        print("Exiting")
                        break
                    enabled = self.app_state.enabled
                    input_mode = self.app_state.input_mode

                if self.exit_hotkey is not None and keyboard.is_pressed(self.exit_hotkey):
                    print("Exiting")
                    break

                if self.recorder.is_recording and not enabled:
                    self.recorder.stop()
                    record_mode = None

                    with self.app_state.lock:
                        self.app_state.is_recording = False
                        self.app_state.current_mode = None

                    self.tray.refresh()
                    print("Recording stopped because voice input was disabled")
                    time.sleep(0.05)
                    continue

                if not enabled:
                    time.sleep(0.05)
                    continue

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
            print("Exited with Ctrl+C")
        finally:
            with self.app_state.lock:
                self.app_state.should_exit = True
                self.app_state.is_recording = False
                self.app_state.current_mode = None

            if self.recorder.is_recording:
                self.recorder.stop()

            self.tray.stop()

    def begin_recording(self, mode: str) -> float | None:
        try:
            play_start_sound()
            self.recorder.start()
        except Exception as error:
            print(f"Recording start error: {error}")
            play_error_sound()
            return None

        record_start = time.time()

        with self.app_state.lock:
            self.app_state.is_recording = True
            self.app_state.current_mode = mode

        self.tray.refresh()
        print("Recording started")
        return record_start

    def finish_recording(self, record_mode: str | None, record_start: float) -> None:
        audio = self.recorder.stop()
        record_seconds = time.time() - record_start

        with self.app_state.lock:
            self.app_state.is_recording = False

        self.tray.refresh()
        print(f"Recording stopped ({record_seconds:.2f}s)")

        if audio is None:
            print("No audio was captured")
            play_error_sound()
            return

        if record_seconds < self.min_record_seconds:
            print("Recording too short, skipping")
            play_error_sound()
            return

        print("Transcribing...")
        started_at = time.time()

        try:
            text = self.transcribe_audio(audio)
        except Exception as error:
            print(f"Transcription error: {error}")
            play_error_sound()
            return

        elapsed = time.time() - started_at

        if not text:
            print("Transcription result was empty")
            play_error_sound()
            return

        try:
            text = self.text_rules.format_text_by_mode(text, record_mode)
            text = self.add_output_spacing(text, record_mode)
            pyperclip.copy(text)
            copied = True
            play_done_sound()
        except Exception as error:
            print(f"Clipboard copy failed: {error}")
            play_error_sound()
            copied = False

        print("")
        print("--- Result ---")
        print(text)
        print("------------")
        print(f"Transcription time: {elapsed:.2f}s")
        if copied:
            print("Copied to clipboard")
        print("")

        with self.app_state.lock:
            self.app_state.current_mode = record_mode

        self.tray.refresh()

    def restart_recording(self, mode: str) -> float | None:
        self.recorder.stop()

        with self.app_state.lock:
            self.app_state.is_recording = False
            self.app_state.current_mode = None

        self.tray.refresh()
        print("Discarding current recording and starting over")
        return self.begin_recording(mode)

    def transcribe_audio(self, audio) -> str:
        if audio.ndim == 2:
            audio = audio[:, 0]

        segments, _info = self.model.transcribe(audio, language=self.language)
        text = "".join(segment.text for segment in segments)
        return self.text_rules.normalize_text(text)

    def add_output_spacing(self, text: str, mode: str | None) -> str:
        if mode == "markdown":
            return text + ("\n" * max(0, self.markdown_newlines))
        return text

    def get_hotkey_for_mode(self, mode: str | None) -> str | None:
        if mode == "markdown":
            return self.hotkey_markdown
        if mode == "plain_text":
            return self.hotkey_plain_text
        return None

import threading
import winsound


# 周波数・時間のシーケンスを別スレッドで非同期再生
def play_sound_sequence_async(sequence: list[tuple[int, int]]) -> None:
    def worker() -> None:
        try:
            for frequency, duration in sequence:
                winsound.Beep(frequency, duration)
        except Exception:
            pass  # 音声フィードバック失敗は無視（非クリティカル）

    threading.Thread(target=worker, daemon=True).start()


# 録音開始音
def play_start_sound() -> None:
    play_sound_sequence_async([(880, 100)])


# 文字起こし完了音
def play_done_sound() -> None:
    play_sound_sequence_async([(440, 150)])


# エラー音
def play_error_sound() -> None:
    play_sound_sequence_async([(300, 120), (200, 120)])

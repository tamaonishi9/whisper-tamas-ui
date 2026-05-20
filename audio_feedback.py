import threading
import winsound


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

import pystray
from PIL import Image, ImageDraw

from datas import AppState


class TrayController:
    def __init__(self, app_state: AppState) -> None:
        self.app_state = app_state
        self.icon: pystray.Icon | None = None

    def create_image(self, enabled: bool = True) -> Image.Image:
        bg = "black" if enabled else "gray"
        fg = "white"

        image = Image.new("RGB", (64, 64), bg)
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 16, 48, 48), fill=fg)
        return image

    def get_status_title(self) -> str:
        with self.app_state.lock:
            enabled = self.app_state.enabled
            is_recording = self.app_state.is_recording
            current_mode = self.app_state.current_mode

        enabled_text = "有効" if enabled else "無効"
        recording_text = "録音中" if is_recording else "待機中"

        if current_mode == "obsidian":
            mode_text = "Obsidian"
        elif current_mode == "prompt":
            mode_text = "Prompt"
        else:
            mode_text = "-"

        return f"状態: {enabled_text} / {recording_text} / モード: {mode_text}"

    def build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: "無効化" if self.app_state.enabled else "有効化",
                self.toggle_enabled,
            ),
            pystray.MenuItem(
                lambda item: self.get_status_title(),
                lambda icon, item: None,
                enabled=False,
            ),
            pystray.MenuItem(
                "終了",
                self.request_exit,
            ),
            pystray.MenuItem(
                lambda item: f"操作モード: {'P2T' if self.app_state.input_mode == 'p2t' else 'Toggle'}",
                lambda icon, item: None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Push2Talk",
                self.set_input_mode_p2t,
                checked=lambda item: self.app_state.input_mode == "p2t",
            ),
            pystray.MenuItem(
                "Toggle",
                self.set_input_mode_toggle,
                checked=lambda item: self.app_state.input_mode == "toggle",
            ),
        )

    def refresh(self) -> None:
        if self.icon is None:
            return

        with self.app_state.lock:
            enabled = self.app_state.enabled

        self.icon.icon = self.create_image(enabled=enabled)
        self.icon.title = self.get_status_title()
        self.icon.menu = self.build_menu()
        self.icon.update_menu()

    def toggle_enabled(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.enabled = not self.app_state.enabled
            enabled = self.app_state.enabled

        print("音声入力を有効化しました" if enabled else "音声入力を無効化しました")
        self.refresh()

    def request_exit(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.should_exit = True
        print("トレイから終了要求を受け付けました")
        icon.stop()

    def start(self) -> None:
        self.icon = pystray.Icon(
            "whisper_tamas_ui",
            self.create_image(enabled=True),
            "whisper-tamas-ui",
        )
        self.icon.menu = self.build_menu()
        self.icon.title = self.get_status_title()
        self.icon.run()

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()

    def set_input_mode_p2t(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.input_mode = "p2t"
        print("操作モードを Push2Talk に切り替えました")
        self.refresh()

    def set_input_mode_toggle(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.input_mode = "toggle"
        print("操作モードを Toggle に切り替えました")
        self.refresh()

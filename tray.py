import pystray
from PIL import Image, ImageDraw

from datas import AppState
from startup import is_startup_registered, run_startup_script

APP_NAME = "Whisper Tamas"


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

        enabled_text = "Enabled" if enabled else "Disabled"
        recording_text = "Recording" if is_recording else "Idle"

        if current_mode == "markdown":
            mode_text = "Markdown"
        elif current_mode == "plain_text":
            mode_text = "Plain Text"
        else:
            mode_text = "-"

        return f"Status: {enabled_text} / {recording_text} / Mode: {mode_text}"

    def get_input_mode_label(self, item=None) -> str:
        mode_text = "Push2Talk" if self.app_state.input_mode == "p2t" else "Toggle"
        return f"Input Mode: {mode_text}"

    def get_startup_status_label(self, item=None) -> str:
        return (
            "Startup: Registered"
            if is_startup_registered()
            else "Startup: Not Registered"
        )

    def build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                lambda item: self.get_status_title(),
                lambda icon, item: None,
                enabled=False,
            ),
            pystray.MenuItem(
                self.get_input_mode_label,
                lambda icon, item: None,
                enabled=False,
            ),
            pystray.MenuItem(
                self.get_startup_status_label,
                lambda icon, item: None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "Disable" if self.app_state.enabled else "Enable",
                self.toggle_enabled,
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
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Register Startup",
                self.register_startup,
                enabled=lambda item: not is_startup_registered(),
            ),
            pystray.MenuItem(
                "Unregister Startup",
                self.unregister_startup,
                enabled=lambda item: is_startup_registered(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Exit",
                self.request_exit,
            ),
        )

    def refresh(self) -> None:
        if self.icon is None:
            return

        with self.app_state.lock:
            enabled = self.app_state.enabled

        self.icon.icon = self.create_image(enabled=enabled)
        self.icon.title = f"{APP_NAME} | {self.get_status_title()}"
        self.icon.menu = self.build_menu()
        self.icon.update_menu()

    def toggle_enabled(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.enabled = not self.app_state.enabled
            enabled = self.app_state.enabled

        print("Voice input enabled" if enabled else "Voice input disabled")
        self.refresh()

    def register_startup(self, icon: pystray.Icon, item) -> None:
        if run_startup_script("install_startup.ps1"):
            print("Startup registration completed")
        else:
            print("Startup registration failed")
        self.refresh()

    def unregister_startup(self, icon: pystray.Icon, item) -> None:
        if run_startup_script("uninstall_startup.ps1"):
            print("Startup unregistration completed")
        else:
            print("Startup unregistration failed")
        self.refresh()

    def request_exit(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.should_exit = True
        print("Exit requested from tray")
        icon.stop()

    def start(self) -> None:
        self.icon = pystray.Icon(
            "whisper_tamas_ui",
            self.create_image(enabled=True),
            APP_NAME,
        )
        self.icon.menu = self.build_menu()
        self.icon.title = f"{APP_NAME} | {self.get_status_title()}"
        self.icon.run()

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()

    def set_input_mode_p2t(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.input_mode = "p2t"
        print("Input mode switched to Push2Talk")
        self.refresh()

    def set_input_mode_toggle(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.input_mode = "toggle"
        print("Input mode switched to Toggle")
        self.refresh()

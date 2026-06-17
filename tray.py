import io

import pystray
from PIL import Image, ImageDraw

from app_logging import get_logger
from datas import AppState
from startup import is_startup_registered, run_startup_script

APP_NAME = "Whisper Tamas"
logger = get_logger(__name__)


class TrayController:
    def __init__(self, app_state: AppState, tooltip: str | None = None) -> None:
        self.app_state = app_state
        self.icon: pystray.Icon | None = None
        self.tooltip = tooltip.strip() if tooltip else APP_NAME

    # 有効/無効状態に応じたトレイアイコン画像を生成
    def create_image(self, enabled: bool = True) -> Image.Image:
        bg = "black" if enabled else "gray"
        fg = "white"

        image = Image.new("RGB", (64, 64), bg)
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 16, 48, 48), fill=fg)
        return image

    # 現在の有効・録音・モード状態をまとめたステータス文字列を返す
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

    # 入力モード表示ラベルを返す
    def get_input_mode_label(self, item=None) -> str:
        with self.app_state.lock:
            input_mode = self.app_state.input_mode
        mode_text = "Push2Talk" if input_mode == "p2t" else "Toggle"
        return f"Input Mode: {mode_text}"

    # スタートアップ登録状態ラベルを返す
    def get_startup_status_label(self, item=None) -> str:
        return (
            "Startup: Registered"
            if is_startup_registered()
            else "Startup: Not Registered"
        )

    # トレイの右クリックメニューを構築して返す
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

    # アイコン・タイトル・メニューをAppStateに合わせて再描画
    def refresh(self) -> None:
        if self.icon is None:
            return

        with self.app_state.lock:
            enabled = self.app_state.enabled

        self.icon.icon = self.create_image(enabled=enabled)
        self.icon.title = f"{self.tooltip} | {self.get_status_title()}"
        self.icon.menu = self.build_menu()
        self.icon.update_menu()

    # 音声入力の有効/無効をトグル
    def toggle_enabled(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.enabled = not self.app_state.enabled
            enabled = self.app_state.enabled

        logger.info("Voice input %s", "enabled" if enabled else "disabled")
        self.refresh()

    # スタートアップ登録スクリプトを実行
    def register_startup(self, icon: pystray.Icon, item) -> None:
        if run_startup_script("install_startup.ps1"):
            logger.info("Startup registration completed")
        else:
            logger.warning("Startup registration failed")
        self.refresh()

    # スタートアップ登録解除スクリプトを実行
    def unregister_startup(self, icon: pystray.Icon, item) -> None:
        if run_startup_script("uninstall_startup.ps1"):
            logger.info("Startup unregistration completed")
        else:
            logger.warning("Startup unregistration failed")
        self.refresh()

    # AppStateにexit要求をセットしてトレイを停止
    def request_exit(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.should_exit = True
        logger.info("Exit requested from tray")
        icon.stop()

    # PILのPNGエンコーダとC拡張をメインスレッドで事前ロード
    # frozen実行時、pystrayスレッドからの初回PNGシリアライズで
    # アーカイブ遅延展開とaccess violationが発生するのを回避する
    def prewarm_icon_encoder(self) -> None:
        try:
            self.create_image(enabled=True).save(io.BytesIO(), format="PNG")
        except Exception as error:
            logger.warning("Icon encoder prewarm failed: %s", error)

    # トレイアイコンを初期化して起動（ブロッキング）
    def start(self) -> None:
        with self.app_state.lock:
            enabled = self.app_state.enabled

        self.icon = pystray.Icon(
            "whisper_tamas_ui",
            self.create_image(enabled=enabled),
            self.tooltip,
        )
        self.icon.menu = self.build_menu()
        self.icon.title = f"{self.tooltip} | {self.get_status_title()}"
        self.icon.run()

    # トレイアイコンを停止
    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()

    # 入力モードをPush2Talkに切替
    def set_input_mode_p2t(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.input_mode = "p2t"
        logger.info("Input mode switched to Push2Talk")
        self.refresh()

    # 入力モードをToggleに切替
    def set_input_mode_toggle(self, icon: pystray.Icon, item) -> None:
        with self.app_state.lock:
            self.app_state.input_mode = "toggle"
        logger.info("Input mode switched to Toggle")
        self.refresh()

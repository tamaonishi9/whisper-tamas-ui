import subprocess
import sys
import winreg
from pathlib import Path

APP_NAME = "WhisperTamas"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


# 凍結実行ファイルとスクリプト起動の両方に対応したベースディレクトリを返す
def get_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# スタートアップスクリプトの絶対パスを返す
def get_startup_script_path(script_name: str) -> Path:
    return get_app_base_dir() / script_name


# WindowsレジストリのRunキーにアプリが登録済みか確認する
def is_startup_registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        return False

    return bool(str(value).strip())


# PowerShellスクリプトを隠しウィンドウで実行し、成否を返す
def run_startup_script(script_name: str) -> bool:
    script_path = get_startup_script_path(script_name)
    if not script_path.is_file():
        return False

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(script_path),
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return False

    return completed.returncode == 0

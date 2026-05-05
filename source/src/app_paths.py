import sys
import os
import shutil
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).parent.parent


def _user_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".local" / "share"
    return base / "ScadenzarioCV"


def get_asset_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "asset"
    return _project_root() / "asset"


def get_data_dir() -> Path:
    if not getattr(sys, 'frozen', False):
        return _project_root() / "mock_data"

    user_data = _user_data_dir()
    if not user_data.exists():
        bundle_mock = Path(sys._MEIPASS) / "mock_data"
        shutil.copytree(bundle_mock, user_data)
    return user_data

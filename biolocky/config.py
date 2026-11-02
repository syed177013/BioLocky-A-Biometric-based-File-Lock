"""Paths and persisted (non-sensitive) preferences."""
import json
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)                       # running as a PyInstaller EXE
_SRC = Path(__file__).resolve().parent.parent
BUNDLE = Path(getattr(sys, "_MEIPASS", _SRC))                 # read-only bundled assets
APP_DIR = Path(sys.executable).parent if FROZEN else _SRC     # user-writable, next to the EXE
HOME = Path(os.environ.get("BIOLOCKY_HOME", APP_DIR / "vault_data"))
LEGACY_DIR = Path(os.environ.get("BIOLOCKY_LEGACY", APP_DIR))
RES_DIR = BUNDLE / "resources"
ICON_DIR = BUNDLE / "icons"
ASSET_DIR = BUNDLE
# PLACEHOLDER: drop your icon here (.png works everywhere; .ico also used on Windows). Missing file is ignored.
APP_ICON = BUNDLE / "app_icon.png"
GITHUB_URL = "https://github.com/syed177013/BioLocky-A-Biometric-based-File-Lock"

DEFAULTS = {
    "theme": "System",        # Light | Dark | System
    "autolock_min": 5,        # 0 = never
    "relock_sec": 120,        # opened files are wiped after this
    "move_on_import": True,   # delete original after verified import
    "voice_lang": "en-IN",
    "face_threshold": 0.72,
    "sort_key": "name",       # name | added | created | modified | type | size
    "sort_desc": False,
    "keep_unlocked": True,    # one successful auth opens every file until the vault locks
}


class Settings:
    def __init__(self, path: Path):
        self.path = path
        self.data = dict(DEFAULTS)
        try:
            self.data.update(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError):
            pass

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), "utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass
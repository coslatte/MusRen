import json
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".musren"
CONFIG_FILE = CONFIG_DIR / "config.json"

VALID_KEYS = {
    "acoustid": "AcoustID API key for audio recognition",
    "shazam": "Shazam API credentials (future)",
    "musicbrainz": "MusicBrainz credentials (future)",
    "lastfm": "Last.fm API key (future)",
}

DEFAULT_SETTINGS = {
    "theme": "dark",
    "auto_confirm": False,
    "recursive": False,
}


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE
        self.config_dir = CONFIG_DIR
        self._config: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            except json.JSONDecodeError:
                self._config = {}
        else:
            self._config = {}

    def _save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        if key in VALID_KEYS:
            return self._config.get("keys", {}).get(key, default)
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        if key in VALID_KEYS:
            if "keys" not in self._config:
                self._config["keys"] = {}
            self._config["keys"][key] = value
        else:
            self._config[key] = value
        self._save()
        return True

    def delete(self, key: str) -> bool:
        if key in VALID_KEYS:
            if "keys" in self._config and key in self._config["keys"]:
                del self._config["keys"][key]
                self._save()
                return True
            return False
        if key in self._config:
            del self._config[key]
            self._save()
            return True
        return False

    def list_keys(self) -> Dict[str, str]:
        return self._config.get("keys", {})

    def list_all(self) -> Dict[str, Any]:
        result = dict(self._config)
        result["_valid_keys"] = list(VALID_KEYS.keys())
        return result

    def clear(self) -> bool:
        self._config = {}
        if self.config_path.exists():
            self.config_path.unlink()
        return True

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._config.get("settings", {}).get(key, default)

    def set_setting(self, key: str, value: Any) -> bool:
        if "settings" not in self._config:
            self._config["settings"] = {}
        self._config["settings"][key] = value
        self._save()
        return True


_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

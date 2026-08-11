from __future__ import annotations

from PySide6.QtCore import QSettings


class AppSettings:
    def __init__(self) -> None:
        self._settings = QSettings("LINLin640", "EtherCAT Workbench")

    def value(self, key: str, default: object = None) -> object:
        return self._settings.value(key, default)

    def set_value(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)

    @property
    def auto_reset_esc(self) -> bool:
        return self._settings.value("eeprom/auto_reset_esc", True, type=bool)

    @auto_reset_esc.setter
    def auto_reset_esc(self, value: bool) -> None:
        self._settings.setValue("eeprom/auto_reset_esc", value)

    @property
    def recent_esi(self) -> list[str]:
        value = self._settings.value("esi/recent", [])
        return [str(item) for item in (value if isinstance(value, list) else [value]) if item]

    def remember_esi(self, path: str) -> None:
        values = [path, *(item for item in self.recent_esi if item != path)][:10]
        self._settings.setValue("esi/recent", values)

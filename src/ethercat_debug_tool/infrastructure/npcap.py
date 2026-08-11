from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path

NPCAP_REQUIRED_VERSION = (1, 88)
NPCAP_DOWNLOAD_URL = "https://npcap.com/dist/npcap-1.88.exe"


@dataclass(frozen=True, slots=True)
class NpcapStatus:
    installed: bool
    compatible: bool
    version: tuple[int, ...] | None

    @property
    def version_text(self) -> str:
        return ".".join(str(part) for part in self.version) if self.version else "未知"

    @property
    def ready(self) -> bool:
        return (
            self.installed
            and self.compatible
            and self.version is not None
            and self.version >= NPCAP_REQUIRED_VERSION
        )

    @property
    def guidance(self) -> str:
        if not self.installed:
            return "未检测到 Npcap。"
        if self.version is None:
            return "已检测到 Npcap，但无法确认版本。"
        if self.version < NPCAP_REQUIRED_VERSION:
            return f"Npcap {self.version_text} 低于所需的 1.88。"
        if not self.compatible:
            return "Npcap 未启用 WinPcap API-compatible Mode。"
        return f"Npcap {self.version_text} 已就绪，WinPcap 兼容模式可用。"


def parse_version(value: str) -> tuple[int, ...] | None:
    parts: list[int] = []
    for item in value.replace(",", ".").split("."):
        digits = "".join(char for char in item if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if len(parts) >= 2 else None


def _file_version(path: Path) -> tuple[int, ...] | None:
    if os.name != "nt" or not path.is_file():
        return None
    size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    translation_pointer = ctypes.c_void_p()
    translation_length = ctypes.c_uint()
    if not ctypes.windll.version.VerQueryValueW(
        buffer,
        "\\VarFileInfo\\Translation",
        ctypes.byref(translation_pointer),
        ctypes.byref(translation_length),
    ):
        return None
    word_count = translation_length.value // ctypes.sizeof(ctypes.c_ushort)
    translations = ctypes.cast(
        translation_pointer, ctypes.POINTER(ctypes.c_ushort * word_count)
    ).contents
    for index in range(0, word_count - 1, 2):
        prefix = f"\\StringFileInfo\\{translations[index]:04x}{translations[index + 1]:04x}"
        for field in ("ProductVersion", "FileVersion"):
            value_pointer = ctypes.c_void_p()
            value_length = ctypes.c_uint()
            if ctypes.windll.version.VerQueryValueW(
                buffer,
                prefix + "\\" + field,
                ctypes.byref(value_pointer),
                ctypes.byref(value_length),
            ):
                parsed = parse_version(ctypes.wstring_at(value_pointer, value_length.value).rstrip("\x00"))
                if parsed is not None:
                    return parsed
    return None


def detect_npcap() -> NpcapStatus:
    if os.name != "nt":
        return NpcapStatus(False, False, None)
    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    npcap_dir = windows / "System32" / "Npcap"
    packet = npcap_dir / "Packet.dll"
    native_wpcap = npcap_dir / "wpcap.dll"
    compatible_wpcap = windows / "System32" / "wpcap.dll"
    installed = packet.is_file() and native_wpcap.is_file()
    return NpcapStatus(installed, compatible_wpcap.is_file(), _file_version(packet))

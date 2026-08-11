from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files


class RegisterFamily(StrEnum):
    ET1100_COMPATIBLE = "ET1100_COMPATIBLE"
    LAN9252_COMPATIBLE = "LAN9252_COMPATIBLE"
    LAN9253_COMPATIBLE = "LAN9253_COMPATIBLE"
    GENERIC = "GENERIC"


@dataclass(frozen=True, slots=True)
class EscProfile:
    chip_model: str
    register_family: RegisterFamily
    manufacturer: str
    pram_start: int | None
    pram_end: int | None
    fixed_fmmu_count: int | None
    fixed_sm_count: int | None
    reset_supported: bool
    reset_register: int = 0x0040
    reset_sequence: bytes = b"RES"
    documentation: str = ""
    limitations: tuple[str, ...] = ()


class ProfileRegistry:
    def __init__(self) -> None:
        unverified = ("厂商数据手册未提供；厂商专属寄存器和 EEPROM 行为未验证",)
        self._profiles = {
            "E101": EscProfile(
                "E101",
                RegisterFamily.ET1100_COMPATIBLE,
                "国产",
                0x1000,
                0x2FFF,
                8,
                8,
                True,
                limitations=unverified,
            ),
            "E252": EscProfile(
                "E252",
                RegisterFamily.LAN9252_COMPATIBLE,
                "国产",
                0x1000,
                0x2FFF,
                8,
                8,
                True,
                limitations=unverified,
            ),
            "E253": EscProfile(
                "E253",
                RegisterFamily.LAN9253_COMPATIBLE,
                "国产",
                0x1000,
                0x2FFF,
                8,
                8,
                True,
                limitations=unverified,
            ),
            "ET1100": EscProfile(
                "ET1100",
                RegisterFamily.ET1100_COMPATIBLE,
                "Beckhoff",
                None,
                None,
                None,
                None,
                True,
                documentation="ET1100 EtherCAT Slave Controller documentation",
            ),
            "LAN9252": EscProfile(
                "LAN9252",
                RegisterFamily.LAN9252_COMPATIBLE,
                "Microchip",
                None,
                None,
                None,
                None,
                True,
                documentation="Microchip LAN9252 datasheet",
            ),
            "LAN9253": EscProfile(
                "LAN9253",
                RegisterFamily.LAN9253_COMPATIBLE,
                "Microchip",
                None,
                None,
                None,
                None,
                True,
                documentation="Microchip LAN9253 datasheet",
            ),
            "Generic ESC": EscProfile(
                "Generic ESC",
                RegisterFamily.GENERIC,
                "Unknown",
                None,
                None,
                None,
                None,
                False,
                limitations=("仅提供 EtherCAT 公共寄存器和原始访问",),
            ),
        }

    def get(self, chip_model: str) -> EscProfile:
        return self._profiles.get(chip_model, self._profiles["Generic ESC"])

    def resolve(self, *, esi_type: str | None = None, chip_register: bytes | None = None) -> EscProfile:
        candidates = " ".join(
            filter(
                None,
                (
                    esi_type,
                    chip_register.rstrip(b"\x00").decode("ascii", errors="ignore") if chip_register else None,
                ),
            )
        ).upper()
        for name in ("E101", "E252", "E253", "LAN9252", "LAN9253", "ET1100"):
            if name in candidates:
                return self._profiles[name]
        if chip_register:
            value = int.from_bytes(chip_register, "little")
            for name in ("E101", "E252", "E253"):
                if value == int(name, 16):
                    return self._profiles[name]
        return self._profiles["Generic ESC"]

    @staticmethod
    def standard_registers() -> list[dict[str, object]]:
        resource = files("ethercat_debug_tool.esc_profiles.data").joinpath("standard_registers.json")
        return json.loads(resource.read_text(encoding="utf-8"))

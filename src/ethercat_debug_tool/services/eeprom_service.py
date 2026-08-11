from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..backends.base import EtherCatBackend
from ..esi.parser import EsiDevice
from ..models import EepromBackup, OperationProgress, SlaveInfo
from ..sii.parser import SiiImage, SiiParser
from .register_service import ResetService

ProgressCallback = Callable[[OperationProgress], None]
CancelCallback = Callable[[], bool]


class EepromOperationCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EepromComparison:
    equal: bool
    differing_bytes: int
    first_difference: int | None
    target_sha256: str
    readback_sha256: str


@dataclass(frozen=True, slots=True)
class EepromFlashResult:
    backup: EepromBackup
    bytes_read_back: int
    words_written: int
    comparison: EepromComparison
    sii_valid: bool
    semantic_valid: bool
    image_verification: str
    reset_sequence: tuple[bool, bool, bool] | None
    rediscovered: bool | None
    reload_verified: bool | None

    @property
    def image_success(self) -> bool:
        return self.comparison.equal and self.sii_valid and self.semantic_valid


def compare_images(target: bytes, readback: bytes) -> EepromComparison:
    common = min(len(target), len(readback))
    differences = sum(a != b for a, b in zip(target[:common], readback[:common], strict=True))
    differences += abs(len(target) - len(readback))
    first = next((i for i, (a, b) in enumerate(zip(target, readback, strict=False)) if a != b), None)
    if first is None and len(target) != len(readback):
        first = common
    return EepromComparison(
        differences == 0,
        differences,
        first,
        hashlib.sha256(target).hexdigest(),
        hashlib.sha256(readback).hexdigest(),
    )


class EepromService:
    """Runs as a single exclusive Worker task; never call it from the GUI thread."""

    def __init__(
        self,
        backend: EtherCatBackend,
        *,
        stability_wait_s: float = 10.0,
        rediscovery_wait_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.backend = backend
        self.stability_wait_s = stability_wait_s
        self.rediscovery_wait_s = rediscovery_wait_s
        self.sleep = sleep
        self.parser = SiiParser()

    @staticmethod
    def _check_cancel(cancel: CancelCallback) -> None:
        if cancel():
            raise EepromOperationCancelled("EEPROM operation was safely cancelled between EtherCAT requests")

    @staticmethod
    def capacity_from_size_word(size_word: int) -> int:
        capacity = (size_word + 1) * 128
        if not 128 <= capacity <= 16 * 1024 * 1024:
            raise ValueError(f"EEPROM capacity field is unreasonable: {capacity} bytes")
        return capacity

    def read_capacity(self, position: int) -> int:
        size_and_version = self.backend.eeprom_read(position, 0x3E)
        if len(size_and_version) < 2:
            raise RuntimeError("EEPROM size word could not be read")
        return self.capacity_from_size_word(int.from_bytes(size_and_version[:2], "little"))

    def read_full(
        self,
        position: int,
        *,
        progress: ProgressCallback = lambda _: None,
        cancel: CancelCallback = lambda: False,
    ) -> bytes:
        capacity = self.read_capacity(position)
        result = bytearray()
        for byte_offset in range(0, capacity, 4):
            self._check_cancel(cancel)
            chunk = self.backend.eeprom_read(position, byte_offset // 2)
            if len(chunk) != 4:
                raise RuntimeError(f"EEPROM returned {len(chunk)} bytes; expected four")
            result.extend(chunk)
            progress(
                OperationProgress(
                    "eeprom-read", "read", min(byte_offset + 4, capacity), capacity, f"0x{byte_offset:04X}"
                )
            )
        return bytes(result[:capacity])

    def backup(
        self,
        position: int,
        directory: Path,
        slave: SlaveInfo,
        *,
        progress: ProgressCallback = lambda _: None,
        cancel: CancelCallback = lambda: False,
    ) -> EepromBackup:
        raw = self.read_full(position, progress=progress, cancel=cancel)
        parsed = self.parser.parse(raw)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        base = directory / f"slave{position}_{slave.identity.product_code:08X}_{stamp}"
        binary_path = base.with_suffix(".bin")
        metadata_path = base.with_suffix(".json")
        binary_path.write_bytes(raw)
        metadata = {
            "created_utc": datetime.now(UTC).isoformat(),
            "slave": asdict(slave),
            "size": len(raw),
            "sha256": parsed.sha256,
            "sii": {
                "vendor_id": parsed.vendor_id,
                "product_code": parsed.product_code,
                "revision": parsed.revision,
                "serial_number": parsed.serial_number,
                "version": parsed.version,
                "category_count": len(parsed.categories),
            },
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        return EepromBackup(binary_path, metadata_path, parsed.sha256, len(raw))

    @staticmethod
    def different_words(current: bytes, target: bytes) -> tuple[int, ...]:
        if len(current) != len(target) or len(target) % 2:
            raise ValueError("EEPROM images must have the same even size")
        return tuple(
            offset // 2
            for offset in range(0, len(target), 2)
            if current[offset : offset + 2] != target[offset : offset + 2]
        )

    @staticmethod
    def semantic_matches(image: SiiImage, device: EsiDevice) -> bool:
        if (image.vendor_id, image.product_code, image.revision, image.serial_number) != (
            device.vendor_id,
            device.product_code,
            device.revision,
            device.serial_number,
        ):
            return False
        kinds = {category.kind for category in image.categories}
        required = {0x000A, 0x001E}
        if device.fmmu:
            required.add(0x0028)
        if device.sync_managers:
            required.add(0x0029)
        if device.tx_pdos:
            required.add(0x0032)
        if device.rx_pdos:
            required.add(0x0033)
        if device.dc_modes:
            required.add(0x003C)
        expected_names = {
            device.name,
            device.type_name,
            *(pdo.name for pdo in (*device.tx_pdos, *device.rx_pdos)),
        }
        return required <= kinds and all(not name or name in image.strings for name in expected_names)

    def flash(
        self,
        position: int,
        target: bytes,
        device: EsiDevice,
        backup_dir: Path,
        slave: SlaveInfo,
        *,
        auto_reset: bool = True,
        progress: ProgressCallback = lambda _: None,
        cancel: CancelCallback = lambda: False,
    ) -> EepromFlashResult:
        self.parser.parse(target)
        if len(target) != self.read_capacity(position):
            raise ValueError("Target image size does not match the physical EEPROM capacity")
        # A complete valid backup is mandatory and happens before the first write.
        backup = self.backup(position, backup_dir, slave, progress=progress, cancel=cancel)
        current = backup.binary_path.read_bytes()
        words = self.different_words(current, target)
        total = len(words)
        for completed, word in enumerate(words, 1):
            self._check_cancel(cancel)
            expected = target[word * 2 : word * 2 + 2]
            self.backend.eeprom_write(position, word, expected)
            if self.backend.eeprom_read(position, word)[:2] != expected:
                raise RuntimeError(f"EEPROM batch verification failed at word 0x{word:04X}")
            progress(
                OperationProgress("eeprom-flash", "write-verify", completed, total, f"word 0x{word:04X}")
            )

        # This wait is intentionally not cancellable: it is a mandatory stability stage.
        progress(
            OperationProgress(
                "eeprom-flash", "stability-wait", 0, 1, f"mandatory {self.stability_wait_s:g} second wait"
            )
        )
        self.sleep(self.stability_wait_s)
        readback = self.read_full(position, progress=progress, cancel=lambda: False)
        comparison = compare_images(target, readback)
        readback_parsed = self.parser.parse(readback)
        semantic_valid = self.semantic_matches(readback_parsed, device)
        verification = (
            "逐字节、SHA-256、SII 结构与 XML 身份语义均通过"
            if (comparison.equal and semantic_valid)
            else "镜像验证失败"
        )
        reset: tuple[bool, bool, bool] | None = None
        rediscovered: bool | None = None
        reload_verified: bool | None = None
        if comparison.equal and semantic_valid and auto_reset:
            # The three calls below are adjacent inside this exclusive Worker operation.
            reset = ResetService(self.backend).reset_ecat(position)
            # A temporary drop after reset is expected and never rewrites the image result.
            self.sleep(self.rediscovery_wait_s)
            try:
                rediscovered = any(item.position == position for item in self.backend.scan())
            except Exception:
                rediscovered = False
            if rediscovered:
                try:
                    reload = self.read_full(position, progress=progress, cancel=lambda: False)
                    reload_image = self.parser.parse(reload)
                    reload_verified = compare_images(target, reload).equal and self.semantic_matches(
                        reload_image, device
                    )
                except Exception:
                    reload_verified = False
        return EepromFlashResult(
            backup,
            len(readback),
            total,
            comparison,
            True,
            semantic_valid,
            verification,
            reset,
            rediscovered,
            reload_verified,
        )

    def restore(
        self, position: int, backup_path: Path, backup_dir: Path, slave: SlaveInfo, **kwargs: object
    ) -> EepromFlashResult:
        raw = backup_path.read_bytes()
        parsed = self.parser.parse(raw)
        # Restores still make a fresh mandatory backup. Semantic target uses current backup identity.
        synthetic = EsiDevice(
            0,
            "",
            "",
            "",
            parsed.vendor_id,
            parsed.product_code,
            parsed.revision,
            parsed.serial_number,
            len(raw),
            b"",
            b"",
            (),
            (),
            (),
            (),
            (),
            None,
            None,
            None,
            "",
            0,
            0,
            0,
        )
        return self.flash(position, raw, synthetic, backup_dir, slave, **kwargs)  # type: ignore[arg-type]

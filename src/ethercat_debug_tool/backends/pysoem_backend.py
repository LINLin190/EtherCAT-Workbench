from __future__ import annotations

import ctypes.util
import time
from dataclasses import replace
from typing import Any

from ..models import (
    AdapterInfo,
    EtherCatState,
    ObjectDictionaryEntry,
    PdoDirection,
    PdoEntry,
    ProcessDataSnapshot,
    SlaveIdentity,
    SlaveInfo,
)
from .base import CommunicationError, EnvironmentError


def _decode_adapter_description(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _chip_from_register(
    raw: bytes,
    *,
    fmmu_count: int | None = None,
    sm_count: int | None = None,
    ram_kib: int | None = None,
) -> tuple[str, str]:
    text = raw.rstrip(b"\x00").decode("ascii", errors="ignore").upper()
    value = int.from_bytes(raw, "little")
    candidates = {"E101": "ET1100_COMPATIBLE", "E252": "LAN9252_COMPATIBLE", "E253": "LAN9253_COMPATIBLE"}
    for model, family in candidates.items():
        if model in text or value == int(model, 16):
            return model, family
    # LAN9252 exposes 3 FMMUs, 4 SyncManagers and 4 KiB DPRAM. This
    # capability signature is used only for the original Microchip part;
    # domestic compatible models remain identifiable solely by model text
    # or their explicit chip register value above.
    if (fmmu_count, sm_count, ram_kib) == (3, 4, 4):
        return "LAN9252", "LAN9252_COMPATIBLE"
    return "Generic ESC", "GENERIC"


class PysoemBackend:
    """Thin pySOEM adapter. Every method must be invoked only by EtherCatWorker."""

    def __init__(self) -> None:
        self._pysoem: Any = None
        self._master: Any = None
        self._connected = False
        self._mapped = False
        self._slaves: list[SlaveInfo] = []
        self._cycle_count = 0
        self._wkc_errors = 0
        self._timeouts = 0
        self._consecutive = 0

    @property
    def connected(self) -> bool:
        return self._connected

    def _load(self) -> Any:
        if self._pysoem is None:
            try:
                import pysoem
            except (ImportError, OSError) as exc:
                raise EnvironmentError(
                    "无法加载 pySOEM/Npcap。请安装 pysoem==1.1.13 和 Npcap，并启用 WinPcap API-compatible Mode。"
                ) from exc
            if pysoem.__version__ != "1.1.13":
                raise EnvironmentError(f"需要 pysoem 1.1.13，当前为 {pysoem.__version__}")
            self._pysoem = pysoem
        return self._pysoem

    def enumerate_adapters(self) -> list[AdapterInfo]:
        pysoem = self._load()
        try:
            adapters = pysoem.find_adapters()
        except (OSError, RuntimeError) as exc:
            raise EnvironmentError(
                "无法枚举网卡。请确认 Npcap 已安装并启用 WinPcap API-compatible Mode。"
            ) from exc
        return [AdapterInfo(a.name, _decode_adapter_description(a.desc)) for a in adapters]

    def connect(self, adapter_name: str) -> None:
        pysoem = self._load()
        master = pysoem.Master()
        master.always_release_gil = True
        try:
            master.open(adapter_name)
        except (ConnectionError, OSError) as exc:
            hint = "请检查网卡状态、管理员权限以及 Npcap 的 WinPcap 兼容模式。"
            if ctypes.util.find_library("wpcap") is None:
                hint = "未检测到 Npcap/wpcap，请安装 Npcap 并启用 WinPcap API-compatible Mode。"
            raise EnvironmentError(f"无法打开 EtherCAT 网卡。{hint}") from exc
        self._master = master
        self._connected = True
        self._mapped = False

    def disconnect(self) -> None:
        if self._master is not None:
            try:
                self._master.close()
            finally:
                self._master = None
        self._connected = False
        self._mapped = False
        self._slaves = []

    def _require_master(self) -> Any:
        if not self._connected or self._master is None:
            raise CommunicationError("Master is not connected")
        return self._master

    def _slave(self, position: int) -> Any:
        master = self._require_master()
        if not 1 <= position <= len(master.slaves):
            raise CommunicationError(f"Slave {position} is not available")
        return master.slaves[position - 1]

    def _serial(self, slave: Any) -> int:
        try:
            return int.from_bytes(slave.sdo_read(0x1018, 4, ca=False, release_gil=True), "little")
        except Exception:
            try:
                return int.from_bytes(slave.eeprom_read(0x0E), "little")
            except Exception:
                return 0

    def _pdo_size(self, position: int, direction: PdoDirection) -> int:
        try:
            bits = sum(entry.bit_length for entry in self.read_pdo_mapping(position, direction))
            return (bits + 7) // 8
        except CommunicationError:
            return 0

    def _info(self, position: int, slave: Any) -> SlaveInfo:
        configured_address = None
        chip_model, family = "Generic ESC", "GENERIC"
        try:
            configured_address = int.from_bytes(slave._fprd(0x0010, 2, 4000), "little")
        except Exception:
            pass
        chip_raw = b""
        try:
            chip_raw = slave._fprd(0x0E00, 4, 4000)
        except Exception:
            # Some ESCs reject reads in the 0x0E00 area; the capability
            # signature below still identifies original vendor chips.
            pass
        try:
            capabilities = slave._fprd(0x0004, 3, 4000)
        except Exception:
            capabilities = None
        if capabilities is not None or chip_raw:
            chip_model, family = _chip_from_register(
                chip_raw,
                fmmu_count=capabilities[0] if capabilities is not None else None,
                sm_count=capabilities[1] if capabilities is not None else None,
                ram_kib=capabilities[2] if capabilities is not None else None,
            )
        try:
            state = EtherCatState(int(slave.state) & 0x0F)
        except ValueError:
            state = EtherCatState.NONE
        return SlaveInfo(
            position,
            slave.name,
            SlaveIdentity(slave.man, slave.id, slave.rev, self._serial(slave)),
            state,
            int(slave.al_status),
            self._pdo_size(position, PdoDirection.TX),
            self._pdo_size(position, PdoDirection.RX),
            configured_address,
            chip_model,
            family,
        )

    def scan(self) -> list[SlaveInfo]:
        master = self._require_master()
        try:
            count = master.config_init(False, release_gil=True)
        except Exception as exc:
            raise CommunicationError(f"扫描从站失败：{exc}") from exc
        if count <= 0:
            self._slaves = []
            return []
        self._slaves = [self._info(i, slave) for i, slave in enumerate(master.slaves, 1)]
        return list(self._slaves)

    def read_states(self) -> list[SlaveInfo]:
        master = self._require_master()
        master.read_state()
        self._slaves = [self._info(i, slave) for i, slave in enumerate(master.slaves, 1)]
        return list(self._slaves)

    def request_state(self, position: int | None, state: EtherCatState, timeout_us: int) -> list[SlaveInfo]:
        master = self._require_master()
        target = master if position is None else self._slave(position)
        if state is EtherCatState.OP and self._mapped:
            master.send_processdata(release_gil=True)
            master.receive_processdata(2000, release_gil=True)
        target.state = int(state)
        target.write_state()
        actual = target.state_check(int(state), timeout_us)
        if (actual & 0x0F) != int(state):
            self.read_states()
            raise CommunicationError(f"State transition to {state.label} failed (actual 0x{actual:02X})")
        return self.read_states()

    def reconfig(self, position: int, timeout_us: int) -> bool:
        return bool(self._slave(position).reconfig(timeout_us))

    def recover(self, position: int, timeout_us: int) -> bool:
        return bool(self._slave(position).recover(timeout_us))

    @staticmethod
    def _normalize_error(exc: Exception, operation: str) -> CommunicationError:
        abort = getattr(exc, "abort_code", None)
        desc = getattr(exc, "desc", None) or getattr(exc, "message", None) or str(exc)
        suffix = f" (0x{abort:08X})" if abort is not None else ""
        return CommunicationError(f"{operation} failed{suffix}: {desc}")

    def sdo_read(self, position: int, index: int, subindex: int, size: int = 0) -> bytes:
        try:
            return self._slave(position).sdo_read(index, subindex, size=size, ca=False, release_gil=True)
        except Exception as exc:
            raise self._normalize_error(exc, f"SDO read 0x{index:04X}:{subindex:02X}") from exc

    def sdo_write(self, position: int, index: int, subindex: int, data: bytes) -> None:
        try:
            self._slave(position).sdo_write(index, subindex, bytes(data), ca=False, release_gil=True)
        except Exception as exc:
            raise self._normalize_error(exc, f"SDO write 0x{index:04X}:{subindex:02X}") from exc

    def read_object_dictionary(self, position: int) -> list[ObjectDictionaryEntry]:
        result: list[ObjectDictionaryEntry] = []
        try:
            for obj in self._slave(position).od:
                entries = obj.entries
                for subindex, entry in enumerate(entries):
                    if entry.data_type > 0 and entry.bit_length > 0:
                        result.append(
                            ObjectDictionaryEntry(
                                obj.index,
                                subindex,
                                entry.name or obj.name,
                                entry.data_type,
                                entry.bit_length,
                                entry.obj_access,
                            )
                        )
        except Exception as exc:
            raise self._normalize_error(exc, "CoE SDO Info object dictionary") from exc
        return result

    def read_pdo_mapping(self, position: int, direction: PdoDirection) -> list[PdoEntry]:
        assignment = 0x1C12 if direction is PdoDirection.RX else 0x1C13
        count = int.from_bytes(self.sdo_read(position, assignment, 0), "little")
        result: list[PdoEntry] = []
        bit_offset = 0
        for assign_sub in range(1, count + 1):
            pdo_index = int.from_bytes(self.sdo_read(position, assignment, assign_sub), "little")
            entry_count = int.from_bytes(self.sdo_read(position, pdo_index, 0), "little")
            for entry_sub in range(1, entry_count + 1):
                value = int.from_bytes(self.sdo_read(position, pdo_index, entry_sub), "little")
                index, subindex, bits = (value >> 16) & 0xFFFF, (value >> 8) & 0xFF, value & 0xFF
                result.append(PdoEntry(direction, pdo_index, index, subindex, bits, bit_offset))
                bit_offset += bits
        return result

    def map_process_data(self) -> int:
        master = self._require_master()
        try:
            size = int(master.config_map())
        except Exception as exc:
            raise self._normalize_error(exc, "PDO mapping") from exc
        self._mapped = True
        self._slaves = [
            replace(info, input_size=len(master.slaves[i].input), output_size=len(master.slaves[i].output))
            for i, info in enumerate(self._slaves)
        ]
        return size

    def exchange_process_data(self, timeout_us: int) -> ProcessDataSnapshot:
        master = self._require_master()
        if not self._mapped:
            raise CommunicationError("Process data is not mapped")
        master.send_processdata(release_gil=True)
        actual = int(master.receive_processdata(timeout_us, release_gil=True))
        expected = int(master.expected_wkc)
        self._cycle_count += 1
        if actual <= 0:
            self._timeouts += 1
        if actual != expected:
            self._wkc_errors += 1
            self._consecutive += 1
        else:
            self._consecutive = 0
        return ProcessDataSnapshot(
            tuple(s.input for s in master.slaves),
            tuple(s.output for s in master.slaves),
            actual,
            expected,
            self._cycle_count,
            self._timeouts,
            self._wkc_errors,
            self._consecutive,
            time.time(),
        )

    def set_output(self, position: int, data: bytes) -> None:
        slave = self._slave(position)
        expected = len(slave.output)
        if len(data) != expected:
            raise ValueError(f"Output must be exactly {expected} bytes")
        slave.output = bytes(data)

    def eeprom_read(self, position: int, word_address: int) -> bytes:
        try:
            return self._slave(position).eeprom_read(word_address)
        except Exception as exc:
            raise self._normalize_error(exc, f"EEPROM read word 0x{word_address:04X}") from exc

    def eeprom_write(self, position: int, word_address: int, data: bytes) -> None:
        if len(data) != 2:
            raise ValueError("EEPROM writes are exactly one 16-bit word")
        try:
            self._slave(position).eeprom_write(word_address, bytes(data))
        except Exception as exc:
            raise self._normalize_error(exc, f"EEPROM write word 0x{word_address:04X}") from exc

    def register_read(self, position: int, address: int, size: int, timeout_us: int) -> bytes:
        if not 1 <= size <= 256 or not 0 <= address <= 0xFFFF or address + size > 0x10000:
            raise ValueError("Register range is invalid")
        try:
            return self._slave(position)._fprd(address, size, timeout_us)
        except Exception as exc:
            raise self._normalize_error(exc, f"FPRD 0x{address:04X}") from exc

    def register_write(self, position: int, address: int, data: bytes, timeout_us: int) -> None:
        if not data or not 0 <= address <= 0xFFFF or address + len(data) > 0x10000:
            raise ValueError("Register range is invalid")
        try:
            self._slave(position)._fpwr(address, bytes(data), timeout_us)
        except Exception as exc:
            raise self._normalize_error(exc, f"FPWR 0x{address:04X}") from exc

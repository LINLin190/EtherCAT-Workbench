from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


class EsiValidationError(ValueError):
    pass


def parse_number(value: str | None, *, default: int | None = None) -> int:
    if value is None or not value.strip():
        if default is None:
            raise EsiValidationError("Required numeric value is missing")
        return default
    text = value.strip()
    if text.lower().startswith("#x"):
        return int(text[2:], 16)
    return int(text, 0)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local(child.tag) == name]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next(iter(_children(element, name)), None)


def _text(element: ET.Element | None, default: str = "") -> str:
    return (element.text or "").strip() if element is not None else default


def _localized_name(element: ET.Element, fallback: str = "") -> str:
    names = _children(element, "Name")
    for preferred in (1033, 2052, 1031):
        for name in names:
            if parse_number(name.attrib.get("LcId"), default=0) == preferred and _text(name):
                return _text(name)
    return _text(names[0], fallback) if names else fallback


@dataclass(frozen=True, slots=True)
class EsiEntry:
    index: int
    subindex: int
    bit_length: int
    name: str
    data_type: str | None
    flags: int = 0


@dataclass(frozen=True, slots=True)
class EsiPdo:
    index: int
    name: str
    sync_manager: int | None
    entries: tuple[EsiEntry, ...]
    flags: int = 0


@dataclass(frozen=True, slots=True)
class EsiDcMode:
    name: str
    description: str
    assign_activate: int
    cycle_time_sync0: int
    shift_time_sync0: int
    cycle_time_sync1: int
    shift_time_sync1: int


@dataclass(frozen=True, slots=True)
class EsiSyncManager:
    start_address: int
    default_size: int
    control_byte: int
    enable: bool
    kind: str


@dataclass(frozen=True, slots=True)
class EsiObjectEntry:
    index: int
    subindex: int
    name: str
    data_type: str
    bit_length: int
    access: str


@dataclass(frozen=True, slots=True)
class EsiDevice:
    ordinal: int
    name: str
    type_name: str
    group_type: str
    vendor_id: int
    product_code: int
    revision: int
    serial_number: int
    byte_size: int
    config_data: bytes
    bootstrap: bytes
    fmmu: tuple[str, ...]
    sync_managers: tuple[EsiSyncManager, ...]
    rx_pdos: tuple[EsiPdo, ...]
    tx_pdos: tuple[EsiPdo, ...]
    dc_modes: tuple[EsiDcMode, ...]
    dpram_size: int | None
    fmmu_count: int | None
    sm_count: int | None
    physics: str
    coe_details: int
    mailbox_protocol: int
    general_flags: int
    objects: tuple[EsiObjectEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class EsiDocument:
    path: Path
    sha256: str
    vendor_id: int
    vendor_name: str
    devices: tuple[EsiDevice, ...]


class EsiParser:
    def parse(self, path: str | Path) -> EsiDocument:
        source = Path(path).resolve()
        try:
            raw = source.read_bytes()
            root = ET.fromstring(raw)
        except (OSError, ET.ParseError) as exc:
            raise EsiValidationError(f"Unable to parse ESI XML {source}: {exc}") from exc
        descriptions = next((node for node in root.iter() if _local(node.tag) == "Descriptions"), None)
        if descriptions is None:
            raise EsiValidationError("ESI XML does not contain Descriptions")
        vendor = _child(root, "Vendor")
        devices_node = _child(descriptions, "Devices")
        if vendor is None or devices_node is None:
            raise EsiValidationError("ESI XML must contain Vendor and Devices")
        vendor_id = parse_number(_text(_child(vendor, "Id")))
        vendor_name = _text(_child(vendor, "Name"), "Unknown vendor")
        devices = tuple(
            self._parse_device(i, element, vendor_id)
            for i, element in enumerate(_children(devices_node, "Device"))
        )
        if not devices:
            raise EsiValidationError("ESI XML contains no Device definitions")
        return EsiDocument(source, hashlib.sha256(raw).hexdigest(), vendor_id, vendor_name, devices)

    def _parse_device(self, ordinal: int, device: ET.Element, vendor_id: int) -> EsiDevice:
        type_element = _child(device, "Type")
        if type_element is None:
            raise EsiValidationError(f"Device {ordinal + 1} has no Type")
        type_name = _text(type_element)
        name = _localized_name(device, type_name)
        eeprom = _child(device, "Eeprom")
        if eeprom is None:
            raise EsiValidationError(f"Device {name} has no Eeprom section")
        byte_size = parse_number(_text(_child(eeprom, "ByteSize")))
        if byte_size <= 0 or byte_size % 2:
            raise EsiValidationError(f"Device {name} EEPROM ByteSize must be a positive even number")
        config_data = self._hex(_text(_child(eeprom, "ConfigData")), "ConfigData", name)
        bootstrap = self._hex(_text(_child(eeprom, "BootStrap")), "BootStrap", name, allow_empty=True)
        info = _child(device, "Info")
        controller = None
        if info is not None:
            controller = next((n for n in info.iter() if _local(n.tag) == "EtherCATController"), None)

        def ctl(name_: str) -> int | None:
            node = _child(controller, name_) if controller is not None else None
            return parse_number(_text(node), default=0) if node is not None else None

        return EsiDevice(
            ordinal,
            name,
            type_name,
            _text(_child(device, "GroupType")),
            vendor_id,
            parse_number(type_element.attrib.get("ProductCode")),
            parse_number(type_element.attrib.get("RevisionNo")),
            parse_number(type_element.attrib.get("SerialNo"), default=0),
            byte_size,
            config_data,
            bootstrap,
            tuple(_text(x) for x in _children(device, "Fmmu")),
            tuple(self._parse_sm(x) for x in _children(device, "Sm")),
            tuple(self._parse_pdo(x) for x in _children(device, "RxPdo")),
            tuple(self._parse_pdo(x) for x in _children(device, "TxPdo")),
            self._dc_modes(device),
            ctl("DpramSize"),
            ctl("FmmuCount"),
            ctl("SmCount"),
            device.attrib.get("Physics", ""),
            *self._mailbox(device, info),
            self._objects(device),
        )

    @staticmethod
    def _objects(device: ET.Element) -> tuple[EsiObjectEntry, ...]:
        profile = _child(device, "Profile")
        if profile is None:
            return ()
        dictionary = _child(profile, "Dictionary")
        if dictionary is None:
            return ()
        data_types_node = _child(dictionary, "DataTypes")
        type_nodes = (
            {}
            if data_types_node is None
            else {_text(_child(node, "Name")): node for node in _children(data_types_node, "DataType")}
        )
        objects_node = _child(dictionary, "Objects")
        if objects_node is None:
            return ()
        result: list[EsiObjectEntry] = []
        for obj in _children(objects_node, "Object"):
            index = parse_number(_text(_child(obj, "Index")))
            type_name = _text(_child(obj, "Type"))
            data_type = type_nodes.get(type_name)
            subitems = _children(data_type, "SubItem") if data_type is not None else []
            if subitems:
                for sub in subitems:
                    flags = _child(sub, "Flags")
                    result.append(
                        EsiObjectEntry(
                            index,
                            parse_number(_text(_child(sub, "SubIdx")), default=0),
                            _text(_child(sub, "Name")),
                            _text(_child(sub, "Type")),
                            parse_number(_text(_child(sub, "BitSize")), default=0),
                            _text(_child(flags, "Access") if flags is not None else None, "unknown"),
                        )
                    )
            else:
                flags = _child(obj, "Flags")
                result.append(
                    EsiObjectEntry(
                        index,
                        0,
                        _text(_child(obj, "Name")),
                        type_name,
                        parse_number(_text(_child(obj, "BitSize")), default=0),
                        _text(_child(flags, "Access") if flags is not None else None, "unknown"),
                    )
                )
        return tuple(result)

    @staticmethod
    def _hex(text: str, field: str, device: str, allow_empty: bool = False) -> bytes:
        if not text and allow_empty:
            return b""
        try:
            return bytes.fromhex("".join(text.split()))
        except ValueError as exc:
            raise EsiValidationError(f"Device {device} has invalid {field} hex data") from exc

    @staticmethod
    def _parse_sm(element: ET.Element) -> EsiSyncManager:
        return EsiSyncManager(
            parse_number(element.attrib.get("StartAddress")),
            parse_number(element.attrib.get("DefaultSize"), default=0),
            parse_number(element.attrib.get("ControlByte")),
            element.attrib.get("Enable", "0") not in {"0", "false", "False"},
            _text(element),
        )

    @staticmethod
    def _parse_pdo(element: ET.Element) -> EsiPdo:
        entries: list[EsiEntry] = []
        for entry in _children(element, "Entry"):
            index_node = _child(entry, "Index")
            flags = (
                0x1000
                if index_node is not None
                and index_node.attrib.get("DependOnSlot", "false").lower() in {"true", "1"}
                else 0
            )
            entries.append(
                EsiEntry(
                    parse_number(_text(_child(entry, "Index"))),
                    parse_number(_text(_child(entry, "SubIndex")), default=0),
                    parse_number(_text(_child(entry, "BitLen"))),
                    _localized_name(entry, ""),
                    _text(_child(entry, "DataType")) or None,
                    flags,
                )
            )
        sm_text = element.attrib.get("Sm")
        index_node = _child(element, "Index")
        flags = 0
        if element.attrib.get("Fixed", "false").lower() in {"true", "1"}:
            flags |= 0x0010
        if element.attrib.get("Mandatory", "false").lower() in {"true", "1"}:
            flags |= 0x0001
        if element.attrib.get("Virtual", "false").lower() in {"true", "1"}:
            flags |= 0x0020
        if index_node is not None and index_node.attrib.get("DependOnSlot", "false").lower() in {"true", "1"}:
            flags |= 0x0200
        return EsiPdo(
            parse_number(_text(_child(element, "Index"))),
            _localized_name(element, ""),
            parse_number(sm_text) if sm_text else None,
            tuple(entries),
            flags,
        )

    @staticmethod
    def _dc_modes(device: ET.Element) -> tuple[EsiDcMode, ...]:
        dc = _child(device, "Dc")
        if dc is None:
            return ()
        result = []
        for mode in _children(dc, "OpMode"):
            result.append(
                EsiDcMode(
                    _text(_child(mode, "Name")),
                    _text(_child(mode, "Desc")),
                    parse_number(_text(_child(mode, "AssignActivate")), default=0),
                    parse_number(_text(_child(mode, "CycleTimeSync0")), default=0),
                    parse_number(_text(_child(mode, "ShiftTimeSync0")), default=0),
                    parse_number(_text(_child(mode, "CycleTimeSync1")), default=0),
                    parse_number(_text(_child(mode, "ShiftTimeSync1")), default=0),
                )
            )
        return tuple(result)

    @staticmethod
    def _mailbox(device: ET.Element, info: ET.Element | None) -> tuple[int, int, int]:
        mailbox = _child(device, "Mailbox")
        if mailbox is None:
            return 0, 0, 0
        coe = _child(mailbox, "CoE")
        coe_details = 0
        if coe is not None:
            coe_details = 1
            for attribute, bit in (
                ("SdoInfo", 1),
                ("PdoAssign", 2),
                ("PdoConfig", 3),
                ("PdoUpload", 4),
                ("CompleteAccess", 5),
            ):
                if coe.attrib.get(attribute, "false").lower() in {"true", "1"}:
                    coe_details |= 1 << bit
        protocol = (1 << 2) if coe is not None else 0
        if _child(mailbox, "FoE") is not None:
            protocol |= 1 << 3
        if _child(mailbox, "EoE") is not None:
            protocol |= 1 << 1
        if _child(mailbox, "VoE") is not None:
            protocol |= 1 << 5
        flags = 0x04 if mailbox.attrib.get("DataLinkLayer", "false").lower() in {"true", "1"} else 0
        if (
            info is not None
            and _text(next((x for x in info.iter() if _local(x.tag) == "IdentificationReg134"), None)).lower()
            == "true"
        ):
            flags |= 0x08
        return coe_details, protocol, flags

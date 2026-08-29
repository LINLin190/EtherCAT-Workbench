from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AlStatusInfo:
    name: str
    detail: str
    action: str
    known: bool


@lru_cache(maxsize=1)
def _payload() -> dict[str, object]:
    path = Path(__file__).with_name("protocol") / "al_status_codes.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _catalog() -> dict[int, AlStatusInfo]:
    codes = _payload()["codes"]
    assert isinstance(codes, dict)
    return {
        int(code, 16): AlStatusInfo(
            name=str(value["name"]),
            detail=str(value["detail"]),
            action=str(value["action"]),
            known=True,
        )
        for code, value in codes.items()
    }


def _fallback(section: str, key: str | None = None) -> AlStatusInfo:
    value = _payload()[section]
    if key is not None:
        assert isinstance(value, dict)
        value = value[key]
    assert isinstance(value, dict)
    return AlStatusInfo(str(value["name"]), str(value["detail"]), str(value["action"]), False)


def al_status_info(code: int) -> AlStatusInfo:
    normalized = code & 0xFFFF
    if info := _catalog().get(normalized):
        return info
    if normalized >= 0x8000:
        return _fallback("ranges", "0x8000-0xFFFF")
    return _fallback("unknown")

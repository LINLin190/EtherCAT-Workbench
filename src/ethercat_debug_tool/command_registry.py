from __future__ import annotations

import dataclasses
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

Lane = Literal["control", "metadata", "hardware"]


@dataclasses.dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    lane: Lane
    timeout_ms: int
    mutating: bool


@dataclasses.dataclass(frozen=True, slots=True)
class CommandRegistry:
    protocol_version: int
    max_frame_bytes: int
    metadata_queue: int
    hardware_queue: int
    commands: dict[str, CommandSpec]

    def require(self, method: str) -> CommandSpec:
        try:
            return self.commands[method]
        except KeyError as exc:
            raise ValueError(f"Unknown bridge method: {method}") from exc


@lru_cache(maxsize=1)
def load_command_registry() -> CommandRegistry:
    path = Path(__file__).resolve().parent / "protocol" / "commands.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    commands = {
        name: CommandSpec(name, value["lane"], int(value["timeout_ms"]), bool(value["mutating"]))
        for name, value in data["commands"].items()
    }
    limits = data["limits"]
    return CommandRegistry(
        int(data["protocol_version"]),
        int(limits["max_frame_bytes"]),
        int(limits["metadata_queue"]),
        int(limits["hardware_queue"]),
        commands,
    )

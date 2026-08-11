from pathlib import Path

import pytest

from ethercat_debug_tool.esi.parser import EsiDocument, EsiParser


@pytest.fixture(scope="session")
def workspace() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def sample_esi(workspace: Path) -> EsiDocument:
    return EsiParser().parse(workspace / "ESI示例" / "SlaveCTT_900e80.xml")

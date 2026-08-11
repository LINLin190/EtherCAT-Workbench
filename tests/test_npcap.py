from ethercat_debug_tool.infrastructure.npcap import NpcapStatus, parse_version


def test_parse_npcap_version() -> None:
    assert parse_version("1.88") == (1, 88)
    assert parse_version("1,88,0,0") == (1, 88, 0, 0)
    assert parse_version("1.88 beta") == (1, 88)
    assert parse_version("unknown") is None


def test_npcap_status_requires_version_and_compatibility() -> None:
    assert NpcapStatus(True, True, (1, 88)).ready
    assert NpcapStatus(True, True, (1, 89)).ready
    assert not NpcapStatus(True, True, (1, 79)).ready
    assert not NpcapStatus(True, False, (1, 88)).ready
    assert not NpcapStatus(False, False, None).ready

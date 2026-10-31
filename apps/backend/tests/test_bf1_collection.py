import pytest
from app.api.errors import EAApiError
from app.services.bf1 import collection_service as cs


def _prog(unlocked: bool, acquired: float = 0.0, needed: float = 1.0) -> dict:
    return {"valueNeeded": needed, "valueAcquired": acquired, "unlocked": unlocked}


MEDALS = {
    "result": [
        {
            "name": "載具",
            "awards": [
                {
                    "code": "m05",
                    "progression": _prog(False),
                    "stages": [
                        {"code": "m05a", "progression": _prog(True, 1, 1)},
                        {"code": "m05b", "progression": _prog(True, 1, 1)},
                        {"code": "m05c", "progression": _prog(False)},
                    ],
                },
                {"code": "m06", "progression": _prog(True, 1, 1), "stages": []},
            ],
        },
        {"name": "空", "awards": None},
    ]
}

DOGTAGS = {
    "result": [
        {
            "name": "進度",
            "dogtags": [
                {"unlockId": "df082", "progression": _prog(True, 1, 1)},
                {"unlockId": "df083", "progression": _prog(False, 37, 100)},
                {"unlockId": "df084", "progression": _prog(False, 0, 1)},
                {"name": "没有 id 的条目"},
            ],
        }
    ]
}


def test_build_medals_counts_stages() -> None:
    got = [(m.code, m.unlocked, m.stages_done, m.stages_total) for m in cs._build_medals(MEDALS)]
    assert got == [("m05", False, 2, 3), ("m06", True, 0, 0)]


def test_build_dogtags_keeps_progress_only_when_meaningful() -> None:
    got = [(t.id, t.unlocked, t.acquired, t.needed) for t in cs._build_dogtags(DOGTAGS)]
    assert got == [
        ("df082", True, None, None),
        ("df083", False, 37, 100),
        ("df084", False, None, None),
    ]


@pytest.mark.parametrize("res", ["EA 报错", {"result": None}, {"error": {"code": -32000}}])
def test_bad_gateway_response_raises(res) -> None:
    with pytest.raises(EAApiError):
        cs._build_medals(res)
    with pytest.raises(EAApiError):
        cs._build_dogtags(res)


def test_build_equipped_reads_unlock_ids() -> None:
    # 2026-10-31 实测：result 是两块狗牌，文字跟着被查的人的语言走，只用 unlockId
    res = {
        "result": [
            {"name": "Palmier du désert", "unlockId": "dfxp111", "tagType": {"name": "Basic"}},
            {"name": "…", "unlockId": "db000", "tagType": {"name": "Advanced"}},
        ]
    }
    assert cs._build_equipped(res) == ["dfxp111", "db000"]
    assert cs._build_equipped({"result": None}) == []
    assert cs._build_equipped("EA 报错") == []


async def test_get_collection_caches(monkeypatch) -> None:
    calls: list[str] = []

    class FakeClient:
        async def getMedalsByPersonaId(self, pid):  # noqa: N802 - 仿 Gateway 客户端
            calls.append("medals")
            return MEDALS

        async def getDogtagsByPersonaId(self, pid):  # noqa: N802
            calls.append("dogtags")
            return DOGTAGS

        async def getEquippedDogtagsByPersonaId(self, pid):  # noqa: N802
            calls.append("equipped")
            raise RuntimeError("EA 超时")

    class Ctx:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, *exc):
            return False

    store: dict[str, object] = {}

    class FakeCache:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ttl=None):
            store[key] = value

    async def fake_get_cache():
        return FakeCache()

    monkeypatch.setattr(cs, "get_bf1_client", lambda db: Ctx())
    monkeypatch.setattr(cs, "get_cache", fake_get_cache)
    first = await cs.get_collection(None, 7)  # type: ignore[arg-type]
    # 佩戴的狗牌读失败不影响整页
    assert first.equipped == [] and len(first.medals) == 2
    assert await cs.get_collection(None, 7) == first  # type: ignore[arg-type]
    assert calls == ["medals", "dogtags", "equipped"]

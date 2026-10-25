from app.services.bf1 import player_service


async def test_get_avatars_uses_cache_and_caches_misses(monkeypatch) -> None:
    store: dict = {"bf1:avatar:1": "https://a/1.jpg", "bf1:avatar:2": ""}
    ttls: dict = {}

    class _Cache:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ttl=None):
            store[key] = value
            ttls[key] = ttl

    async def fake_get_cache():
        return _Cache()

    asked: list[int] = []

    async def fake_fetch(pid: int):
        asked.append(pid)
        return "https://a/3.jpg" if pid == 3 else None

    monkeypatch.setattr(player_service, "get_cache", fake_get_cache)
    monkeypatch.setattr(player_service, "_fetch_gametools_avatar", fake_fetch)

    result = await player_service.get_avatars([1, 2, 3, 4])

    assert result == {1: "https://a/1.jpg", 2: None, 3: "https://a/3.jpg", 4: None}
    assert sorted(asked) == [3, 4]
    assert ttls["bf1:avatar:3"] == player_service.AVATAR_TTL
    assert (store["bf1:avatar:4"], ttls["bf1:avatar:4"]) == ("", player_service.MISSING_AVATAR_TTL)


async def test_lookup_exact_prefers_gametools_then_blaze(monkeypatch) -> None:
    from app.schemas.bf1.player import PersonaBrief

    calls: list[str] = []

    async def gametools(name):
        calls.append("gametools")
        return PersonaBrief(persona_id=1, display_name=name) if name == "A-b" else None

    async def blaze(db, name):
        calls.append("blaze")
        return (2, "C-d") if name == "c-d" else None

    monkeypatch.setattr(player_service, "_fetch_gametools_persona", gametools)
    monkeypatch.setattr(player_service.blaze_service, "lookup_online_persona", blaze)
    svc = player_service.BF1PlayerService(db=None)

    assert (await svc._lookup_exact("A-b")).persona_id == 1
    assert calls == ["gametools"]
    hit = await svc._lookup_exact("c-d")
    assert (hit.persona_id, hit.display_name) == (2, "C-d")
    assert await svc._lookup_exact("nobody") is None

"""一键卡行动的纯逻辑"""

from __future__ import annotations

from app.services.bf1 import card_engine as engine

IMG = "[BB_PREFIX]/gamedata/Tunguska/45/67/{}_LandscapeLarge-2dbd3bf5.jpg"


def details(mode: str, maps: list[str], soldiers: int = 0, spectators: int = 0) -> dict:
    return {
        "guid": "0f07362c-77db-4967-a58a-aa2728631a23",
        "mapMode": mode,
        "mapName": maps[0] if maps else "",
        "slots": {
            "Soldier": {"current": soldiers, "max": 64},
            "Spectator": {"current": spectators, "max": 4},
            "Queue": {"current": 0, "max": 10},
        },
        "rotation": [{"mapImage": IMG.format(m), "modePrettyName": "行動模式"} for m in maps],
    }


RSP = {
    "serverSettings": {
        "name": "[TEST] 卡行动",
        "description": "简介",
        "message": "",
        "password": "123",
        "bannerUrl": "",
        "mapRotationId": "100",
        "customGameSettings": '{"version":10}',
    },
    "mapRotations": [
        {
            "mapRotationId": "100",
            "name": "0",
            "description": "",
            "mod": "63",
            "rotationType": "",
            "maps": [
                {"gameMode": "CQ0", "mapName": "MP_Amiens"},
                {"gameMode": "CQ0", "mapName": "MP_Suez"},
            ],
        }
    ],
}

OPS = [f"MP_Map{i}" for i in range(24)]


def test_seed_by_slots():
    assert engine.seed_maps(64) == [{"gameMode": "CQ0", "mapName": "MP_Alps"}] * 3
    assert engine.seed_maps(40)[0] == {"gameMode": "AA0", "mapName": "MP_Naval"}
    assert engine.seed_maps(32)[0] == {"gameMode": "TOW0", "mapName": "MP_Naval"}
    assert engine.seed_maps(24)[0] == {"gameMode": "TDM0", "mapName": "MP_Naval"}
    # 不在表里的人数按 64 人处理
    assert engine.seed_maps(0)[0]["mapName"] == "MP_Alps"


def test_map_code_from_image():
    assert engine.map_code(IMG.format("MP_Tsaritsyn")) == "MP_Tsaritsyn"
    assert engine.map_code(IMG.format("MP_Shoveltown")) == "MP_ShovelTown"
    assert engine.map_code("") == ""


def test_parse_state_and_hit():
    st = engine.parse_state(details("BreakthroughLarge", OPS, soldiers=1, spectators=1))
    assert st.mode == "BreakthroughLarge"
    assert st.maps == OPS
    assert st.occupied == 2
    assert st.soldier_max == 64
    assert engine.is_hit(st)
    assert not engine.is_hit(engine.parse_state(details("BreakthroughLarge", OPS[:5])))
    assert not engine.is_hit(engine.parse_state(details("Conquest", OPS)))


def test_snapshot_keeps_password_and_rotation():
    snap = engine.snapshot_from_rsp(RSP)
    assert snap.settings["password"] == "123"
    assert snap.rotation["mod"] == "63"
    assert [m["mapName"] for m in snap.rotation["maps"]] == ["MP_Amiens", "MP_Suez"]
    assert engine.Snapshot.from_dict(snap.to_dict()) == snap


def test_update_params_seed_and_restore():
    snap = engine.snapshot_from_rsp(RSP)
    seed = engine.update_params(12552064, snap, engine.seed_maps(64))
    assert seed["serverId"] == "12552064"
    assert seed["game"] == "tunguska"
    assert seed["mapRotation"]["maps"] == engine.seed_maps(64)
    assert seed["mapRotation"]["mod"] == engine.SEED_MOD
    # 其余设置原样回填
    s = seed["serverSettings"]
    assert (s["name"], s["description"], s["password"]) == ("[TEST] 卡行动", "简介", "123")
    assert s["customGameSettings"] == '{"version":10}'
    assert s["mapRotationId"] == seed["mapRotation"]["id"] == "100"

    restore = engine.update_params(12552064, snap)
    assert restore["mapRotation"]["maps"] == RSP["mapRotations"][0]["maps"]
    assert restore["mapRotation"]["mod"] == "63"


def test_anchor_maps_and_check():
    st = engine.parse_state(details("BreakthroughLarge", OPS))
    maps = engine.anchor_maps(st.maps)
    assert maps[0] == {"gameMode": "AA0", "mapName": "MP_Map0"}
    assert engine.is_anchored(st, maps)
    assert not engine.is_anchored(st, list(reversed(maps)))
    assert not engine.is_anchored(st, [{**m, "gameMode": "CQ0"} for m in maps])


def test_update_error_ignores_banner_noise():
    assert engine.update_error({"result": "success"}) is None
    assert engine.update_error("ERR_AUTHORIZATION_REQUIRED") is None
    assert engine.update_error("Internal Error: updateServerBanner failed") is None
    assert engine.update_error("无权限") == "无权限"
    assert engine.is_permission_error("无权限")


def test_append_events_newest_first_and_capped():
    ev = engine.append_events([], [("info", "a"), ("info", "b")], 1.0)
    assert [e["message"] for e in ev] == ["b", "a"]
    ev = engine.append_events(ev, [("info", str(i)) for i in range(400)], 2.0)
    assert len(ev) == engine.EVENT_LIMIT
    assert ev[0]["message"] == "399"

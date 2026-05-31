"""BFBAN / BFEAC 封禁解析纯函数单测

覆盖 _parse_bfban 与 _parse_bfeac 从外部接口响应提取封禁三态（clean / hit /
unknown）的逻辑，含命中、无记录、结构异常等降级路径。BFBAN 形态取自现行
gametools 接口实测（personaids[pid].hacker 布尔），并保留旧 status 形态的兼容；
解析对未知结构一律降级为 unknown。
"""

from __future__ import annotations

from app.services.bf1.ban_service import _parse_bfban, _parse_bfeac


def test_parse_bfban_clean_when_hacker_false() -> None:
    # 实测形态：{"names":{},"userids":{},"personaids":{"<pid>":{"hacker":false}}}
    payload = {
        "names": {},
        "userids": {},
        "personaids": {"1005989050250": {"hacker": False}},
    }
    state, url = _parse_bfban(payload, 1005989050250)
    assert state == "clean"
    assert url is None


def test_parse_bfban_hit_when_hacker_true() -> None:
    payload = {"personaids": {"1005989050250": {"hacker": True, "url": "https://bfban/case/1"}}}
    state, url = _parse_bfban(payload, 1005989050250)
    assert state == "hit"
    assert url == "https://bfban/case/1"


def test_parse_bfban_hit_with_legacy_status() -> None:
    # 旧形态：无 hacker，靠 status 字符串判定，"1" 为实锤
    payload = {"personaids": {"1005989050250": {"status": "1", "url": "https://bfban/case/1"}}}
    state, url = _parse_bfban(payload, 1005989050250)
    assert state == "hit"
    assert url == "https://bfban/case/1"


def test_parse_bfban_clean_when_status_zero() -> None:
    payload = {"personaids": {"1005989050250": {"status": "0"}}}
    state, url = _parse_bfban(payload, 1005989050250)
    assert state == "clean"
    assert url is None


def test_parse_bfban_accepts_flat_top_level_bucket() -> None:
    # 部分形态把 pid 结果直接平铺在顶层而非 personaids 下
    payload = {"1005989050250": {"hacker": True}}
    state, _ = _parse_bfban(payload, 1005989050250)
    assert state == "hit"


def test_parse_bfban_unknown_when_pid_missing() -> None:
    payload = {"personaids": {"999": {"hacker": True}}}
    state, url = _parse_bfban(payload, 1005989050250)
    assert state == "unknown"
    assert url is None


def test_parse_bfban_unknown_on_bad_shape() -> None:
    assert _parse_bfban(None, 1)[0] == "unknown"
    # 既无 hacker 也无 status，无法判定
    assert _parse_bfban({"personaids": {"1": {}}}, 1)[0] == "unknown"


def test_parse_bfeac_hit_with_url() -> None:
    payload = {"data": [{"current_status": 1, "case_id": 9}]}
    state, url = _parse_bfeac(payload)
    assert state == "hit"
    assert url == "https://bfeac.com/#/case/9"


def test_parse_bfeac_clean_when_status_not_banned() -> None:
    payload = {"data": [{"current_status": 3}]}
    state, url = _parse_bfeac(payload)
    assert state == "clean"
    assert url is None


def test_parse_bfeac_clean_on_empty_data() -> None:
    # data 为空列表表示查无案件
    state, url = _parse_bfeac({"data": []})
    assert state == "clean"
    assert url is None


def test_parse_bfeac_unknown_on_bad_shape() -> None:
    assert _parse_bfeac(None)[0] == "unknown"
    assert _parse_bfeac({"data": None})[0] == "unknown"
    assert _parse_bfeac({"data": [{"current_status": "x"}]})[0] == "unknown"

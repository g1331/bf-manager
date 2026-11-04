"""BF6 客户端网关用到的 protobuf 消息，手写 wire 编解码。

只覆盖我们发出和读取的字段：

- ``santiago.client.authentication.ClientAuthentication/viaJWT``：
  请求 ``{1: jwt, 2: platform}``，响应 ``{1: jwt, 2: Player}``
- ``santiago.client.stats.ClientStats/getStats``：
  请求 ``{1: repeated category_id, 2: repeated Player, 3: repeated stat_id,
  4: repeated DimensionsFilter}``，
  响应 ``{1: repeated PlayerStats}``
- ``Player``：``{1: nucleus_id, 2: persona_id, 3: platform}``
- ``PlayerStats``：``{1: Player, 2: repeated CategoryStats}``
- ``CategoryStats``：``{1: category_id, 2: repeated Stat, 3: repeated DimensionedStat}``
- ``Stat``：``{1: name, 2: int32 value}``；``DimensionedStat`` 多一个 ``{3: repeated Dimension}``
- ``Dimension``：``{1: key, 2: value}``

只有字符串和 varint 两种线上类型，引入 protobuf 运行时和生成代码不划算。
"""

from __future__ import annotations

from dataclasses import dataclass, field

_WIRE_VARINT = 0
_WIRE_FIXED64 = 1
_WIRE_LEN = 2
_WIRE_FIXED32 = 5


class WireError(ValueError):
    """响应不是合法的 protobuf 编码。"""


# ---------------------------------------------------------------------------
# 基础编码
# ---------------------------------------------------------------------------


def _varint(value: int) -> bytes:
    if value < 0:
        # proto3 的负 int32/int64 按 64 位补码编码
        value &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(field_number: int, wire: int) -> bytes:
    return _varint((field_number << 3) | wire)


def _uint_field(field_number: int, value: int) -> bytes:
    # proto3 默认值不上线
    if not value:
        return b""
    return _key(field_number, _WIRE_VARINT) + _varint(value)


def _bytes_field(field_number: int, value: bytes) -> bytes:
    return _key(field_number, _WIRE_LEN) + _varint(len(value)) + value


def _str_field(field_number: int, value: str) -> bytes:
    return _bytes_field(field_number, value.encode("utf-8"))


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise WireError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift >= 64:
            raise WireError("varint too long")


def _to_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


_Fields = dict[int, list[int | bytes]]


def _parse(buf: bytes) -> _Fields:
    """按字段号收集值：varint 是 int，长度分隔是 bytes；定长字段这些消息里没有，跳过。"""
    fields: _Fields = {}
    pos = 0
    while pos < len(buf):
        key, pos = _read_varint(buf, pos)
        number, wire = key >> 3, key & 0x07
        if number == 0:
            raise WireError("invalid field number 0")
        if wire == _WIRE_VARINT:
            value, pos = _read_varint(buf, pos)
            fields.setdefault(number, []).append(value)
        elif wire == _WIRE_LEN:
            length, pos = _read_varint(buf, pos)
            end = pos + length
            if end > len(buf):
                raise WireError("truncated length-delimited field")
            fields.setdefault(number, []).append(buf[pos:end])
            pos = end
        elif wire == _WIRE_FIXED64:
            pos += 8
        elif wire == _WIRE_FIXED32:
            pos += 4
        else:
            raise WireError(f"unsupported wire type {wire}")
        if pos > len(buf):
            raise WireError("truncated fixed-width field")
    return fields


def _get_int(fields: _Fields, number: int) -> int:
    # 同一标量字段出现多次时 protobuf 取最后一个
    for value in reversed(fields.get(number, [])):
        if isinstance(value, int):
            return value
    return 0


def _get_str(fields: _Fields, number: int) -> str:
    for value in reversed(fields.get(number, [])):
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
    return ""


def _get_messages(fields: _Fields, number: int) -> list[bytes]:
    return [value for value in fields.get(number, []) if isinstance(value, bytes)]


# ---------------------------------------------------------------------------
# 消息
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Player:
    nucleus_id: int = 0
    persona_id: int = 0
    platform: int = 0


@dataclass(frozen=True)
class Dimension:
    key: str
    value: str


@dataclass(frozen=True)
class DimensionedStat:
    name: str
    value: int
    dimensions: tuple[Dimension, ...] = ()


@dataclass(frozen=True)
class CategoryStats:
    category_id: str
    stats: tuple[tuple[str, int], ...] = ()
    dimensioned_stats: tuple[DimensionedStat, ...] = ()


@dataclass(frozen=True)
class PlayerStats:
    player: Player
    categories: tuple[CategoryStats, ...] = field(default_factory=tuple)


def encode_player(player: Player) -> bytes:
    return (
        _uint_field(1, player.nucleus_id)
        + _uint_field(2, player.persona_id)
        + _uint_field(3, player.platform)
    )


def encode_via_jwt_request(jwt: str, platform: int) -> bytes:
    return _str_field(1, jwt) + _uint_field(2, platform)


def encode_dimensions_filter(stat_id: str, dimensions: list[tuple[str, str]]) -> bytes:
    """``DimensionsFilter{1: dimensioned_stat_id, 2: repeated Dimension}``。

    stat_id 为空表示所有统计；空字符串也照样编码上线，和游戏客户端发的一致。
    """
    out = bytearray(_str_field(1, stat_id))
    for key, value in dimensions:
        out += _bytes_field(2, _str_field(1, key) + _str_field(2, value))
    return bytes(out)


def encode_get_stats_request(
    category_ids: list[str],
    players: list[Player],
    dimensions_filters: list[bytes] | None = None,
) -> bytes:
    """字段 3（stat_ids）不发：传任何值都会把整个类别过滤成空，按字段过滤要用 dimensions_filters。"""
    out = bytearray()
    for category in category_ids:
        out += _str_field(1, category)
    for player in players:
        out += _bytes_field(2, encode_player(player))
    for payload in dimensions_filters or ():
        out += _bytes_field(4, payload)
    return bytes(out)


def decode_player(buf: bytes) -> Player:
    fields = _parse(buf)
    return Player(
        nucleus_id=_get_int(fields, 1),
        persona_id=_get_int(fields, 2),
        platform=_to_int32(_get_int(fields, 3)),
    )


def _decode_dimensioned(buf: bytes) -> DimensionedStat:
    fields = _parse(buf)
    dims = []
    for raw in _get_messages(fields, 3):
        dim = _parse(raw)
        dims.append(Dimension(_get_str(dim, 1), _get_str(dim, 2)))
    return DimensionedStat(_get_str(fields, 1), _to_int32(_get_int(fields, 2)), tuple(dims))


def _decode_category(buf: bytes) -> CategoryStats:
    fields = _parse(buf)
    stats = []
    for raw in _get_messages(fields, 2):
        stat = _parse(raw)
        stats.append((_get_str(stat, 1), _to_int32(_get_int(stat, 2))))
    return CategoryStats(
        category_id=_get_str(fields, 1),
        stats=tuple(stats),
        dimensioned_stats=tuple(_decode_dimensioned(raw) for raw in _get_messages(fields, 3)),
    )


def decode_get_stats_response(buf: bytes) -> list[PlayerStats]:
    result = []
    for raw in _get_messages(_parse(buf), 1):
        fields = _parse(raw)
        players = _get_messages(fields, 1)
        result.append(
            PlayerStats(
                player=decode_player(players[0]) if players else Player(),
                categories=tuple(_decode_category(c) for c in _get_messages(fields, 2)),
            )
        )
    return result


def decode_via_jwt_response(buf: bytes) -> tuple[str, Player]:
    fields = _parse(buf)
    players = _get_messages(fields, 2)
    return _get_str(fields, 1), decode_player(players[0]) if players else Player()


# 测试构造响应用
def encode_dimensioned_stat(stat: DimensionedStat) -> bytes:
    out = bytearray(_str_field(1, stat.name) + _uint_field(2, stat.value))
    for dim in stat.dimensions:
        out += _bytes_field(3, _str_field(1, dim.key) + _str_field(2, dim.value))
    return bytes(out)


def encode_get_stats_response(players: list[PlayerStats]) -> bytes:
    out = bytearray()
    for item in players:
        body = bytearray(_bytes_field(1, encode_player(item.player)))
        for category in item.categories:
            cat = bytearray(_str_field(1, category.category_id))
            for name, value in category.stats:
                cat += _bytes_field(2, _str_field(1, name) + _uint_field(2, value))
            for stat in category.dimensioned_stats:
                cat += _bytes_field(3, encode_dimensioned_stat(stat))
            body += _bytes_field(2, bytes(cat))
        out += _bytes_field(1, bytes(body))
    return bytes(out)

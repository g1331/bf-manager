"""Blaze 编解码与收包分帧单测：锁定整数 / blob 往返，以及 TCP 粘包、半包、坏帧、断线时的行为"""

from __future__ import annotations

import asyncio

import pytest
from app.domain.ea.blaze_protocol.protocol import Blaze
from app.domain.ea.blaze_protocol.socket import BlazeSocket


def _frame(packet_id: int, game_id: int = 1) -> bytes:
    return Blaze(
        {
            "method": "GameManager.getGameDataFromId",
            "type": "Command",
            "id": packet_id,
            "data": {"DNAM 1": "csFullGameList", "GLST 40": [game_id]},
        }
    ).encode()


def _socket_with_pending(*ids: int) -> tuple[BlazeSocket, dict[int, asyncio.Future]]:
    """未真正建连的 socket，预先登记若干等待中的请求。"""
    sock = BlazeSocket("test", 0)
    sock.connect = True
    loop = asyncio.get_running_loop()
    futures = {i: loop.create_future() for i in ids}
    sock.map.update(futures)
    return sock, futures


@pytest.mark.parametrize("value", [0, 1, 63, 64, 8191, -1, -5, -64, 10**15 + 1, 2**60 + 3])
def test_integer_roundtrip(value: int) -> None:
    encoded = bytes.fromhex(Blaze.write_integer(value))
    decoded, offset = Blaze.parse_integer(encoded, 0)
    assert decoded == value
    assert offset == len(encoded)


def test_blob_roundtrip_keeps_last_byte() -> None:
    encoded = bytes.fromhex(Blaze.write_blob("aabbcc"))
    assert Blaze.parse_blob(encoded, 0) == ("aabbcc", len(encoded))


def test_decode_unknown_component_does_not_raise() -> None:
    frame = bytearray(16)
    frame[6:8] = (999).to_bytes(2, "big")
    frame[8:10] = (7).to_bytes(2, "big")
    assert Blaze(bytes(frame)).decode()["method"] == "999.7"


async def test_multiple_frames_in_one_read() -> None:
    sock, futures = _socket_with_pending(1, 2)
    await sock.concat(_frame(1) + _frame(2))
    assert futures[1].result()["id"] == 1
    assert futures[2].result()["id"] == 2
    assert not sock._buffer


async def test_frames_split_across_reads_including_header() -> None:
    sock, futures = _socket_with_pending(3, 4)
    stream = _frame(3, game_id=10**12) + _frame(4)
    # 逐 7 字节喂入：包头被拆开、上一帧尾部与下一帧开头同处一次 read
    for i in range(0, len(stream), 7):
        await sock.concat(stream[i : i + 7])
    assert futures[3].result()["data"]["GLST"] == [10**12]
    assert futures[4].result()["id"] == 4


async def test_bad_frame_fails_only_its_request() -> None:
    sock, futures = _socket_with_pending(5, 6)
    bad = bytearray(_frame(5))
    bad[16:] = b"\xff" * (len(bad) - 16)  # 包头完好、包体损坏
    await sock.concat(bytes(bad) + _frame(6))
    with pytest.raises(ValueError):
        futures[5].result()
    assert futures[6].result()["id"] == 6
    assert sock.connect


async def test_disconnect_fails_pending_requests() -> None:
    sock, futures = _socket_with_pending(7)
    reader = asyncio.StreamReader()
    reader.feed_eof()
    sock.reader = reader
    await sock.receive_data()
    assert not sock.connect
    assert not sock.map
    with pytest.raises(ConnectionError):
        futures[7].result()


async def test_receive_loop_marks_disconnected_on_corrupt_stream() -> None:
    sock, futures = _socket_with_pending(8)
    reader = asyncio.StreamReader()
    reader.feed_data(b"\xff" * 16)  # 帧长度超上限，流已错位
    sock.reader = reader
    await sock.receive_data()
    assert not sock.connect
    with pytest.raises(ConnectionError):
        futures[8].result()

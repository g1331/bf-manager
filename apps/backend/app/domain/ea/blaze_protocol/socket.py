import asyncio
import contextlib
import ssl
from typing import Union

import httpx
from loguru import logger

from app.domain.ea.blaze_protocol.protocol import QType, Blaze, keepalive

context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE
context.set_ciphers("ALL")


class BlazeServerREQ:
    BF1 = (
        "<serverinstancerequest><name>battlefield-1-pc</name><connectionprofile>standardSecure_v4"
        "</connectionprofile></serverinstancerequest> "
    )
    BFV = (
        "<serverinstancerequest><name>battlefield-casablanca-pc</name><connectionprofile>standardSecure_v4"
        "</connectionprofile></serverinstancerequest> "
    )
    BF2042 = (
        "<serverinstancerequest><name>bf-2021-pc-gen5</name><connectionprofile>standardSecure_v4"
        "</connectionprofile></serverinstancerequest> "
    )

    @staticmethod
    async def get_server_address(
        game_code: Union["BF1", "BFV", "BF2042"] = BF1,
    ) -> (str, int):
        """
        获取服务器地址
        :param game_code: 游戏代码, 默认为BF1, 可选BF1, BFV, BF2042
        :return: Blaze服务器地址
        eg:
        {
            'address': {
                'ipAddress': {
                    'hostname': 'diceprodblapp-08.ea.com',
                    'ip': 2677614132,
                    'port': 10483
                }
            },
            'addressRemaps': [],
            'certificateList': [],
            'messages': [],
            'nameRemaps': [],
            'secure': 1,
            'trialServiceName': '',
            'defaultDnsAddress': 0
        }
        """
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                "https://spring18.gosredirector.ea.com:42230/redirector/getServerInstance",
                headers={
                    "Content-Type": "application/xml",
                    "Accept": "application/json",
                },
                data=game_code,
            )
            response.raise_for_status()
            host = response.json()["address"]["ipAddress"]["hostname"]
            port = response.json()["address"]["ipAddress"]["port"]
            return host, port


# Blaze 帧头固定 16 字节：[0:4] 长度 + [4:6] 扩展长度 + 组件 / 命令 / ID / 类型
HEADER_SIZE = 16
# 单帧上限：超出视为流已错位（或对端异常），断开连接而不是无限缓冲
MAX_FRAME_SIZE = 64 * 1024 * 1024
# 能匹配等待中请求的包类型（命令的应答）
_REPLY_TYPES = ("Result", "Error")


class BlazeSocket:
    def __init__(self, host: str, port: int, callback=None, readable: bool = True):
        self.callback = callback
        self.readable = readable
        self.connect = False
        self.authenticated = False
        self.map: dict[int, asyncio.Future] = {}
        self.id = 1
        # TCP 是字节流：一次 read 可能含半个帧，也可能含多个帧，统一进缓冲区按帧头切分
        self._buffer = bytearray()
        # 持有后台任务引用，避免被 GC 回收（asyncio.create_task 文档要求）
        self._tasks: set[asyncio.Task] = set()
        self.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.ssl_context.set_ciphers("ALL")
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None

    @classmethod
    async def create(cls, host: str = "diceprodblapp-08.ea.com", port: int = 10539, callback=None):
        self = BlazeSocket(host, port, callback)
        await self.connect_to_server()
        self._spawn(self.keepalive())
        return self

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def connect_to_server(self):
        # 异步连接到服务器
        self.reader, self.writer = await asyncio.open_connection(
            self.host, self.port, ssl=self.ssl_context
        )
        self.connect = True
        logger.success(f"已连接到Blaze服务器 {self.host}:{self.port}")
        self._spawn(self.receive_data())

    def _is_writer_valid(self) -> bool:
        """检查writer是否有效可用"""
        if not self.writer:
            return False
        if self.writer.is_closing():
            return False
        transport = self.writer.transport
        if not transport or transport.is_closing():
            return False

        # 检查SSL协议层状态
        # 注意：_ssl_protocol是asyncio内部属性，不是公共API的一部分
        # 这是针对观察到的AttributeError: 'NoneType' object has no attribute '_write_appdata'的务实解决方案
        # 当SSL连接断开时，_ssl_protocol可能变为None，但transport对象仍然存在
        # 如果未来Python提供公共API来检查SSL层健康状态，应优先使用公共API
        try:
            # 首先尝试使用更安全的方法检查SSL状态
            if hasattr(transport, "get_extra_info"):
                ssl_object = transport.get_extra_info("ssl_object")
                if ssl_object is None and hasattr(transport, "_ssl_protocol"):
                    # 如果没有SSL对象但transport声称支持SSL，可能存在问题
                    return transport._ssl_protocol is not None

            # 作为后备方案，检查内部_ssl_protocol属性
            if hasattr(transport, "_ssl_protocol") and transport._ssl_protocol is None:
                return False
        except Exception:
            # 如果SSL状态检查失败，采用保守策略
            # 假设连接可能有问题，但不完全阻止操作
            logger.debug("SSL状态检查失败，采用保守策略继续")

        return True

    def _cleanup_connection(self):
        """清理连接资源"""
        self.writer = None
        self.reader = None

    def _mark_disconnected(self, reason: str) -> None:
        """标记连接断开，并让所有等待中的请求立即失败，而不是各自干等到超时。"""
        self.connect = False
        if self.writer is not None:
            with contextlib.suppress(Exception):
                self.writer.close()
        self._cleanup_connection()
        self._buffer.clear()
        pending, self.map = self.map, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(ConnectionError(reason))

    async def close(self):
        # 关闭连接
        self.connect = False
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except ssl.SSLError as e:
                # 处理SSL错误：APPLICATION_DATA_AFTER_CLOSE_NOTIFY
                logger.warning(f"SSL关闭连接时出现错误 (可忽略): {e}")
            except Exception as e:
                logger.exception(f"关闭连接时出现错误: {e}")
        self._mark_disconnected("连接已关闭")
        # close 可能在接收任务内部被调用（会话过期分支），不能取消自己
        current = asyncio.current_task()
        for task in list(self._tasks):
            if task is not current:
                task.cancel()
        logger.success(f"已断开与Blaze服务器 {self.host}:{self.port} 的连接")

    async def keepalive(self):
        while self.connect:
            await asyncio.sleep(60)
            # 检查连接状态和writer有效性
            if self.connect and self._is_writer_valid():
                try:
                    self.writer.write(keepalive)
                    await self.writer.drain()  # 确保数据发送
                except Exception as e:
                    logger.exception(f"Keepalive发送失败，连接可能已断开: {e}")
                    self._mark_disconnected("Keepalive 发送失败")
                    break
            elif self.connect:
                # 连接标志为True但writer无效，说明连接已断开
                logger.warning("检测到连接异常，writer无效，停止keepalive")
                self._mark_disconnected("writer 无效")
                break

    async def send(self, packet, timeout=60):
        # 发送数据包
        if not self.connect:
            raise ConnectionError("连接已关闭")
        if self.id > 65535:
            self.id = 1
        if isinstance(packet, bytes):
            packet = Blaze(packet).decode()

        future = asyncio.Future()
        if "id" not in packet:
            packet["id"] = self.id
            self.id += 1
        if packet["id"] in self.map:
            packet["id"] = self.id
            self.id += 1
        self.map[packet["id"]] = future
        self.id += 1
        try:
            await self.request(packet)
        except BaseException:
            self.map.pop(packet["id"], None)
            raise
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as e:
            self.map.pop(packet["id"], None)
            raise TimeoutError(f"Timeout waiting for response to packet ID: {packet['id']}") from e

    async def request(self, packet):
        # 请求数据包
        if not self.connect:
            raise ConnectionError("连接已关闭")
        if isinstance(packet, dict):
            # 编码失败是请求体写错，连接本身完好，不能走下面的断线分支
            try:
                packet = Blaze(packet).encode()
            except Exception as e:
                raise ValueError(f"数据包编码失败: {e}") from e
        elif not isinstance(packet, bytes):
            raise TypeError("packet must be dict or bytes")
        if not self._is_writer_valid():
            raise ConnectionError("Writer无效，连接可能已断开")
        try:
            self.writer.write(packet)
            await self.writer.drain()  # 确保数据发送
        except Exception as e:
            logger.exception(f"发送数据包失败: {e}")
            self._mark_disconnected(f"发送数据包失败: {e}")
            raise ConnectionError(f"发送数据包失败: {e}") from e

    async def receive_data(self):
        # 接收数据；无论因何退出（含意外异常），都把连接标记为断开，避免连接池误判可用
        reason = "接收循环退出"
        try:
            while self.connect:
                try:
                    data = await self.reader.read(65565)
                except ConnectionResetError:
                    logger.warning("连接被重置，正在清理资源")
                    reason = "连接被重置"
                    break
                except Exception as e:
                    logger.exception(f"接收数据时发生错误: {e}")
                    reason = f"接收数据出错: {e}"
                    break
                if not data:
                    # 主动 close() 后读到 EOF 属正常收尾，不告警
                    if self.connect:
                        logger.warning("连接已断开，没有更多数据")
                    reason = "连接已断开"
                    break
                await self.concat(data)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"处理接收数据时发生错误: {e}")
            reason = f"处理接收数据出错: {e}"
        finally:
            if self.connect:
                self._mark_disconnected(reason)

    async def concat(self, data: bytes) -> None:
        """把收到的字节追加到缓冲区，切出所有完整帧逐个处理，剩余半帧留待下次。"""
        self._buffer += data
        while len(self._buffer) >= HEADER_SIZE:
            frame_size = (
                HEADER_SIZE
                + int.from_bytes(self._buffer[0:4], "big")
                + int.from_bytes(self._buffer[4:6], "big")
            )
            if frame_size > MAX_FRAME_SIZE:
                raise ConnectionError(f"Blaze 帧长度异常: {frame_size}")
            if len(self._buffer) < frame_size:
                return
            frame = bytes(self._buffer[:frame_size])
            del self._buffer[:frame_size]
            try:
                packet = Blaze(frame).decode(self.readable)
            except Exception as e:
                # 单帧解码失败不影响后续帧：若是应答则让对应请求立即失败，继续处理下一帧
                packet_id = int.from_bytes(frame[11:13], "big")
                logger.exception(f"Blaze 帧解码失败 (ID {packet_id}, {frame_size} 字节): {e}")
                if QType.get(str(frame[13])) in _REPLY_TYPES:
                    future = self.map.pop(packet_id, None)
                    if future is not None and not future.done():
                        future.set_exception(ValueError(f"Blaze 响应解码失败: {e}"))
                continue
            await self.response(packet)

    async def response(self, packet):
        # 处理接收到的数据包
        if packet["method"] == "KeepAlive":
            return
        # 只有应答能匹配等待中的请求：推送的 ID 与请求无关（登录时的 UserAuthenticated 推送 ID 同为 0），
        # 按 ID 匹配会让推送抢先充当登录应答
        if packet["type"] in _REPLY_TYPES and packet["id"] in self.map:
            future = self.map.pop(packet["id"])
            if not future.done():
                future.set_result(packet)
        elif packet["method"] == "UserSessions.UserUnauthenticated":
            logger.error("Blaze 会话已被注销，请重新登录/连接！")
            await self.close()
        elif packet["type"] == "Message":
            # 推送体可能很大（游戏列表快照数 MB），只记方法名
            logger.debug(f"Blaze 推送: {packet['method']}")
        elif packet["type"] == "Pong":
            pass
        else:
            logger.warning(f"Blaze 应答无对应请求: {packet['method']} (ID {packet['id']})")
        if self.callback:
            self.callback(packet)

    @staticmethod
    def callback(packet):
        # 只记方法名：登录应答里带会话 key 等凭据
        logger.debug(f"Blaze 包: {packet.get('method')} ({packet.get('type')})")

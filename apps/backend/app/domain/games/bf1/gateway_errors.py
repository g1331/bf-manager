"""BF1 gateway 调用失败时的返回值

gateway 的方法历来是「成功返回 dict、失败返回中文说明」，六十多处调用方靠
``isinstance(res, dict)`` 判成败，并把字符串直接展示给用户。EAGatewayError 继承 str，
这些老写法照常工作；需要按错误种类分支的地方改看 ``kind`` / ``code`` / ``ea_message``，
不再去匹配中文文案。
"""

from __future__ import annotations

from typing import Literal

ErrorKind = Literal["network", "bad_response", "ea", "internal"]


class EAGatewayError(str):
    """gateway 调用失败。

    - ``network``：超时、连不上，属于暂时性故障
    - ``bad_response``：EA 返回了非 JSON 等无法解析的内容
    - ``ea``：EA 返回了 JSON-RPC error；``code`` 是 EA 的错误码，``ea_message`` 是原文
      （如 ``RspErrUserIsAlreadyVip()``）
    - ``internal``：处理响应时本地代码出错
    """

    kind: ErrorKind
    code: int | None
    ea_message: str | None

    def __new__(
        cls,
        text: str,
        *,
        kind: ErrorKind,
        code: int | None = None,
        ea_message: str | None = None,
    ) -> EAGatewayError:
        obj = super().__new__(cls, text)
        obj.kind = kind
        obj.code = code
        obj.ea_message = ea_message
        return obj

    def __repr__(self) -> str:
        return f"EAGatewayError({str(self)!r}, kind={self.kind!r}, code={self.code!r})"

    def __reduce__(self) -> tuple[object, ...]:
        # str 子类默认按 cls.__new__(cls, text) 重建，缺关键字参数会让 copy / pickle 直接报错
        return (_rebuild, (str(self), self.kind, self.code, self.ea_message))


def _rebuild(
    text: str, kind: ErrorKind, code: int | None, ea_message: str | None
) -> EAGatewayError:
    return EAGatewayError(text, kind=kind, code=code, ea_message=ea_message)


# EA 拒绝重复添加 VIP 时的原文
ALREADY_VIP = "RspErrUserIsAlreadyVip()"

"""BF1 gateway 调用失败时的返回值

gateway 的方法「成功返回 EA 的 JSON、失败返回 EAGatewayError」。EAGatewayError 继承 str，
文案可以直接展示；判成败用 :func:`gateway_failure`，按失败种类分支看 ``kind`` 和下面几个
派生属性，不去匹配中文文案。
"""

from __future__ import annotations

from typing import Any, Literal

ErrorKind = Literal["network", "bad_response", "auth", "ea", "internal"]

# EA 拒绝重复添加 VIP 时的原文
ALREADY_VIP = "RspErrUserIsAlreadyVip()"

# EA 自己超时、会话失效（api_call 已重登重放过一次仍失效）：EA 这会儿整体不可用
_TRANSIENT_EA_CODES = frozenset({-32501, -32504})
_TRANSIENT_EA_MESSAGES = frozenset(
    {
        "Internal Error: se.dice.operations.commons.rx.time.TimeoutNamedException",
        "Internal Error: com.ea.sparta.hachiko.generated.thrift.InvocationException",
        "Invalid Params: no valid session",
    }
)
# 找不到服务器 / 服务器不存在或已过期 / 玩家不存在 / 战队不存在
_NOT_FOUND_EA_CODES = frozenset({-34501, -32851, -32856, -35150})
_NO_PERMISSION_EA_CODES = frozenset({-35160})
_NO_PERMISSION_EA_MESSAGES = frozenset({"Internal Error: org.apache.thrift.TApplicationException"})
# 已知的业务拒绝：方法不存在 / 参数不对 / 无法处置管理员 / 服务器未开启，以及上面的查无此物、没权限。
# 没列在这里的 EA 错误（NullPointerException 这类后端内部异常、没见过的错误码）不能证明请求
# 本身有问题，按暂时性故障处理
_REJECTED_EA_CODES = (
    frozenset({-32601, -32602, -32857, -32858}) | _NOT_FOUND_EA_CODES | _NO_PERMISSION_EA_CODES
)
_REJECTED_EA_MESSAGES = (
    frozenset(
        {
            "Authentication failed",
            "com.fasterxml.jackson.core.JsonParseException",
            "ServerNotRestartableException",
            "InvalidLevelIndexException",
        }
    )
    | _NO_PERMISSION_EA_MESSAGES
)
# RSP 的业务错误都是 RspErrXxx()，如 RspErrUserIsAlreadyVip()、RspErrServerBanMax()
_REJECTED_EA_MESSAGE_PREFIX = "RspErr"


class EAGatewayError(str):
    """gateway 调用失败。

    - ``network``：超时、连不上
    - ``bad_response``：EA 返回了非 JSON、非 200 等无法解析的内容
    - ``auth``：本站这次用的 EA 账号拿不到可用凭据（EA Desktop token 缺失或被作废）
    - ``ea``：EA 返回了 JSON-RPC error；``code`` 是 EA 的错误码，``ea_message`` 是原文
      （如 ``RspErrUserIsAlreadyVip()``）
    - ``internal``：本地代码出错，或调用前的本地校验没过
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

    @property
    def rejected(self) -> bool:
        """EA 明确拒绝了这次请求（玩家不存在、没有权限、名单已满……），原样重试不会变"""
        if self.kind != "ea":
            return False
        message = self.ea_message or ""
        return (
            self.code in _REJECTED_EA_CODES
            or message in _REJECTED_EA_MESSAGES
            or message.startswith(_REJECTED_EA_MESSAGE_PREFIX)
        )

    @property
    def retryable(self) -> bool:
        """暂时性故障：过一会儿或换个账号重试可能成功。EA 没明确拒绝的错误都算"""
        return self.kind in ("network", "bad_response", "auth") or (
            self.kind == "ea" and not self.rejected
        )

    @property
    def ea_unavailable(self) -> bool:
        """EA 这会儿整体不可用（连不上、超时、会话失效）：接着发别的请求也会失败。

        比 retryable 窄：EA 后端对某个玩家报的内部异常是 retryable，但不代表别人的请求也会失败。
        """
        if self.kind in ("network", "bad_response", "auth"):
            return True
        return self.kind == "ea" and (
            self.code in _TRANSIENT_EA_CODES or self.ea_message in _TRANSIENT_EA_MESSAGES
        )

    @property
    def not_found(self) -> bool:
        return self.kind == "ea" and self.code in _NOT_FOUND_EA_CODES

    @property
    def no_permission(self) -> bool:
        """执行账号不是这台服的管理员"""
        return self.kind == "ea" and (
            self.code in _NO_PERMISSION_EA_CODES or self.ea_message in _NO_PERMISSION_EA_MESSAGES
        )


# gateway 方法的返回值：成功是 EA 的 JSON，失败是 EAGatewayError
GatewayResult = dict[str, Any] | EAGatewayError


def _rebuild(
    text: str, kind: ErrorKind, code: int | None, ea_message: str | None
) -> EAGatewayError:
    return EAGatewayError(text, kind=kind, code=code, ea_message=ea_message)


def gateway_failure(res: object) -> EAGatewayError | None:
    """gateway 返回的是失败就给出错误，成功返回 None。

    成功的返回是 EA 的 JSON（dict）；遗留的纯字符串错误按 internal 处理，其他形状按
    bad_response 处理。
    """
    if isinstance(res, dict):
        return None
    if isinstance(res, EAGatewayError):
        return res
    if isinstance(res, str):
        return EAGatewayError(res, kind="internal")
    return EAGatewayError("EA 返回了意外的数据", kind="bad_response")


def is_already_vip(res: object) -> bool:
    err = gateway_failure(res)
    return err is not None and err.ea_message == ALREADY_VIP

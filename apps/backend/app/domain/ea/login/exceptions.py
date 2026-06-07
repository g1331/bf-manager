"""EA 登录链路的业务异常。

这里定义的异常仅在 ``domain/ea/login`` 内部与 service 层使用。Service 层负责把它们
映射成 ``app.api.errors`` 中的 HTTP 异常对外抛出，避免 domain 直接依赖 HTTP 层。
"""

from __future__ import annotations


class EALoginError(Exception):
    """EA 登录链路族基类。

    Attributes:
        code: 程序可读的错误代码（前端按前缀分类文案）。
        message: 面向用户的提示文案，禁止包含明文 email / password / cookie。
        stage: 错误发生在哪一步（``email`` / ``password`` / ``2fa_method`` /
            ``2fa_request`` / ``2fa_submit`` / ``redirect`` / ``finalize``），仅用于
            日志与诊断字段，不直接对外暴露。
    """

    code: str = "EA_LOGIN_UNKNOWN"
    message: str = "EA 登录失败"

    def __init__(
        self,
        message: str | None = None,
        *,
        stage: str | None = None,
        code: str | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        self.stage = stage
        super().__init__(self.message)


class EmailRejectedError(EALoginError):
    """EA 在邮箱阶段返回错误（账号不存在、被锁、不是 EA 账号等）。"""

    code = "EA_LOGIN_EMAIL_REJECTED"
    message = "EA 拒绝了该邮箱，可能是账号不存在或被锁定"


class WrongPasswordError(EALoginError):
    """密码错误。注意 EA 多次错误会触发风控，连续错误应直接转为 RiskBlocked。"""

    code = "EA_LOGIN_WRONG_PASSWORD"
    message = "密码错误"


class CredentialsExpiredError(EALoginError):
    """EA 提示 "credentials are incorrect or have expired"：账号凭据已过期或无效。

    与单纯的「密码错错了再试一次」不同：EA 在此状态下会拒绝任何密码尝试，需要用户
    去 EA 官网走「忘记密码 / 重置密码」流程恢复账号，前端文案与操作按钮也应当区
    别对待，避免引导用户反复试错触发风控。
    """

    code = "EA_LOGIN_CREDENTIALS_EXPIRED"
    message = "EA 凭据已过期或无效，请前往 EA 官网重置密码后重试"


class Need2FAMethodSelectionError(EALoginError):
    """EA 提供了多种 2FA 方式，需要由调用方决定走哪一种。

    Attributes:
        available_methods: EA 返回的可选方式标识（如 ``["EMAIL", "APP"]``）。
    """

    code = "EA_LOGIN_NEED_2FA_METHOD"
    message = "需要选择二次验证方式"

    def __init__(self, available_methods: list[str], *, stage: str | None = None) -> None:
        super().__init__(stage=stage)
        self.available_methods = available_methods


class Need2FACodeError(EALoginError):
    """EA 已发出验证码，需要由调用方提交。

    Attributes:
        method: 当前已选定的验证方式（``EMAIL`` / ``APP``）。
        masked_destination: EA 返回的脱敏目标（如 ``a***@b***``），仅供前端展示，
            禁止落日志。
    """

    code = "EA_LOGIN_NEED_2FA_CODE"
    message = "需要输入二次验证码"

    def __init__(
        self,
        method: str,
        masked_destination: str = "",
        *,
        stage: str | None = None,
    ) -> None:
        super().__init__(stage=stage)
        self.method = method
        self.masked_destination = masked_destination


class Invalid2FACodeError(EALoginError):
    """提交的 2FA 验证码被 EA 拒绝。"""

    code = "EA_LOGIN_INVALID_2FA_CODE"
    message = "验证码错误或已失效，请重新发起"


class Invalid2FAMethodError(EALoginError):
    """调用方选择了 EA 未提供的 2FA 方式。"""

    code = "EA_LOGIN_INVALID_2FA_METHOD"
    message = "选择的二次验证方式不在 EA 提供的列表中"


class RiskBlockedError(EALoginError):
    """EA 风控拦截：连续失败、IP 异常、需人机校验等。"""

    code = "EA_LOGIN_RISK_BLOCKED"
    message = "EA 风控拦截，请稍后再试或换网络重试"


class PrivacyAcceptRequiredError(EALoginError):
    """EA 要求接受新的隐私协议。登录引擎默认自动接受，仅在自动接受失败时上抛。"""

    code = "EA_LOGIN_PRIVACY_REQUIRED"
    message = "EA 需要接受新的隐私协议但自动确认失败"


class FormStructureChangedError(EALoginError):
    """EA 登录页结构变化导致解析失败。线上出现时是改版告警。

    Attributes:
        snippet: 脱敏后的关键 HTML 片段（最多 300 字符），仅用于日志诊断，
            禁止透传给前端。
    """

    code = "EA_LOGIN_FORM_CHANGED"
    message = "EA 登录页结构发生变化，登录链路暂不可用"

    def __init__(self, snippet: str = "", *, stage: str | None = None) -> None:
        super().__init__(stage=stage)
        self.snippet = snippet[:300]


class CookieExtractionFailedError(EALoginError):
    """最终重定向链未能提取到 remid 或 sid。"""

    code = "EA_LOGIN_COOKIE_MISSING"
    message = "登录链路完成但未能拿到 EA 凭据，请重试"


class UpstreamError(EALoginError):
    """非业务原因的上游异常：网络错误、TLS 失败、5xx 等。"""

    code = "EA_LOGIN_UPSTREAM_ERROR"
    message = "与 EA 服务器通信失败，请稍后重试"


__all__ = [
    "CookieExtractionFailedError",
    "CredentialsExpiredError",
    "EALoginError",
    "EmailRejectedError",
    "FormStructureChangedError",
    "Invalid2FACodeError",
    "Invalid2FAMethodError",
    "Need2FACodeError",
    "Need2FAMethodSelectionError",
    "PrivacyAcceptRequiredError",
    "RiskBlockedError",
    "UpstreamError",
    "WrongPasswordError",
]

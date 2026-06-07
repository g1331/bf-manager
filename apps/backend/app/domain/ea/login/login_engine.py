"""驱动 EA 网页登录链路的有限状态机。

引擎与任务管理 / FastAPI / 数据库无关，纯粹用 aiohttp 完成 EA 多步表单交互：

::

    start()                # GET → POST email → POST password
      ├─ next_step="done"        # 无 2FA，直接拿到 remid/sid/gatewaySessionId
      ├─ next_step="need_code"   # 单一 2FA 方式自动选定并已请求验证码
      └─ next_step="need_method" # 多方式，需调用方决定走哪一种

    select_method(method)  # 多方式分支后调用，内部触发请求验证码
    submit_code(code)      # 提交验证码 → 跟随重定向 → 拿到 cookies

设计约定：

- 实例字段保留 ``email`` / ``password`` 直到任务终态；所有日志只输出 ``step``、
  ``http_status``、``duration_ms``、``cookie_keys`` 等元数据，绝不出现明文。
- 网络异常统一映射为 :class:`UpstreamError`；EA 业务层错误映射为对应的具体异常。
- 调用方必须在终态后调用 :meth:`aclose` 关闭 aiohttp ``ClientSession`` 以避免连接池泄漏。
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl
from dataclasses import dataclass, field
from typing import Literal

import aiohttp
from loguru import logger
from lxml import html as lxml_html

from app.domain.ea.login.exceptions import (
    CookieExtractionFailedError,
    CredentialsExpiredError,
    EmailRejectedError,
    FormStructureChangedError,
    Invalid2FACodeError,
    Invalid2FAMethodError,
    PrivacyAcceptRequiredError,
    RiskBlockedError,
    UpstreamError,
    WrongPasswordError,
)
from app.domain.ea.login.form_parser import (
    build_form_payload,
    extract_available_auth_methods,
    extract_page_error,
    extract_redirect_url,
    get_email_method_masked_destination,
    has_privacy_accept_checkbox,
    parse_set_cookie_pair,
)

# EA 登录流程的起始 URL：sparta-companion-web 是 BF1 战地伴侣使用的 OAuth client。
EA_START_URL = (
    "https://accounts.ea.com/connect/auth?client_id=sparta-companion-web"
    "&response_type=code&display=web2/login&locale=en_US"
    "&redirect_uri=https%3A%2F%2Fcompanion-api.battlefield.com%2Fcompanion%2Fsso%3Fprotocol%3Dhttps"
)

# 模拟主流桌面浏览器，避免被 EA 风控判定为脚本。Accept-Language 走中文优先。
_DEFAULT_HEADERS = {
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# 用于识别风控关键词的小列表。匹配中英双语避免漏判。
_RISK_KEYWORDS = (
    "unusual",
    "verify your identity",
    "captcha",
    "blocked",
    "暂时无法",
    "异常",
    "拦截",
    "请稍后",
)

# EA 明确告知「账号凭据过期 / 不可用」时返回的关键片段。命中后引导用户去官网走重置
# 流程，而非反复尝试密码。注意 EA 实际页面常把这条文案与「You must be online…」
# 等通用提示拼在一起，所以匹配片段只取确诊力强的子串。
_CREDENTIALS_EXPIRED_KEYWORDS = (
    "credentials are incorrect or have expired",
    "credentials have expired",
    "凭据已过期",
)


def _classify_page_error(page_err: str) -> str:
    """把 EA 返回的错误文本分流成已知错误类别。

    返回值约定：``"expired"`` / ``"risk_blocked"`` / ``"wrong_password"``。
    顺序敏感：``expired`` 关键词与 ``wrong_password``（"incorrect"）字面上有交集，
    必须优先匹配 ``expired`` 才能避免把凭据过期场景误判为单纯密码错误。
    """
    if not page_err:
        return "wrong_password"
    lower = page_err.lower()
    if any(kw in lower for kw in _CREDENTIALS_EXPIRED_KEYWORDS):
        return "expired"
    if any(kw in lower for kw in _RISK_KEYWORDS):
        return "risk_blocked"
    return "wrong_password"


@dataclass
class LoginCookies:
    """登录成功后从 EA 抓取的核心 cookie 三元组。"""

    remid: str
    sid: str
    gateway_session_id: str


@dataclass
class StartOutcome:
    """:meth:`EALoginEngine.start` 的返回值，描述下一步应当做什么。"""

    next_step: Literal["need_method", "need_code", "done"]
    available_methods: list[str] = field(default_factory=list)
    selected_method: str | None = None
    masked_destination: str = ""
    cookies: LoginCookies | None = None


@dataclass
class MethodOutcome:
    """:meth:`EALoginEngine.select_method` 的返回值。"""

    selected_method: str
    masked_destination: str = ""


@dataclass
class FinalizeOutcome:
    """:meth:`EALoginEngine.submit_code` 的返回值。"""

    cookies: LoginCookies


class EALoginEngine:
    """单次 EA 登录任务的状态机。

    实例与单个登录任务一一对应；调用方负责在任务终态后调用 :meth:`aclose`。
    多次调用 :meth:`start` 或在错误状态下调用 :meth:`submit_code` 会抛出业务异常。
    """

    def __init__(self, task_id: str, email: str, password: str) -> None:
        self._task_id = task_id
        self._email = email
        self._password = password

        self._session: aiohttp.ClientSession | None = None
        # 在调用 select_method / submit_code 时需要复用密码页响应的 URL 与 HTML
        self._post_password_url: str = ""
        self._post_password_html: str = ""
        self._available_methods: list[str] = []
        self._selected_method: str | None = None
        # 请求验证码后 EA 返回的新 URL，供 submit_code 复用
        self._request_code_url: str = ""

    # ===== 公开 API =====

    async def start(self) -> StartOutcome:
        """完成 EA 登录链路前半段，把任务推进到等待用户输入或终态。

        EA 早期分两步：先 POST email，响应是密码页；再 POST password，响应是 2FA / redirect。
        EA juno 新版改为单页表单，email 与 password 出现在同一个 ``login-form`` 里——
        ``build_form_payload`` 会一次性取走两者，所以 ``_post_email`` 实际已经完成了
        密码校验，响应直接是终态页面（密码错 / 凭据过期 / 2FA / redirect）。

        本方法兼容两种版本：``_post_email`` 之后立即分类响应；仅当响应仍是一个**纯**
        密码输入页（旧版两步流程，并且没有任何错误提示）时才补发一次 ``_post_password``。
        """
        session = await self._ensure_session()
        start_resp, start_text = await self._get_start(session)
        email_resp, email_text = await self._post_email(session, start_resp, start_text)

        password_resp, password_text = await self._maybe_post_password(
            session, email_resp, email_text
        )

        if has_privacy_accept_checkbox(password_text):
            self._log("privacy_accept_required")
            password_resp, password_text = await self._accept_privacy(
                session, password_resp, password_text
            )

        return await self._classify_post_password_response(session, password_resp, password_text)

    async def _maybe_post_password(
        self,
        session: aiohttp.ClientSession,
        email_resp: aiohttp.ClientResponse,
        email_text: str,
    ) -> tuple[aiohttp.ClientResponse, str]:
        """决定是否补发一次密码 POST，兼容 EA 旧版两步流程。

        判定逻辑：
        - 响应**有** password 输入框且**没有**任何错误提示 → 旧版两步表单的纯密码页，
          补发一次 ``_post_password``；
        - 其它任何情况（含错误、2FA、redirect、隐私协议、未知页）→ 直接交给后续分类器
          处理，不再发多余 POST。这一步是新版 juno 单页表单的关键修复点：第一次 POST
          已经完成了密码校验，再 POST 一次会进入引擎不认识的页面，最终被误报为
          ``FormStructureChangedError``，掩盖掉真实的「密码错误 / 凭据过期」。
        """
        tree = lxml_html.fromstring(email_text)
        has_password_input = bool(tree.xpath('//input[@type="password" and @name="password"]'))
        if not has_password_input:
            self._log("skip_post_password", reason="no_password_input")
            return email_resp, email_text

        if extract_page_error(email_text):
            self._log("skip_post_password", reason="page_error_present")
            return email_resp, email_text

        # 旧版两步表单：第一步只校验邮箱，第二步才校验密码。
        return await self._post_password(session, email_resp, email_text)

    async def _classify_post_password_response(
        self,
        session: aiohttp.ClientSession,
        password_resp: aiohttp.ClientResponse,
        password_text: str,
    ) -> StartOutcome:
        """对 POST email/password 之后的响应做统一分类，抛对应异常或推进流程。

        分类顺序：
        1. 密码输入框还在 → 凭据被拒（凭据过期 / 风控 / 密码错误三选一）
        2. 2FA radio 列表非空 → 进入 2FA 流程
        3. ``window.location=`` 重定向 → 跳过去拿 cookies，``next_step="done"``
        4. 还有 page error 文本 → 按关键词分流（兜底捕捉 EA 不带 password 输入但
           直接渲染了错误信息的新版页面）
        5. 全部不匹配 → ``FormStructureChangedError``，附 HTML snippet 入日志
        """
        tree = lxml_html.fromstring(password_text)
        if tree.xpath('//input[@type="password" and @name="password"]'):
            page_err = extract_page_error(password_text) or "密码错误"
            self._raise_for_credentials_outcome(page_err, stage="password")

        methods = extract_available_auth_methods(password_text)
        if methods:
            self._post_password_url = str(password_resp.url)
            self._post_password_html = password_text
            self._available_methods = methods
            if len(methods) == 1:
                method = methods[0]
                self._selected_method = method
                masked = await self._request_code(session, method)
                return StartOutcome(
                    next_step="need_code",
                    available_methods=methods,
                    selected_method=method,
                    masked_destination=masked,
                )
            return StartOutcome(next_step="need_method", available_methods=methods)

        redirect_url = extract_redirect_url(password_text)
        if redirect_url:
            cookies = await self._handle_redirect(session, redirect_url, stage="finalize")
            return StartOutcome(next_step="done", cookies=cookies)

        page_err = extract_page_error(password_text)
        if page_err:
            self._raise_for_credentials_outcome(page_err, stage="password")

        raise FormStructureChangedError(_safe_snippet(password_text), stage="password")

    def _raise_for_credentials_outcome(self, page_err: str, *, stage: str) -> None:
        """按 :func:`_classify_page_error` 的分流结果抛对应业务异常。

        集中维护这套映射让 ``start()`` 与未来可能的 2FA 阶段分类共享同一份关键词表。
        """
        category = _classify_page_error(page_err)
        if category == "expired":
            raise CredentialsExpiredError(page_err, stage=stage)
        if category == "risk_blocked":
            raise RiskBlockedError(page_err, stage=stage)
        raise WrongPasswordError(page_err, stage=stage)

    async def select_method(self, method: str) -> MethodOutcome:
        """多 2FA 方式分支下选定一种，内部触发 EA 发送验证码。"""
        if not self._available_methods:
            raise Invalid2FAMethodError("当前任务尚未进入 2FA 阶段", stage="2fa_method")
        if method not in self._available_methods:
            raise Invalid2FAMethodError(f"方式 {method} 不在 EA 提供的列表中", stage="2fa_method")
        self._selected_method = method
        session = await self._ensure_session()
        masked = await self._request_code(session, method)
        return MethodOutcome(selected_method=method, masked_destination=masked)

    async def submit_code(self, code: str) -> FinalizeOutcome:
        """提交验证码并跟随最终重定向链取出 cookies。"""
        if not self._selected_method or not self._request_code_url:
            raise Invalid2FACodeError("当前任务尚未进入 2FA 提交阶段", stage="2fa_submit")
        session = await self._ensure_session()
        payload = {
            "oneTimeCode": code,
            "_trustThisDevice": "on",
            "trustThisDevice": "on",
            "_eventId": "submit",
        }
        resp, resp_text = await self._post(
            session, self._request_code_url, payload, stage="2fa_submit"
        )
        self._log(
            "submit_2fa_code",
            http_status=resp.status,
            method=self._selected_method,
        )

        tree = lxml_html.fromstring(resp_text)
        if tree.xpath('//input[@name="oneTimeCode"]'):
            page_err = extract_page_error(resp_text) or "验证码错误或已过期"
            raise Invalid2FACodeError(page_err, stage="2fa_submit")

        redirect_url = extract_redirect_url(resp_text)
        if not redirect_url:
            page_err = extract_page_error(resp_text)
            if page_err:
                raise Invalid2FACodeError(page_err, stage="2fa_submit")
            raise FormStructureChangedError(_safe_snippet(resp_text), stage="2fa_submit")

        cookies = await self._handle_redirect(session, redirect_url, stage="finalize")
        return FinalizeOutcome(cookies=cookies)

    async def aclose(self) -> None:
        """关闭 aiohttp 会话；多次调用安全。"""
        if self._session is not None:
            with contextlib.suppress(Exception):
                await self._session.close()
            self._session = None

    # ===== 多步链路的私有助手 =====

    async def _get_start(
        self, session: aiohttp.ClientSession
    ) -> tuple[aiohttp.ClientResponse, str]:
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        try:
            resp = await session.get(EA_START_URL)
        except aiohttp.ClientError as e:
            raise UpstreamError(f"GET start failed: {type(e).__name__}", stage="email") from e
        text = await resp.text()
        self._log("get_start", http_status=resp.status, duration_ms=_ms(loop, t0))
        return resp, text

    async def _post_email(
        self,
        session: aiohttp.ClientSession,
        prev_resp: aiohttp.ClientResponse,
        prev_text: str,
    ) -> tuple[aiohttp.ClientResponse, str]:
        values = self._base_form_values()
        form = build_form_payload(prev_text, values)
        resp, resp_text = await self._post(session, str(prev_resp.url), form, stage="email")
        self._log(
            "post_email",
            http_status=resp.status,
            form_keys=sorted(form.keys()),
        )

        tree = lxml_html.fromstring(resp_text)
        has_password_input = bool(tree.xpath('//input[@type="password" and @name="password"]'))
        if not has_password_input and not _looks_like_2fa_or_redirect(resp_text):
            page_err = extract_page_error(resp_text) or "EA 拒绝了该邮箱"
            raise EmailRejectedError(page_err, stage="email")

        return resp, resp_text

    async def _post_password(
        self,
        session: aiohttp.ClientSession,
        prev_resp: aiohttp.ClientResponse,
        prev_text: str,
    ) -> tuple[aiohttp.ClientResponse, str]:
        values = self._base_form_values()
        form = build_form_payload(prev_text, values)
        resp, resp_text = await self._post(session, str(prev_resp.url), form, stage="password")
        self._log(
            "post_password",
            http_status=resp.status,
            form_keys=sorted(form.keys()),
        )
        return resp, resp_text

    async def _accept_privacy(
        self,
        session: aiohttp.ClientSession,
        prev_resp: aiohttp.ClientResponse,
        _prev_text: str,
    ) -> tuple[aiohttp.ClientResponse, str]:
        payload = {"_readAccept": "on", "readAccept": "on", "_eventId": "accept"}
        try:
            resp, resp_text = await self._post(
                session, str(prev_resp.url), payload, stage="password"
            )
        except UpstreamError as e:
            raise PrivacyAcceptRequiredError("EA 隐私协议接受失败", stage="password") from e
        self._log("accept_privacy", http_status=resp.status)
        return resp, resp_text

    async def _request_code(self, session: aiohttp.ClientSession, method: str) -> str:
        masked = (
            get_email_method_masked_destination(self._post_password_html)
            if method == "EMAIL"
            else ""
        )
        payload = {
            "codeType": method,
            "maskedDestination": masked,
            "_codeType": method,
            "_eventId": "submit",
        }
        resp, _ = await self._post(session, self._post_password_url, payload, stage="2fa_request")
        self._log(
            "request_2fa_code",
            http_status=resp.status,
            method=method,
            has_masked_destination=bool(masked),
        )
        if resp.status != 200:
            raise UpstreamError(f"EA 拒绝请求 {method} 验证码", stage="2fa_request")
        self._request_code_url = str(resp.url)
        return masked

    async def _handle_redirect(
        self, session: aiohttp.ClientSession, url: str, *, stage: str
    ) -> LoginCookies:
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        try:
            resp = await session.get(url, allow_redirects=False)
        except aiohttp.ClientError as e:
            raise UpstreamError(f"GET redirect failed: {type(e).__name__}", stage=stage) from e

        remid, sid = _extract_remid_sid(resp)
        self._log(
            "redirect_extract_cookies",
            http_status=resp.status,
            duration_ms=_ms(loop, t0),
            cookie_keys=[k for k, v in (("remid", remid), ("sid", sid)) if v],
        )
        if not remid or not sid:
            raise CookieExtractionFailedError(stage=stage)

        location = resp.headers.get("Location")
        if not location:
            raise CookieExtractionFailedError("EA 重定向缺少 Location 头", stage=stage)

        t0 = loop.time()
        try:
            follow_resp = await session.get(location)
        except aiohttp.ClientError as e:
            raise UpstreamError(f"GET final follow failed: {type(e).__name__}", stage=stage) from e
        gw_session = _extract_gateway_session(follow_resp)
        self._log(
            "redirect_final_follow",
            http_status=follow_resp.status,
            duration_ms=_ms(loop, t0),
            has_gateway_session=bool(gw_session),
        )
        if not gw_session:
            raise CookieExtractionFailedError("未能提取 gatewaySessionId", stage=stage)
        return LoginCookies(remid=remid, sid=sid, gateway_session_id=gw_session)

    # ===== 通用 POST 助手与异常分类 =====

    async def _post(
        self,
        session: aiohttp.ClientSession,
        url: str,
        payload: dict[str, str],
        *,
        stage: str,
    ) -> tuple[aiohttp.ClientResponse, str]:
        try:
            resp = await session.post(url, data=payload)
        except aiohttp.ClientError as e:
            raise UpstreamError(f"POST {stage} failed: {type(e).__name__}", stage=stage) from e
        text = await resp.text()
        return resp, text

    # ===== 基础 =====

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            # 复用 BF1GatewayClient 的 SSL 配置：禁用证书验证以兼容部分网络环境
            # （EA 在国内偶尔出现证书链与 CDN 不匹配的 526 错误）。
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_ctx)
            # trust_env=True 让 aiohttp 读取 HTTP_PROXY / HTTPS_PROXY / NO_PROXY 环境变量，
            # 与 app.core.config.Settings 的 http_proxy / https_proxy / no_proxy 同源（都来自
            # 容器注入的同名环境变量）。部分网络环境必须经代理才能访问 accounts.ea.com；
            # 没有这一项，.env 里配的代理对本登录链路不生效。BF1GatewayClient 走的是显式
            # proxy=_get_proxy()，这里改用 trust_env 是因为它额外尊重 NO_PROXY 白名单。
            self._session = aiohttp.ClientSession(
                connector=connector,
                headers=_DEFAULT_HEADERS,
                trust_env=True,
            )
        return self._session

    def _base_form_values(self) -> dict[str, str]:
        return {
            "email": self._email,
            "regionCode": "CN",
            "phoneNumber": "",
            "password": self._password,
            "_eventId": "submit",
            "loginMethod": "emailPassword",
            "_rememberMe": "on",
            "rememberMe": "on",
        }

    def _log(self, step: str, **fields: object) -> None:
        # ``logger.bind`` 注入结构化字段；通过 core/logging.py 的全局 PII filter 兜底
        # 即使有人误传 email/password 也会被脱敏成 ``[REDACTED]``。
        logger.bind(component="ea_login", task_id=self._task_id, step=step, **fields).info(
            "ea_login.step"
        )


# ===== 模块级辅助 =====


def _ms(loop: asyncio.AbstractEventLoop, t0: float) -> int:
    """计算 event loop 时间差并转为毫秒整数。"""
    return int((loop.time() - t0) * 1000)


def _extract_remid_sid(resp: aiohttp.ClientResponse) -> tuple[str | None, str | None]:
    remid: str | None = None
    sid: str | None = None
    c_remid = resp.cookies.get("remid")
    if c_remid is not None:
        remid = c_remid.value
    c_sid = resp.cookies.get("sid")
    if c_sid is not None:
        sid = c_sid.value
    if remid and sid:
        return remid, sid
    set_cookies = resp.headers.getall("Set-Cookie", [])
    remid = remid or parse_set_cookie_pair(set_cookies, "remid")
    sid = sid or parse_set_cookie_pair(set_cookies, "sid")
    return remid, sid


def _extract_gateway_session(resp: aiohttp.ClientResponse) -> str | None:
    cookie = resp.cookies.get("gatewaySessionId")
    if cookie is not None:
        return cookie.value
    return parse_set_cookie_pair(resp.headers.getall("Set-Cookie", []), "gatewaySessionId")


def _looks_like_2fa_or_redirect(text: str) -> bool:
    """识别邮箱页提交后已经进入下一阶段的情形。"""
    return (
        "_codeType" in text
        or "window.location=" in text.replace(" ", "")
        or 'id="readAccept"' in text
        or '<input type="password"' in text
    )


def _safe_snippet(text: str, *, limit: int = 300) -> str:
    """从异常 HTML 中截一段供日志诊断使用。

    不做正则脱敏：诊断片段只进 :class:`FormStructureChanged` 异常的 ``snippet``
    字段，永远不应当被直接写入日志或返回给前端；最终输出到日志的是全局 PII
    filter 处理过的版本。
    """
    return text[:limit]


__all__ = [
    "EA_START_URL",
    "EALoginEngine",
    "FinalizeOutcome",
    "LoginCookies",
    "MethodOutcome",
    "StartOutcome",
]

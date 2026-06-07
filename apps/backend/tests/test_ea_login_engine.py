"""EALoginEngine.start() 状态机单元测试。

重点覆盖 EA juno 单页登录表单改版后的分类逻辑：第一次 POST（email + password 同表单）
之后，引擎要正确区分「凭据过期 / 密码错误 / 风控 / 2FA / redirect / 旧版两步流程 /
未知页」，而不是无条件再 POST 一次密码导致误报 FormStructureChangedError。

测试通过替换 ``EALoginEngine._ensure_session`` 注入一个脚本化的假 aiohttp 会话：
按 GET → POST → POST… 的调用顺序依次吐出预设响应，不发真实网络请求。
"""

from __future__ import annotations

import pytest
from app.domain.ea.login.exceptions import (
    CredentialsExpiredError,
    FormStructureChangedError,
    RiskBlockedError,
    WrongPasswordError,
)
from app.domain.ea.login.login_engine import EALoginEngine

# ===== 脱敏 HTML 样本（最小骨架，仅含分类器关心的元素）=====

# juno 单页登录页：email 与 password 同在一个 login-form。
_JUNO_START_PAGE = """
<html><body>
<form id="login-form" method="post">
    <input type="email" name="email" value="">
    <input type="password" name="password" value="">
    <input type="hidden" name="_eventId" value="submit">
    <input type="hidden" name="cid" value="">
    <input type="hidden" name="loginMethod" value="emailPassword">
</form>
</body></html>
"""

# juno 密码错误重试页：仍含 password 输入框 + 错误提示。
_JUNO_WRONG_PASSWORD_PAGE = """
<html><body>
<div class="otkinput-errorMsg" role="alert">
    Your credentials are incorrect. Please try again or reset your password.
</div>
<form id="login-form" method="post">
    <input type="password" name="password" value="">
    <input type="hidden" name="_eventId" value="submit">
</form>
</body></html>
"""

# juno 凭据过期页：含 EA "incorrect or have expired" 文案。
_JUNO_EXPIRED_PAGE = """
<html><body>
<div class="otkinput-errorMsg" role="alert">
    Your credentials are incorrect or have expired. Please try again or reset your password.
</div>
<form id="login-form" method="post">
    <input type="password" name="password" value="">
    <input type="hidden" name="_eventId" value="submit">
</form>
</body></html>
"""

# juno 风控页：含风控关键词。
_JUNO_RISK_PAGE = """
<html><body>
<div class="error" role="alert">
    We noticed something unusual. Please verify your identity to continue.
</div>
<form id="login-form" method="post">
    <input type="password" name="password" value="">
</form>
</body></html>
"""

# 2FA 单方式页（无 password 输入框，含 codeType radio）。
_TWO_FA_SINGLE_PAGE = """
<html><body>
<form id="login-form" method="post">
    <input type="radio" name="_codeType" id="codeType-EMAIL:a***@e***" value="EMAIL" checked>
</form>
</body></html>
"""

# 2FA 多方式页。
_TWO_FA_MULTI_PAGE = """
<html><body>
<form id="login-form" method="post">
    <input type="radio" name="_codeType" id="codeType-EMAIL:a***@e***" value="EMAIL" checked>
    <input type="radio" name="_codeType" id="codeType-APP" value="APP">
</form>
</body></html>
"""

# 引擎完全不认识的页（无 password / 无 2FA / 无 redirect / 无错误文本）。
_UNKNOWN_PAGE = """
<html><body>
<form id="otcForm" method="post">
    <input type="hidden" name="codeType" value="">
    <input type="hidden" name="_eventId" value="submit">
</form>
</body></html>
"""

# 旧版两步流程：密码页（含 password，无错误）。
_LEGACY_PASSWORD_PAGE = """
<html><body>
<form id="login-form" method="post">
    <input type="hidden" name="email" value="user@example.com">
    <input type="password" name="password" value="">
    <input type="hidden" name="_eventId" value="submit">
</form>
</body></html>
"""


class _FakeResponse:
    """脚本化的假 aiohttp 响应：只暴露 ``url`` 与 ``text()``。"""

    def __init__(self, html: str, url: str = "https://signin.ea.com/p/juno/login") -> None:
        self._html = html
        self.url = url
        self.status = 200

    async def text(self) -> str:
        return self._html


class _FakeSession:
    """按调用顺序回放预设响应的假会话。

    ``script`` 是 HTML 字符串列表；GET 与 POST 共用同一条时间线，与
    ``EALoginEngine`` 内部 GET → POST → (POST)… 的真实调用顺序对应。
    """

    def __init__(self, script: list[str]) -> None:
        self._script = script
        self._idx = 0

    def _next(self) -> _FakeResponse:
        html = self._script[self._idx]
        self._idx += 1
        return _FakeResponse(html)

    async def get(self, url, allow_redirects=True):
        return self._next()

    async def post(self, url, data=None):
        return self._next()

    async def close(self) -> None:
        return None


def _engine_with_script(script: list[str]) -> EALoginEngine:
    engine = EALoginEngine(task_id="t-test", email="user@example.com", password="pw")
    session = _FakeSession(script)

    async def _fake_ensure_session():
        return session

    engine._ensure_session = _fake_ensure_session  # type: ignore[method-assign]
    return engine


@pytest.mark.asyncio
async def test_juno_wrong_password_raises_wrong_password():
    """juno 单页：第一次 POST 返回密码错误页 → WrongPasswordError，不再多发 POST。"""
    engine = _engine_with_script([_JUNO_START_PAGE, _JUNO_WRONG_PASSWORD_PAGE])
    with pytest.raises(WrongPasswordError):
        await engine.start()


@pytest.mark.asyncio
async def test_juno_expired_credentials_raises_credentials_expired():
    """juno 单页：凭据过期文案 → CredentialsExpiredError（区别于普通密码错误）。"""
    engine = _engine_with_script([_JUNO_START_PAGE, _JUNO_EXPIRED_PAGE])
    with pytest.raises(CredentialsExpiredError):
        await engine.start()


@pytest.mark.asyncio
async def test_juno_risk_page_raises_risk_blocked():
    """juno 单页：风控关键词 → RiskBlockedError。"""
    engine = _engine_with_script([_JUNO_START_PAGE, _JUNO_RISK_PAGE])
    with pytest.raises(RiskBlockedError):
        await engine.start()


@pytest.mark.asyncio
async def test_juno_single_2fa_method_enters_need_code():
    """juno 单页：密码正确且单一 2FA 方式 → 自动请求验证码，next_step=need_code。"""
    # GET start → POST(email+password) 得到 2FA 页 → POST(request_code) 回任意页。
    engine = _engine_with_script([_JUNO_START_PAGE, _TWO_FA_SINGLE_PAGE, _TWO_FA_SINGLE_PAGE])
    outcome = await engine.start()
    assert outcome.next_step == "need_code"
    assert outcome.selected_method == "EMAIL"


@pytest.mark.asyncio
async def test_juno_multi_2fa_method_enters_need_method():
    """juno 单页：密码正确且多种 2FA 方式 → next_step=need_method，等待用户选。"""
    engine = _engine_with_script([_JUNO_START_PAGE, _TWO_FA_MULTI_PAGE])
    outcome = await engine.start()
    assert outcome.next_step == "need_method"
    assert set(outcome.available_methods) == {"EMAIL", "APP"}


@pytest.mark.asyncio
async def test_classifier_unknown_page_raises_form_structure_changed():
    """分类器兜底：既无 password、又无 2FA / redirect / 错误文本的页面 →
    FormStructureChangedError，并带 snippet 供日志诊断。

    直接单测 ``_classify_post_password_response``：``_post_email`` 自身有一层 guard，
    完全不认识的页面在第一次 POST 后会被它先判成 ``EmailRejectedError``，走不到
    分类器末端，因此兜底分支只能在分类器层面验证。
    """
    engine = _engine_with_script([_JUNO_START_PAGE])
    with pytest.raises(FormStructureChangedError) as exc:
        await engine._classify_post_password_response(
            None, _FakeResponse(_UNKNOWN_PAGE), _UNKNOWN_PAGE
        )
    assert exc.value.snippet  # snippet 非空，供日志诊断


@pytest.mark.asyncio
async def test_legacy_two_step_pure_password_page_reposts():
    """旧版两步流程兼容：第一次 POST 返回纯密码页（含 password、无错误）→ 补发一次
    密码 POST，再对其结果分类。

    时间线：GET start → POST 得到纯密码页（无错误提示）→ 补发 POST 得到 2FA 多方式页。
    """
    engine = _engine_with_script([_JUNO_START_PAGE, _LEGACY_PASSWORD_PAGE, _TWO_FA_MULTI_PAGE])
    outcome = await engine.start()
    assert outcome.next_step == "need_method"

"""EA 登录页面解析器单元测试。

样本 HTML 是脱敏后的最小骨架，覆盖以下页面形态：

- 邮箱页（仅 email 输入框）
- 密码页（password + 表单字段）
- 2FA 方法选择页（多个 codeType radio）
- 隐私协议接受页（readAccept checkbox）
- 错误页（class=error 的提示）
- 中间跳转页（``window.location="..."``）
"""

from __future__ import annotations

from app.domain.ea.login.form_parser import (
    build_form_payload,
    extract_available_auth_methods,
    extract_page_error,
    extract_redirect_url,
    get_email_method_masked_destination,
    has_privacy_accept_checkbox,
    looks_like_login_form,
    parse_set_cookie_pair,
)

_EMAIL_PAGE = """
<html><body>
<form id="login-form" action="/login" method="post">
    <input type="hidden" name="cid" value="abc">
    <input type="hidden" name="_eventId" value="submit">
    <input type="email" name="email" value="">
    <input type="hidden" name="loginMethod" value="emailPassword">
    <input type="checkbox" name="rememberMe" checked>
    <input type="hidden" name="_rememberMe" value="on">
</form>
</body></html>
"""

_PASSWORD_PAGE = """
<html><body>
<form id="login-form" action="/login" method="post">
    <input type="hidden" name="cid" value="abc">
    <input type="hidden" name="_eventId" value="submit">
    <input type="hidden" name="email" value="user@example.com">
    <input type="password" name="password" value="">
    <input type="checkbox" name="rememberMe" checked>
</form>
</body></html>
"""

_TWO_FA_PAGE = """
<html><body>
<form id="login-form" action="/2fa" method="post">
    <input type="hidden" name="_eventId" value="submit">
    <input type="radio" name="_codeType" id="codeType-EMAIL:a***@e***" value="EMAIL" checked>
    <input type="radio" name="_codeType" id="codeType-APP" value="APP">
</form>
</body></html>
"""

_PRIVACY_PAGE = """
<html><body>
<form id="login-form" action="/privacy" method="post">
    <input type="checkbox" id="readAccept" name="readAccept" value="on">
    <input type="hidden" name="_readAccept" value="on">
    <input type="hidden" name="_eventId" value="accept">
</form>
</body></html>
"""

_ERROR_PAGE = """
<html><body>
<div class="login-error" role="alert">Sorry, your account name or password was incorrect.</div>
<div class="error">Sign in</div>
<form id="login-form">
    <input type="password" name="password">
</form>
</body></html>
"""

_REDIRECT_PAGE = """
<html><body>
<script>
window.location="https://signin.ea.com/p/web2/redirect?code=abc&state=def";
</script>
</body></html>
"""


def test_build_form_payload_only_includes_existing_fields():
    """邮箱阶段只能提交 email + 隐藏字段，不带 password。"""
    values = {
        "email": "user@example.com",
        "password": "secret",
        "_eventId": "submit",
        "loginMethod": "emailPassword",
        "rememberMe": "on",
    }
    payload = build_form_payload(_EMAIL_PAGE, values)
    assert payload["email"] == "user@example.com"
    assert payload["_eventId"] == "submit"
    assert payload["loginMethod"] == "emailPassword"
    assert payload["rememberMe"] == "on"
    # password 字段在邮箱页不存在，应被排除
    assert "password" not in payload


def test_build_form_payload_password_stage_includes_password():
    values = {"email": "user@example.com", "password": "secret", "_eventId": "submit"}
    payload = build_form_payload(_PASSWORD_PAGE, values)
    assert payload["password"] == "secret"
    assert payload["email"] == "user@example.com"


def test_build_form_payload_skips_unchecked_radio_and_checkbox():
    page = """
    <html><body><form id="login-form">
        <input type="hidden" name="keep" value="default">
        <input type="checkbox" name="optional">
        <input type="radio" name="choice" value="A">
    </form></body></html>
    """
    payload = build_form_payload(page, {})
    assert payload == {"keep": "default"}


def test_build_form_payload_returns_copy_when_no_form():
    payload = build_form_payload("<html><body>nothing</body></html>", {"foo": "bar"})
    assert payload == {"foo": "bar"}


def test_extract_available_auth_methods_orders_by_html():
    methods = extract_available_auth_methods(_TWO_FA_PAGE)
    assert methods == ["EMAIL", "APP"]


def test_extract_available_auth_methods_empty_when_no_2fa():
    assert extract_available_auth_methods(_PASSWORD_PAGE) == []


def test_has_privacy_accept_checkbox():
    assert has_privacy_accept_checkbox(_PRIVACY_PAGE) is True
    assert has_privacy_accept_checkbox(_PASSWORD_PAGE) is False


def test_get_email_method_masked_destination_extracts_id_suffix():
    masked = get_email_method_masked_destination(_TWO_FA_PAGE)
    assert masked == "a***@e***"


def test_get_email_method_masked_destination_empty_when_absent():
    assert get_email_method_masked_destination(_PASSWORD_PAGE) == ""


def test_extract_page_error_filters_noise_and_truncates():
    error = extract_page_error(_ERROR_PAGE)
    # "Sign in" 在 noise 列表中，应当被过滤
    assert error is not None
    assert "password was incorrect" in error.lower()
    assert "sign in" not in error.lower()


def test_extract_page_error_none_when_no_error_div():
    assert extract_page_error(_PASSWORD_PAGE) is None


def test_extract_redirect_url_finds_window_location():
    url = extract_redirect_url(_REDIRECT_PAGE)
    assert url is not None
    assert url.startswith("https://signin.ea.com/")


def test_extract_redirect_url_tolerates_whitespace():
    page = '<script>window.location = "https://example.com";</script>'
    url = extract_redirect_url(page)
    assert url == "https://example.com"


def test_extract_redirect_url_none_when_absent():
    assert extract_redirect_url(_PASSWORD_PAGE) is None


def test_parse_set_cookie_pair_extracts_value():
    headers = [
        "remid=abc123; Path=/; Domain=.ea.com; Secure",
        "sid=def456; Path=/; HttpOnly",
        "other=ignore; Path=/",
    ]
    assert parse_set_cookie_pair(headers, "remid") == "abc123"
    assert parse_set_cookie_pair(headers, "sid") == "def456"
    assert parse_set_cookie_pair(headers, "missing") is None


def test_parse_set_cookie_pair_ignores_expired():
    # Max-Age=0 是 EA 用于删除 cookie 的写法，必须跳过
    headers = [
        "sid=stale; Max-Age=0; Path=/",
        "sid=fresh; Path=/; Secure",
    ]
    assert parse_set_cookie_pair(headers, "sid") == "fresh"


def test_looks_like_login_form_matches_login_form_id():
    assert looks_like_login_form(_PASSWORD_PAGE) is True
    assert looks_like_login_form(_REDIRECT_PAGE) is False

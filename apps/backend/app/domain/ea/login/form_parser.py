"""EA 登录页面的纯函数式 HTML 解析。

所有函数：
- 输入：``str`` 形式的 HTML 文本（不依赖 aiohttp Response）。
- 输出：基本类型 / dataclass / 列表。
- 不抛业务异常；解析不到结果时返回空值，由调用方判断是否触发 ``FormStructureChanged``。
- 不写日志（避免把页面文本带入日志）。

设计原则：把所有 XPath / 正则集中在本模块，EA 改版时只需要更新这里 + 测试 fixture。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from lxml import html as lxml_html

# EA 登录链路里出现 ``window.location="..."`` 的中间页用此正则提取跳转目标。
# 注意：必须先把 HTML 中的空白去掉再匹配，因为 EA 模板偶尔会在引号附近插入空格。
_REDIRECT_RE = re.compile(r'window\.location="([^"]+)"')

# Set-Cookie 头里提取 ``key=value`` 的兜底正则，仅在 aiohttp ``CookieJar`` 解析失败时使用。
_SET_COOKIE_KV_RE = re.compile(r"(?P<key>[A-Za-z0-9_]+)=(?P<value>[^;]+)")

# 页面错误文本会包含大量与表单 label 同名的噪音词，按小写比对剔除。
_ERROR_NOISE_WORDS = frozenset(
    {
        "password",
        "email",
        "phone or email",
        "sign in",
        "sign-in",
        "next",
        "continue",
    }
)


def build_form_payload(
    html_text: str,
    values: dict[str, str],
    *,
    form_id: str = "login-form",
) -> dict[str, str]:
    """根据当前页面的表单结构构造 POST payload。

    EA 的登录页是多步表单：邮箱页只有 email 输入框，密码页才出现 password；同一份
    ``values`` 中包含邮箱 + 密码 + 各种隐藏字段，但每一步只能提交当前页实际存在的
    字段，否则会被服务端拒绝。本函数遍历当前 HTML 中所有具名 input 输出 payload：

    - 已选中的 ``values[name]`` 优先覆盖默认值。
    - 未选中的 checkbox / radio 跳过。
    - 没有显式 value 的 input 写空串占位。

    Args:
        html_text: 上一步 EA 响应正文。
        values: 调用方提供的字段映射（email / password / 各类 _eventId 等）。
        form_id: 默认匹配 EA 标准登录表单 id；找不到时退化为第一个 form。

    Returns:
        可直接传给 ``aiohttp.ClientSession.post(data=...)`` 的字段映射。如果页面没有
        任何 form，返回 ``values`` 的浅拷贝兜底。
    """
    tree = lxml_html.fromstring(html_text)
    forms = tree.xpath(f'//form[@id="{form_id}"]') or tree.xpath("//form")
    if not forms:
        return values.copy()

    payload: dict[str, str] = {}
    for element in forms[0].xpath(".//input[@name]"):
        name = element.get("name")
        if not name:
            continue
        input_type = (element.get("type") or "").lower()
        # 未勾选的 checkbox / radio 不提交。EA 的表单沿用 Spring Web Flow 的 ``_field`` +
        # ``field`` 双控件惯例，未勾选时只发 ``_field``，这里保持同样行为。
        if input_type in {"checkbox", "radio"} and element.get("checked") is None:
            continue
        payload[name] = values.get(name, element.get("value") or "")
    return payload


def extract_available_auth_methods(html_text: str) -> list[str]:
    """从密码页响应里提取 EA 提供的全部 2FA 方式标识。

    EA 用一组 ``<input type="radio" name="_codeType">`` 表达可选方式，常见取值为
    ``EMAIL`` / ``APP`` / ``SMS``，按页面出现顺序返回。

    Returns:
        方式标识列表；非 2FA 页面返回空列表。
    """
    tree = lxml_html.fromstring(html_text)
    radios = tree.xpath('//input[@type="radio" and @name="_codeType"]')
    methods: list[str] = []
    for radio in radios:
        value = radio.get("value")
        if value:
            methods.append(value)
    return methods


def has_privacy_accept_checkbox(html_text: str) -> bool:
    """判断当前页面是否要求用户接受新的隐私协议。

    EA 在密码页后偶尔插入一个隐私协议接受步骤（``<input id="readAccept">``），
    需要额外 POST 一次 ``_eventId=accept`` 才能继续。
    """
    tree = lxml_html.fromstring(html_text)
    nodes = tree.xpath('//input[@type="checkbox" and @id="readAccept" and @name="readAccept"]')
    return bool(nodes)


def get_email_method_masked_destination(html_text: str) -> str:
    """EMAIL 验证方式下提取脱敏后的目标邮箱（如 ``a***@b***``）。

    EA 把脱敏字符串编码进 radio 的 ``id`` 属性后缀（``codeType-EMAIL:abc***@def``），
    取 ``id`` 最后一个 ``:`` 之后的部分；不存在时返回空串。

    Returns:
        脱敏后的目标字符串，可直接展示给前端；禁止落日志。
    """
    tree = lxml_html.fromstring(html_text)
    nodes = tree.xpath('//input[@type="radio" and @name="_codeType" and @value="EMAIL"]')
    if not nodes:
        return ""
    raw_id = nodes[0].get("id") or ""
    if ":" not in raw_id:
        return ""
    return raw_id.rsplit(":", 1)[-1]


def extract_page_error(html_text: str) -> str | None:
    """从错误页（密码错、风控、邮箱不存在等）中抽取面向用户的提示。

    EA 把错误信息塞在 ``class`` 含 ``error`` / ``alert``、``role="alert"`` 或 ``id``
    含 ``error`` 的元素里。剔除与按钮文案重合的噪音词后，按出现顺序去重拼接。

    Returns:
        最多 300 字符的错误文案；无错误返回 ``None``。
    """
    try:
        tree = lxml_html.fromstring(html_text)
    except (ValueError, lxml_html.etree.ParserError):
        return None
    raw_texts: Iterable[str] = tree.xpath(
        "//div["
        'contains(@class,"error") or contains(@class,"alert") '
        'or @role="alert" or contains(@id,"error")'
        "]//text()"
    )
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in raw_texts:
        text = raw.strip()
        if not text or text.lower() in _ERROR_NOISE_WORDS:
            continue
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    if not cleaned:
        return None
    return " ".join(cleaned)[:300]


def extract_redirect_url(html_text: str) -> str | None:
    """从 EA 的中间页提取 ``window.location="..."`` 跳转目标。

    EA 把最终重定向写在内联 ``<script>`` 里而非 ``Location`` 头，需要正则提取。
    匹配前先去除空白字符以容忍模板里的少量空格。
    """
    if not html_text:
        return None
    match = _REDIRECT_RE.search(html_text.replace(" ", ""))
    return match.group(1) if match else None


def parse_set_cookie_pair(
    set_cookie_headers: Iterable[str],
    cookie_name: str,
) -> str | None:
    """从 ``Set-Cookie`` 头列表里提取指定 cookie 的有效值。

    aiohttp ``response.cookies`` 在某些重定向场景拿不到 EA 写下的 cookie，需要直接
    扫描原始头。``Max-Age=0`` 表示删除操作，跳过；同名 cookie 多次出现时返回首个
    有效值，符合「EA 在登录完成时一次性写入 remid/sid」的惯例。

    Args:
        set_cookie_headers: ``response.headers.getall("Set-Cookie", [])`` 的结果。
        cookie_name: 要提取的 cookie 名（``remid`` / ``sid`` / ``gatewaySessionId``）。

    Returns:
        cookie 值；提取不到返回 ``None``。
    """
    prefix = f"{cookie_name}="
    for raw in set_cookie_headers:
        if prefix not in raw:
            continue
        if "Max-Age=0" in raw:
            continue
        match = _SET_COOKIE_KV_RE.search(raw)
        if match and match.group("key") == cookie_name:
            return match.group("value")
    return None


def looks_like_login_form(html_text: str) -> bool:
    """快速判断响应是否仍是 EA 登录页（用来兜底识别异常跳转）。"""
    try:
        tree = lxml_html.fromstring(html_text)
    except (ValueError, lxml_html.etree.ParserError):
        return False
    return bool(tree.xpath('//form[@id="login-form"]')) or bool(
        tree.xpath('//input[@name="password"]')
    )


__all__ = [
    "build_form_payload",
    "extract_available_auth_methods",
    "extract_page_error",
    "extract_redirect_url",
    "get_email_method_masked_destination",
    "has_privacy_accept_checkbox",
    "looks_like_login_form",
    "parse_set_cookie_pair",
]

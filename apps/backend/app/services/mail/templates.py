"""邮件模板：每类信一个函数，返回 MailMessage。

版式统一：黑底标题条 + 琥珀色细线（和站点一致），白色正文卡片，一个主按钮，按钮下面附纯文本
链接（有的邮箱会屏蔽按钮），最后是请求时间和来源 IP，方便收信人判断是不是本人操作。
HTML 只用 table 布局和内联样式，QQ 邮箱、Gmail、Outlook 都能正常显示。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from html import escape

from app.services.mail.sender import MailMessage

SITE_NAME = "BF Manager"
_BEIJING = timezone(timedelta(hours=8))

_AMBER = "#f59e0b"
_INK = "#18181b"
_MUTED = "#71717a"


@dataclass(frozen=True)
class RequestMeta:
    """发起这封信的请求：时间和来源 IP（打码后写进信里）"""

    at: datetime
    ip: str | None = None

    @classmethod
    def now(cls, ip: str | None) -> RequestMeta:
        return cls(at=datetime.now(UTC), ip=ip)


def mask_ip(ip: str | None) -> str | None:
    """IPv4 留前三段，IPv6 留前四组：够收信人认出是不是自己，又不完整暴露请求方。"""
    if not ip:
        return None
    if ":" in ip:
        groups = ip.split(":")
        return ":".join(groups[:4]) + ":…"
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + ".*"
    return None


def _fmt_time(at: datetime) -> str:
    return at.astimezone(_BEIJING).strftime("%Y-%m-%d %H:%M")


def _meta_lines(meta: RequestMeta) -> list[str]:
    lines = [f"请求时间：{_fmt_time(meta.at)}（北京时间）"]
    masked = mask_ip(meta.ip)
    if masked:
        lines.append(f"请求来源 IP：{masked}")
    return lines


def _render(
    *,
    to: str,
    kind: str,
    subject: str,
    title: str,
    paragraphs: list[str],
    button: tuple[str, str] | None,
    note: str | None,
    meta: RequestMeta,
    footer: str,
) -> MailMessage:
    """paragraphs 允许少量内联标签（<strong>），调用方负责先 escape 动态内容。"""
    meta_lines = _meta_lines(meta)

    text_parts = [title, ""]
    text_parts += [_strip_tags(p) for p in paragraphs]
    if button:
        text_parts += ["", f"{button[0]}：", button[1]]
    if note:
        text_parts += ["", note]
    text_parts += ["", *meta_lines, "", footer, "", f"— {SITE_NAME}"]
    text = "\n".join(text_parts)

    body_html = "".join(
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.7;color:{_INK};">{p}</p>'
        for p in paragraphs
    )
    button_html = ""
    if button:
        label, url = escape(button[0]), escape(button[1], quote=True)
        button_html = (
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0 8px;">'
            f'<tr><td style="background:{_AMBER};border-radius:4px;">'
            f'<a href="{url}" style="display:inline-block;padding:12px 26px;font-size:15px;'
            f'font-weight:600;color:#111111;text-decoration:none;">{label}</a>'
            "</td></tr></table>"
            f'<p style="margin:0 0 6px;font-size:12px;line-height:1.6;color:{_MUTED};">'
            "按钮打不开的话，把下面的链接复制到浏览器：</p>"
            f'<p style="margin:0 0 6px;font-size:12px;line-height:1.6;word-break:break-all;">'
            f'<a href="{url}" style="color:#b45309;">{url}</a></p>'
        )
    note_html = (
        f'<p style="margin:18px 0 0;font-size:13px;line-height:1.7;color:{_MUTED};">'
        f"{escape(note)}</p>"
        if note
        else ""
    )
    meta_html = "".join(
        f'<div style="font-size:12px;line-height:1.8;color:{_MUTED};">{escape(line)}</div>'
        for line in meta_lines
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#f4f4f5;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
  style="max-width:560px;background:#ffffff;border-radius:6px;overflow:hidden;
  font-family:-apple-system,'PingFang SC','Microsoft YaHei','Helvetica Neue',Arial,sans-serif;">
<tr><td style="background:#0b0b0c;padding:18px 28px;border-bottom:3px solid {_AMBER};">
  <span style="font-size:14px;font-weight:700;letter-spacing:4px;color:#ffffff;">BF-MANAGER</span>
</td></tr>
<tr><td style="padding:28px 28px 8px;">
  <h1 style="margin:0 0 18px;font-size:20px;line-height:1.4;color:{_INK};">{escape(title)}</h1>
  {body_html}{button_html}{note_html}
</td></tr>
<tr><td style="padding:16px 28px 24px;">
  <div style="border-top:1px solid #e4e4e7;padding-top:14px;">{meta_html}
  <div style="margin-top:10px;font-size:12px;line-height:1.7;color:{_MUTED};">{escape(footer)}</div>
  </div>
</td></tr>
</table>
<div style="padding:14px 0 0;font-size:11px;color:#a1a1aa;font-family:Arial,sans-serif;">
  这封信由系统自动发送，请不要直接回复。</div>
</td></tr></table>
</body></html>"""

    return MailMessage(to=to, subject=subject, text=text, html=html, kind=kind)


def _group_line(group_name: str | None) -> list[str]:
    if not group_name:
        return []
    return [f"完成后会自动加入群组 <strong>{escape(group_name)}</strong>。"]


def _strip_tags(s: str) -> str:
    return s.replace("<strong>", "").replace("</strong>", "")


_NOT_ME = "如果这不是你本人的操作，忽略这封信即可，账号不会有任何变化。"


def register_ea(
    *,
    to: str,
    persona_name: str,
    url: str,
    ttl_hours: int,
    meta: RequestMeta,
    group_name: str | None = None,
) -> MailMessage:
    name = escape(persona_name)
    return _render(
        to=to,
        kind="register_ea",
        subject=f"【{SITE_NAME}】完成注册：确认绑定 EA 账号 {persona_name}",
        title="完成注册",
        paragraphs=[
            f"有人用这个 EA 账号的邮箱申请注册 {SITE_NAME}，要绑定的 EA 账号是 <strong>{name}</strong>。",
            "点下面的按钮设置登录密码，注册就完成了。以后用这个邮箱和密码登录。",
            *_group_line(group_name),
        ],
        button=("设置密码，完成注册", url),
        note=f"链接 {ttl_hours} 小时内有效，只能使用一次。",
        meta=meta,
        footer=_NOT_ME,
    )


def register_plain(
    *, to: str, url: str, ttl_hours: int, meta: RequestMeta, group_name: str | None = None
) -> MailMessage:
    return _render(
        to=to,
        kind="register_plain",
        subject=f"【{SITE_NAME}】验证邮箱，完成注册",
        title="验证邮箱",
        paragraphs=[
            f"有人用这个邮箱申请注册 {SITE_NAME}。",
            "点下面的按钮设置登录密码。注册后还要绑定一个 EA 账号（填 remid，或用 EA 账号密码登录一次）才能开始使用。",
            *_group_line(group_name),
        ],
        button=("设置密码", url),
        note=f"链接 {ttl_hours} 小时内有效，只能使用一次。",
        meta=meta,
        footer=_NOT_ME,
    )


def claim_legacy(
    *,
    to: str,
    persona_name: str,
    url: str,
    ttl_hours: int,
    meta: RequestMeta,
    group_name: str | None = None,
) -> MailMessage:
    name = escape(persona_name)
    return _render(
        to=to,
        kind="claim",
        subject=f"【{SITE_NAME}】认领你的旧账号",
        title="认领旧账号",
        paragraphs=[
            f"EA 账号 <strong>{name}</strong> 以前用 remid 登录过 {SITE_NAME}，留下了一个旧账号。",
            "现在改成邮箱和密码登录。点下面的按钮设置密码，旧账号的服务器权限、操作记录都会保留。",
            *_group_line(group_name),
        ],
        button=("设置密码，认领账号", url),
        note=f"链接 {ttl_hours} 小时内有效，只能使用一次。",
        meta=meta,
        footer=_NOT_ME,
    )


def already_registered(
    *, to: str, persona_name: str | None, login_url: str, forgot_url: str, meta: RequestMeta
) -> MailMessage:
    who = (
        f"EA 账号 <strong>{escape(persona_name)}</strong> 已经绑定在一个 {SITE_NAME} 账号上"
        if persona_name
        else f"这个邮箱已经注册过 {SITE_NAME}"
    )
    return _render(
        to=to,
        kind="already_registered",
        subject=f"【{SITE_NAME}】这个账号已经注册过了",
        title="账号已经存在",
        paragraphs=[
            f"有人用这个邮箱申请注册 {SITE_NAME}，但{who}，不需要再注册。",
            f"如果是你本人，直接登录就好；忘了密码可以在登录页点“忘记密码”：{escape(forgot_url)}",
        ],
        button=("去登录", login_url),
        note=None,
        meta=meta,
        footer=_NOT_ME,
    )


def reset_password(*, to: str, url: str, ttl_hours: int, meta: RequestMeta) -> MailMessage:
    return _render(
        to=to,
        kind="reset",
        subject=f"【{SITE_NAME}】重置登录密码",
        title="重置登录密码",
        paragraphs=[
            f"有人申请重置你的 {SITE_NAME} 登录密码。",
            "点下面的按钮设置新密码。重置后，其他设备上的登录会全部退出。",
        ],
        button=("设置新密码", url),
        note=f"链接 {ttl_hours} 小时内有效，只能使用一次。",
        meta=meta,
        footer="如果这不是你本人的操作，忽略这封信即可，原密码继续有效。",
    )


def set_email(
    *, to: str, persona_name: str, url: str, ttl_hours: int, meta: RequestMeta
) -> MailMessage:
    name = escape(persona_name)
    return _render(
        to=to,
        kind="set_email",
        subject=f"【{SITE_NAME}】验证登录邮箱",
        title="验证登录邮箱",
        paragraphs=[
            f"你正在给 {SITE_NAME} 账号（EA：<strong>{name}</strong>）设置登录邮箱。",
            "点下面的按钮验证邮箱并设置密码，以后就用这个邮箱和密码登录。",
        ],
        button=("验证邮箱，设置密码", url),
        note=f"链接 {ttl_hours} 小时内有效，只能使用一次。",
        meta=meta,
        footer=_NOT_ME,
    )


def password_changed(*, to: str, forgot_url: str, meta: RequestMeta) -> MailMessage:
    return _render(
        to=to,
        kind="password_changed",
        subject=f"【{SITE_NAME}】登录密码已修改",
        title="登录密码已修改",
        paragraphs=[
            f"你的 {SITE_NAME} 登录密码刚刚修改成功，其他设备上的登录已经全部退出。",
            "如果不是你本人操作，请马上点下面的按钮重置密码，并检查邮箱和 EA 账号是否安全。",
        ],
        button=("重置密码", forgot_url),
        note=None,
        meta=meta,
        footer="是你本人修改的话，不用理会这封信。",
    )


def group_problems(*, to: str, group_name: str, lines: list[str], url: str) -> MailMessage:
    """群组每日复核发现新问题时发给群主。lines 由调用方 escape"""
    return _render(
        to=to,
        kind="group_problems",
        subject=f"【{SITE_NAME}】群组「{group_name}」的服务器需要处理",
        title=f"群组「{group_name}」的服务器需要处理",
        paragraphs=[
            "今天的例行检查发现了下面这些问题：",
            *(f"· {line}" for line in lines),
            "服务账号登录失败的，重新提交一次凭据；服务账号不再是管理员的，在游戏里把它加回来，"
            "或者给这台服换一个执行账号。",
        ],
        button=("打开群组", url),
        note=None,
        meta=RequestMeta.now(None),
        footer="你是这个群的群主，所以收到这封信。",
    )

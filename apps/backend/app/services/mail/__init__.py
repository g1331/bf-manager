"""发信：通道（sender）与模板（templates）"""

from app.services.mail.sender import (
    LogMailSender,
    MailMessage,
    MailSender,
    get_mail_sender,
    set_mail_sender,
)

__all__ = ["LogMailSender", "MailMessage", "MailSender", "get_mail_sender", "set_mail_sender"]

"""Тексты писем.

Оформление сдержанное: почтовые клиенты режут стили, а брендбук запрещает
градиенты и тени. Держим один акцент, моноширинные числа и явную подпись
о служебном характере письма.
"""

from __future__ import annotations

from app.config import get_settings
from app.core.mail import Letter
from app.core.money import money

FOREST = "#0E3B21"
GREEN = "#22A74E"
INK = "#101613"
SLATE = "#5A655D"
LINE = "#E3E7E3"
MIST = "#F5F7F5"

FOOTER_TEXT = (
    "Это письмо отправлено системой IT-HONA CORE. Отвечать на него не нужно."
)


def _wrap(title: str, body_html: str, action: tuple[str, str] | None = None) -> str:
    """Общий каркас письма. Таблицы, а не флексбокс: почтовые клиенты
    современную вёрстку поддерживают плохо."""
    button = ""
    if action:
        label, url = action
        button = f"""
        <tr><td style="padding:24px 0 0">
          <a href="{url}" style="display:inline-block;background:{GREEN};
             color:#FFFFFF;text-decoration:none;font-weight:600;
             padding:12px 20px;border-radius:4px">{label}</a>
        </td></tr>"""

    return f"""<!doctype html>
<html lang="ru"><body style="margin:0;padding:24px;background:{MIST};
  font-family:Arial,Helvetica,sans-serif;color:{INK}">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0"
    style="max-width:560px;margin:0 auto;background:#FFFFFF;
    border:1px solid {LINE};border-radius:4px">
    <tr><td style="background:{FOREST};padding:16px 24px">
      <span style="color:#FFFFFF;font-weight:bold;letter-spacing:0.06em">
        IT-HONA</span>
      <span style="color:#FFFFFF;opacity:0.7;font-size:12px;
        letter-spacing:0.16em"> CORE</span>
    </td></tr>
    <tr><td style="padding:24px">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"
        width="100%">
        <tr><td style="font-size:19px;font-weight:bold;padding-bottom:12px">
          {title}</td></tr>
        <tr><td style="font-size:15px;line-height:1.55">{body_html}</td></tr>
        {button}
      </table>
    </td></tr>
    <tr><td style="padding:16px 24px;border-top:1px solid {LINE};
      font-size:12px;color:{SLATE}">{FOOTER_TEXT}</td></tr>
  </table>
</body></html>"""


def password_reset(*, full_name: str, url: str) -> Letter:
    minutes = get_settings().password_reset_ttl_minutes
    text = (
        f"{full_name}, здравствуйте.\n\n"
        "Кто-то запросил восстановление пароля для вашей учётной записи "
        "в IT-HONA CORE. Чтобы задать новый пароль, откройте ссылку:\n\n"
        f"{url}\n\n"
        f"Ссылка действует {minutes} мин и срабатывает один раз.\n\n"
        "Если вы этого не запрашивали — просто удалите письмо. Пароль "
        "останется прежним, а без ссылки в систему никто не войдёт.\n\n"
        f"{FOOTER_TEXT}"
    )
    html = _wrap(
        "Восстановление пароля",
        f"<p style=\"margin:0 0 12px\">{full_name}, здравствуйте.</p>"
        "<p style=\"margin:0 0 12px\">Кто-то запросил восстановление пароля "
        "для вашей учётной записи. Чтобы задать новый, нажмите кнопку ниже.</p>"
        f"<p style=\"margin:0;color:{SLATE};font-size:13px\">Ссылка действует "
        f"{minutes} мин и срабатывает один раз. Если вы этого не запрашивали — "
        "удалите письмо, пароль останется прежним.</p>",
        action=("Задать новый пароль", url),
    )
    return Letter(
        to="", subject="Восстановление пароля · IT-HONA CORE", text=text, html=html
    )


def request_awaiting_approval(
    *,
    approver_name: str,
    employee_name: str,
    number: str,
    project: str,
    amount,
    url: str,
) -> Letter:
    summary = f"{employee_name} · {project} · {money(amount)} сомони"
    text = (
        f"{approver_name}, здравствуйте.\n\n"
        f"Новая заявка на согласование: {number}\n"
        f"{summary}\n\n"
        f"Открыть: {url}\n\n"
        "Уведомления можно отключить в разделе «Параметры».\n\n"
        f"{FOOTER_TEXT}"
    )
    html = _wrap(
        "Заявка ждёт решения",
        f"<p style=\"margin:0 0 12px\">{approver_name}, здравствуйте.</p>"
        "<p style=\"margin:0 0 12px\">На согласование поступила заявка "
        f"<strong>{number}</strong>.</p>"
        f"<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" "
        f"border=\"0\" width=\"100%\" style=\"background:{MIST};"
        f"border:1px solid {LINE};padding:12px\">"
        f"<tr><td style=\"font-size:14px\">{employee_name}<br>"
        f"<span style=\"color:{SLATE}\">{project}</span></td>"
        f"<td align=\"right\" style=\"font-family:'Courier New',monospace;"
        f"font-weight:bold;white-space:nowrap\">{money(amount)}</td></tr></table>"
        f"<p style=\"margin:12px 0 0;color:{SLATE};font-size:13px\">"
        "Уведомления можно отключить в разделе «Параметры».</p>",
        action=("Перейти к согласованию", url),
    )
    return Letter(to="", subject=f"Заявка {number} ждёт решения", text=text, html=html)


def test_letter(*, to: str) -> Letter:
    """Проверочное письмо: подтверждает, что SMTP настроен верно."""
    text = (
        "Это проверочное письмо из IT-HONA CORE.\n\n"
        "Если вы его получили, отправка почты настроена правильно.\n\n"
        f"{FOOTER_TEXT}"
    )
    html = _wrap(
        "Проверка почты",
        "<p style=\"margin:0\">Если вы читаете это письмо, отправка почты "
        "из IT-HONA CORE настроена правильно.</p>",
    )
    return Letter(to=to, subject="Проверка почты · IT-HONA CORE", text=text, html=html)

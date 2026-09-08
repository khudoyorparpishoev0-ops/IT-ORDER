"""Команда настройки бота: `python -m app.telegram_setup`."""

from __future__ import annotations

import pytest

from app import telegram_setup as cmd
from app.config import get_settings
from app.core.telegram import TelegramError


@pytest.fixture
def bot(monkeypatch):
    """Настроенный бот и подменённый вызов Bot API."""
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_token", "123:test-token")
    monkeypatch.setattr(settings, "telegram_bot_username", "hona_order_bot")

    calls: list[tuple[str, dict]] = []
    answers = {
        "getMe": {"result": {"username": "hona_order_bot", "first_name": "HONA ORDER"}},
        "setWebhook": {"result": True},
        "getWebhookInfo": {"result": {"url": "", "pending_update_count": 0}},
    }

    def fake_call(method: str, payload: dict):
        calls.append((method, payload))
        if method == "setWebhook":
            # После установки Telegram отдаёт тот же адрес.
            answers["getWebhookInfo"]["result"]["url"] = payload["url"]
        return answers[method]

    monkeypatch.setattr(cmd, "call", fake_call)
    return calls, answers


def test_empty_token_says_where_to_get_it(monkeypatch, capsys):
    monkeypatch.setattr(get_settings(), "telegram_bot_token", "")
    assert cmd.main([]) == 1
    out = capsys.readouterr().out
    assert "BotFather" in out and "TELEGRAM_BOT_TOKEN" in out


def test_wrong_token_explains_the_404(bot, monkeypatch, capsys):
    def explode(method: str, payload: dict):
        raise TelegramError("Telegram отказал (404): Not Found")

    monkeypatch.setattr(cmd, "call", explode)
    assert cmd.main([]) == 1
    out = capsys.readouterr().out
    assert "не знает такой токен" in out
    assert "/mybots" in out


def test_sets_the_webhook_and_reports(bot, capsys):
    calls, _ = bot
    assert cmd.main([]) == 0

    methods = [method for method, _ in calls]
    assert methods == ["getMe", "setWebhook", "getWebhookInfo"]
    url = calls[1][1]["url"]
    assert url.startswith("https://order.it-hona.tj/api/telegram/webhook/")

    out = capsys.readouterr().out
    assert "@hona_order_bot" in out
    assert "ГОТОВО" in out
    # Секрет в вывод не попадает целиком.
    assert url.rsplit("/", 1)[1] not in out


def test_check_does_not_change_anything(bot, capsys):
    calls, answers = bot
    answers["getWebhookInfo"]["result"]["url"] = "https://order.it-hona.tj/api/telegram/webhook/x"
    assert cmd.main(["--check"]) == 0
    assert "setWebhook" not in [method for method, _ in calls]


def test_check_complains_when_webhook_is_absent(bot, capsys):
    assert cmd.main(["--check"]) == 1
    assert "Вебхук не установлен" in capsys.readouterr().out


def test_username_mismatch_is_flagged(bot, monkeypatch, capsys):
    """Имя из .env идёт в ссылку привязки — расхождение уводит людей не туда."""
    monkeypatch.setattr(get_settings(), "telegram_bot_username", "другой_бот")
    assert cmd.main([]) == 0
    assert "ВНИМАНИЕ" in capsys.readouterr().out


def test_delivery_error_is_shown(bot, capsys):
    _, answers = bot
    answers["getWebhookInfo"]["result"]["last_error_message"] = "SSL error"
    cmd.main([])
    assert "SSL error" in capsys.readouterr().out

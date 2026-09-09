"""Помощник по заявке: уточняющие вопросы и готовые позиции."""

from __future__ import annotations

import pytest


@pytest.fixture
def as_employee(client, employee, login):
    login(employee)
    return client

READY = {
    "status": "ready",
    "message": "Заявка готова.",
    "questions": [],
    "lines": [
        {
            "title": "Кабель UTP Cat6 Outdoor",
            "quantity": 2,
            "unit": "бухта",
            "purpose": "подключение наружных IP-камер, всего 610 м",
        }
    ],
    "warnings": [],
    "recommendations": ["Проверить, что жилы медные, а не CCA"],
}

ASK = {
    "status": "need_clarification",
    "message": "Уточните тип кабеля.",
    "questions": [
        {
            "field": "cable_type",
            "question": "Какой кабель нужен?",
            "options": ["UTP Cat5e", "UTP Cat6", "FTP Cat6", "Оптический"],
        }
    ],
    "lines": [],
    "warnings": [],
    "recommendations": [],
}


def ask(client, text: str, **body) -> dict:
    response = client.post("/api/assistant/request", json={"text": text, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_assistant_asks_when_data_is_missing(as_employee, assistant_box) -> None:
    assistant_box.answer = ASK
    body = ask(as_employee, "нужен кабель")
    assert body["available"] is True
    assert body["status"] == "need_clarification"
    assert body["questions"][0]["options"][:2] == ["UTP Cat5e", "UTP Cat6"]
    assert body["lines"] == []


def test_assistant_returns_lines_when_ready(as_employee, assistant_box) -> None:
    assistant_box.answer = READY
    body = ask(as_employee, "кабель utp cat6 outdoor 2 бухты по 305 м на камеры, Регар")
    assert body["status"] == "ready"
    line = body["lines"][0]
    assert line == {
        "title": "Кабель UTP Cat6 Outdoor",
        "quantity": 2,
        "unit": "бухта",
        "purpose": "подключение наружных IP-камер, всего 610 м",
    }
    assert body["recommendations"] == ["Проверить, что жилы медные, а не CCA"]


def test_context_and_history_go_to_the_model(as_employee, employee, assistant_box) -> None:
    """Объект и уже введённые позиции помощник видит и переспрашивать их
    не должен; предыдущие реплики уходят в диалог."""
    assistant_box.answer = READY
    ask(
        as_employee,
        "UTP Cat6, 200 м",
        history=[
            {"role": "user", "text": "нужен кабель"},
            {"role": "assistant", "text": "Какой кабель нужен?"},
        ],
        context={
            "project_name": "Регар",
            "lines": [{"title": "Гофра 16 мм", "quantity": 50, "unit": "м"}],
        },
    )
    prompt = assistant_box.prompts[-1]
    assert "Регар" in prompt
    assert "Гофра 16 мм" in prompt
    # Имя берётся из сессии, а не из тела запроса.
    assert employee.full_name in prompt
    assert assistant_box.histories[-1] == [
        ("user", "нужен кабель"),
        ("assistant", "Какой кабель нужен?"),
    ]


def test_client_cannot_forge_employee_name(as_employee, employee, assistant_box) -> None:
    assistant_box.answer = READY
    ask(as_employee, "кабель", context={"employee_name": "Кто-то другой"})
    prompt = assistant_box.prompts[-1]
    assert employee.full_name in prompt
    assert "Кто-то другой" not in prompt


def test_catalog_is_offered_to_the_model(as_employee, employee, project, assistant_box) -> None:
    """Помощник знает, как материалы называют в компании."""
    as_employee.post(
        "/api/requests",
        json={
            "employee_id": employee.id,
            "project_id": project.id,
            "lines": [{"title": "Гофра гибкая 16 мм", "quantity": 1, "unit": "м"}],
            "submit": False,
        },
    )
    assistant_box.answer = READY
    ask(as_employee, "гофра")
    assert "Гофра гибкая 16 мм" in assistant_box.prompts[-1]


def test_model_failure_is_not_an_error(as_employee, assistant_box) -> None:
    """Модель молчит — форма работает как раньше, а не падает."""
    body = ask(as_employee, "нужен кабель")
    assert body["available"] is False
    assert body["lines"] == []


def test_assistant_is_off_without_key(as_employee) -> None:
    from app.core import assistant

    assistant.set_transport(None)
    body = ask(as_employee, "нужен кабель")
    assert body["available"] is False


def test_empty_question_without_lines_is_answered_locally(as_employee, assistant_box) -> None:
    """Пустой вопрос при пустой форме модели не отправляем."""
    assistant_box.answer = READY
    body = ask(as_employee, "  ")
    assert assistant_box.prompts == []
    assert body["available"] is True and body["status"] == "need_clarification"


def test_check_request_without_text_uses_form_lines(as_employee, assistant_box) -> None:
    """«Проверить заявку»: текста нет, но есть позиции — вопрос уходит."""
    assistant_box.answer = READY
    ask(as_employee, "", context={"lines": [{"title": "Кабель", "quantity": 1, "unit": "м"}]})
    assert "проверить заявку" in assistant_box.prompts[-1]


def test_questions_and_notes_are_trimmed(as_employee, assistant_box) -> None:
    """Помощник не заваливает вопросами: больше трёх не показываем."""
    assistant_box.answer = {
        **ASK,
        "questions": [
            {"field": f"f{i}", "question": f"Вопрос {i}?", "options": []} for i in range(6)
        ],
        "warnings": [f"Замечание {i}" for i in range(5)],
    }
    body = ask(as_employee, "нужен кабель")
    assert len(body["questions"]) == 3
    assert len(body["warnings"]) == 3


def test_assistant_requires_login(client) -> None:
    assert client.post("/api/assistant/request", json={"text": "кабель"}).status_code == 401


def test_prompt_file_overrides_builtin(tmp_path, monkeypatch) -> None:
    """Правила помощника меняются файлом на сервере, без пересборки."""
    from app.config import get_settings
    from app.services import assistant_prompt

    custom = tmp_path / "prompt.txt"
    custom.write_text("Правила помощника из файла", encoding="utf-8")
    monkeypatch.setenv("ASSISTANT_PROMPT_FILE", str(custom))
    get_settings.cache_clear()
    assistant_prompt.request_assistant_prompt.cache_clear()
    try:
        assert assistant_prompt.request_assistant_prompt() == "Правила помощника из файла"
    finally:
        monkeypatch.delenv("ASSISTANT_PROMPT_FILE", raising=False)
        get_settings.cache_clear()
        assistant_prompt.request_assistant_prompt.cache_clear()


def test_unreadable_prompt_file_falls_back(tmp_path, monkeypatch) -> None:
    from app.config import get_settings
    from app.services import assistant_prompt

    monkeypatch.setenv("ASSISTANT_PROMPT_FILE", str(tmp_path / "нет-такого-файла.txt"))
    get_settings.cache_clear()
    assistant_prompt.request_assistant_prompt.cache_clear()
    try:
        assert "IT-HONA" in assistant_prompt.request_assistant_prompt()
    finally:
        monkeypatch.delenv("ASSISTANT_PROMPT_FILE", raising=False)
        get_settings.cache_clear()
        assistant_prompt.request_assistant_prompt.cache_clear()


# --- Диагностика (python -m app.assistant_check) ------------------------------


def test_check_reports_disabled_assistant(capsys, monkeypatch) -> None:
    from app.config import get_settings
    from app import assistant_check
    from app.core import assistant

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    assistant.set_transport(None)
    try:
        assert assistant_check.main() == 1
    finally:
        get_settings.cache_clear()
    assert "не задан ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_check_explains_empty_balance(capsys, assistant_box) -> None:
    """Ответ Anthropic виден целиком, а не «что-то пошло не так»."""
    from app import assistant_check
    from app.core import assistant

    class Broken:
        def ask(self, *, system, prompt, schema, history=None, effort="low"):
            raise assistant.AssistantError(
                "Claude API ответил 400: Your credit balance is too low"
            )

    assistant.set_transport(Broken())
    assert assistant_check.main() == 1
    out = capsys.readouterr().out
    assert "credit balance is too low" in out
    assert "Billing" in out


def test_check_passes_when_model_answers(capsys, assistant_box) -> None:
    from app import assistant_check

    assistant_box.answer = {"ok": True, "word": "работает"}
    assert assistant_check.main() == 0
    assert "Помощник работает" in capsys.readouterr().out

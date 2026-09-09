"""Push-уведомления на телефон: подписка устройства и сообщения о заявке."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core import push
from app.db.models import AuditLog, PushSubscription
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import requests as svc
from app.services.push_notify import notify_employee, notify_request_state


def _sub(endpoint: str = "https://push.example/abc", agent: str = "iPhone Safari"):
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "BPUBLICKEY", "auth": "AUTHSECRET"},
        "user_agent": agent,
    }


def _make_request(session, employee, project, *, submit=True):
    return svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=project.id,
            lines=[ExpenseLineIn(title="Гипсокартон", quantity=Decimal("10"), unit="лист")],
            submit=submit,
        ),
    )


# --- Подписка -----------------------------------------------------------------


def test_config_when_disabled(client, login, employee):
    login(employee)
    data = client.get("/api/push/config").json()
    assert data == {"enabled": False, "public_key": None, "devices": 0}
    # Подписаться при выключенном push нельзя — панель не должна молча
    # копить подписки, по которым никогда ничего не придёт.
    assert client.post("/api/push/subscribe", json=_sub()).status_code == 422


def test_subscribe_and_unsubscribe(client, session, login, employee, push_box):
    login(employee)
    data = client.get("/api/push/config").json()
    assert data["enabled"] is True
    # Открытый ключ P-256 без сжатия: 65 байт → 87 символов base64url.
    assert len(data["public_key"]) == 87
    assert data["devices"] == 0

    created = client.post("/api/push/subscribe", json=_sub())
    assert created.status_code == 201, created.text
    assert created.json()["devices"] == 1

    # Повторная подписка того же браузера не плодит строк.
    again = client.post("/api/push/subscribe", json=_sub())
    assert again.json()["devices"] == 1

    removed = client.post("/api/push/unsubscribe", json={"endpoint": _sub()["endpoint"]})
    assert removed.json()["devices"] == 0

    actions = session.scalars(
        AuditLog.__table__.select().with_only_columns(AuditLog.action)
    ).all()
    assert "push_subscribed" in actions and "push_unsubscribed" in actions


def test_endpoint_moves_to_new_owner(client, session, login, employee, manager, push_box):
    """Один браузер — один человек: чужие заявки на чужой телефон не идут."""
    login(employee)
    client.post("/api/push/subscribe", json=_sub())
    login(manager)
    client.post("/api/push/subscribe", json=_sub())

    session.expire_all()
    rows = session.scalars(PushSubscription.__table__.select()).all()
    assert len(rows) == 1
    owner = session.scalar(
        PushSubscription.__table__.select().with_only_columns(PushSubscription.employee_id)
    )
    assert owner == manager.id


def test_cannot_unsubscribe_someone_elses_device(client, session, login, employee, manager, push_box):
    login(employee)
    client.post("/api/push/subscribe", json=_sub())
    login(manager)
    assert client.post("/api/push/unsubscribe", json={"endpoint": _sub()["endpoint"]}).json()[
        "devices"
    ] == 0
    login(employee)
    assert client.get("/api/push/config").json()["devices"] == 1


def test_test_notification(client, login, employee, push_box):
    login(employee)
    assert client.post("/api/push/test").status_code == 422  # устройств нет
    client.post("/api/push/subscribe", json=_sub())
    assert client.post("/api/push/test").status_code == 204
    assert push_box[-1].title == "HONA ORDER"
    assert push_box[-1].subscription["endpoint"] == _sub()["endpoint"]


# --- Уведомления о заявке -----------------------------------------------------


def test_request_state_goes_to_author_and_manager(
    client, session, login, employee, manager, project, push_box
):
    login(manager)
    client.post("/api/push/subscribe", json=_sub("https://push.example/manager"))
    login(employee)
    client.post("/api/push/subscribe", json=_sub("https://push.example/author"))
    push_box.clear()

    request = _make_request(session, employee, project)
    session.flush()
    notify_request_state(session, request.id)

    by_endpoint = {n.subscription["endpoint"]: n for n in push_box}
    author = by_endpoint["https://push.example/author"]
    assert author.title == "Ваша заявка"
    assert "согласование покупки" in author.body
    assert request.number in author.body

    boss = by_endpoint["https://push.example/manager"]
    assert boss.title == f"Заявка {request.number}"
    assert employee.full_name in boss.body
    assert boss.url.endswith("/approvals")
    # Суммы ещё нет — и в уведомлении её нет.
    assert "сомони" not in boss.body


def test_author_is_not_invited_to_own_request(session, manager, project, push_box):
    """Руководитель подал сам — звать его согласовывать себя незачем."""
    sub = PushSubscription(
        employee_id=manager.id, endpoint="https://push.example/m", p256dh="k", auth="a"
    )
    session.add(sub)
    session.flush()
    request = _make_request(session, manager, project)
    notify_request_state(session, request.id)
    titles = [n.title for n in push_box]
    assert titles == ["Ваша заявка"]


def test_dead_subscription_is_removed(session, employee, push_box):
    """Push-служба ответила «подписки нет» — строку удаляем сами."""
    session.add(
        PushSubscription(
            employee_id=employee.id, endpoint="https://push.example/dead", p256dh="k", auth="a"
        )
    )
    session.add(
        PushSubscription(
            employee_id=employee.id, endpoint="https://push.example/alive", p256dh="k", auth="a"
        )
    )
    session.flush()

    class HalfDead:
        def send(self, notification: push.Notification) -> None:
            if notification.subscription["endpoint"].endswith("/dead"):
                raise push.PushGone("410")

    push.set_transport(HalfDead())
    sent = notify_employee(session, employee, title="t", body="b", url="/")
    assert sent == 1
    left = session.scalars(
        PushSubscription.__table__.select().with_only_columns(PushSubscription.endpoint)
    ).all()
    assert left == ["https://push.example/alive"]


def test_public_key_derivation_is_stable():
    key = push.generate_private_key()
    assert len(key) == 43
    from app.config import get_settings

    settings = get_settings()
    saved = settings.vapid_private_key
    try:
        settings.vapid_private_key = key
        first = push.public_key()
        assert first == push.public_key()
        assert len(first) == 87
        settings.vapid_private_key = "мусор"
        with pytest.raises(push.PushError):
            push.public_key()
    finally:
        settings.vapid_private_key = saved

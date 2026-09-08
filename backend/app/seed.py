"""Загрузка демонстрационных данных.

Запуск:  python -m app.seed
Нужен, чтобы панель не была пустой при первом знакомстве. В рабочей базе
не запускать: данные условные, взяты из дизайн-макета.

Скрипт идемпотентен по справочникам (объекты и сотрудники не дублируются),
но заявки добавляет при каждом запуске — запускайте один раз.
"""

from __future__ import annotations

import logging
import sys
from decimal import Decimal

from sqlalchemy import func, select

from app.config import get_settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.core.time import utcnow
from app.db.models import (
    Employee,
    EmployeeRole,
    ExpenseRequest,
    MonthlyBudget,
    PaymentMethod,
    Project,
)
from app.db.session import get_session_factory
from app.schemas.request import (
    DecisionIn,
    ExpenseLineIn,
    PaymentIn,
    RequestCreate,
    SourcingIn,
    SourcingLineIn,
)
from app.services import requests as svc
from app.services.reports import current_period

log = logging.getLogger("seed")

PROJECTS = ["Вилла Колхозная", "Рекова 132", "Офис на 7 этаже", "Речь"]

#: Пароль демонстрационных учётных записей. Только для показа: в рабочей
#: базе seed не запускают, а пароли назначает администратор.
DEMO_PASSWORD = "hona-demo-2026"

def demo_domain() -> str:
    """Домен для демо-адресов.

    Берём из настроек, а не пишем в коде: с чужим доменом вход по этим
    адресам не сработал бы и весь демо-набор оказался бы бесполезен.
    """
    domains = get_settings().email_domains
    return domains[0] if domains else "example.com"


#: (ФИО, должность, локальная часть почты, роль, лимит)
EMPLOYEES: list[tuple[str, str, str, EmployeeRole, str | None]] = [
    ("Иван Петров", "Мастер-отделочник", "i.petrov", EmployeeRole.EMPLOYEE, "5000.00"),
    ("Мария Сидорова", "Дизайнер", "m.sidorova", EmployeeRole.EMPLOYEE, "4000.00"),
    ("Сергей Никитин", "Прораб", "s.nikitin", EmployeeRole.EMPLOYEE, "8000.00"),
    ("Екатерина Волкова", "Менеджер проекта", "e.volkova", EmployeeRole.EMPLOYEE, "6000.00"),
    ("Алексей Морозов", "Электрик", "a.morozov", EmployeeRole.EMPLOYEE, "3000.00"),
    ("Ольга Кузнецова", "Снабженец", "o.kuznetsova", EmployeeRole.PROCUREMENT, "10000.00"),
    ("Дмитрий Соколов", "Инженер", "d.sokolov", EmployeeRole.EMPLOYEE, "4000.00"),
    ("Анна Лебедева", "Архитектор", "a.lebedeva", EmployeeRole.EMPLOYEE, "5000.00"),
    ("Артём Ковалёв", "Руководитель отдела", "a.kovalev", EmployeeRole.MANAGER, None),
    ("Нигина Рахимова", "Бухгалтер", "n.rahimova", EmployeeRole.FINANCE, None),
    ("Администратор", "Администратор системы", "admin", EmployeeRole.ADMIN, None),
]

#: Демо-сценарий по нынешнему пути заявки.
#:  (сотрудник, объект, строки «что нужно», этап, документ выплаты)
#: Этап: None — ждёт согласования покупки; "sourcing" — ушла в закуп;
#: "priced" — закуп оценил, ждёт решения по сумме; "approved" — сумма
#: утверждена; "stock" — всё нашлось на складе; "reject" — отклонена.
#: Цены закупа заданы отдельно, в SOURCING_PRICES.
SCENARIO: list[tuple[str, str, list[tuple[str, int, str]], str | None, str | None]] = [
    (
        "Иван Петров", "Вилла Колхозная",
        [
            ("Грунтовка глубокого проникновения", 2, "канистра"),
            ("Шпатель 45 см", 1, "шт."),
            ("Мешки для мусора", 5, "упаковка"),
        ],
        None, None,
    ),
    ("Мария Сидорова", "Офис на 7 этаже", [("Печать макетов А1", 6, "лист")], None, None),
    ("Сергей Никитин", "Рекова 132", [("Крепёж и расходники", 4, "коробка")], "sourcing", None),
    (
        "Екатерина Волкова", "Речь",
        [("Аренда прожекторов", 1, "комплект"), ("Удлинитель 20 м", 2, "шт.")],
        "priced", None,
    ),
    ("Алексей Морозов", "Рекова 132", [("Кабель ВВГ 3×2,5", 2, "бухта")], "approved", None),
    ("Ольга Кузнецова", "Вилла Колхозная", [("Партия плитки", 1, "паллета")], "reject", None),
    ("Дмитрий Соколов", "Офис на 7 этаже", [("Стремянка 5 ступеней", 1, "шт.")], "stock", None),
    ("Анна Лебедева", "Речь", [("Печать чертежей", 12, "лист")], "priced", None),
    ("Иван Петров", "Вилла Колхозная", [("Перчатки рабочие", 10, "пара")], "stock", None),
    (
        "Сергей Никитин", "Рекова 132",
        [("Перфоратор в аренду", 1, "шт."), ("Буры", 3, "шт.")],
        "paid", "ПП-0409",
    ),
]

#: Что закуп отвечает по каждой строке демо-заявок: цена или «есть на
#: складе». Ключ — название строки.
SOURCING_PRICES: dict[str, str | None] = {
    "Крепёж и расходники": "600.00",
    "Аренда прожекторов": "2400.00",
    "Удлинитель 20 м": "350.00",
    "Кабель ВВГ 3×2,5": "620.00",
    "Партия плитки": "5600.00",
    "Стремянка 5 ступеней": None,
    "Печать чертежей": "170.00",
    "Перчатки рабочие": None,
    "Перфоратор в аренду": "1200.00",
    "Буры": "95.00",
}


def seed() -> None:
    setup_logging("INFO")
    session = get_session_factory()()
    try:
        existing = session.scalar(select(func.count()).select_from(ExpenseRequest)) or 0
        if existing:
            log.warning(
                "В базе уже %s заявок. Демо-данные не добавлены, чтобы не задвоить их.",
                existing,
            )
            return

        projects: dict[str, Project] = {}
        for name in PROJECTS:
            project = session.scalar(select(Project).where(Project.name == name))
            if project is None:
                project = Project(name=name)
                session.add(project)
                session.flush()
            projects[name] = project

        domain = demo_domain()
        employees: dict[str, Employee] = {}
        for full_name, position, mailbox, role, limit in EMPLOYEES:
            email = f"{mailbox}@{domain}"
            person = session.scalar(select(Employee).where(Employee.email == email))
            if person is None:
                person = Employee(
                    full_name=full_name,
                    position=position,
                    email=email,
                    role=role,
                    monthly_limit=Decimal(limit) if limit else None,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
                session.add(person)
                session.flush()
            employees[full_name] = person

        year, month = current_period()
        if not session.scalar(
            select(MonthlyBudget).where(
                MonthlyBudget.year == year, MonthlyBudget.month == month
            )
        ):
            session.add(
                MonthlyBudget(year=year, month=month, amount=Decimal("156000.00"))
            )

        manager = employees["Артём Ковалёв"].full_name
        buyer = employees["Ольга Кузнецова"].full_name
        for who, where, lines, stage, document in SCENARIO:
            request = svc.create_request(
                session,
                RequestCreate(
                    employee_id=employees[who].id,
                    project_id=projects[where].id,
                    lines=[
                        ExpenseLineIn(title=title, quantity=qty, unit=unit)
                        for title, qty, unit in lines
                    ],
                    submit=True,
                ),
            )
            if stage == "reject":
                svc.decide_request(
                    session,
                    request.id,
                    DecisionIn(
                        approve=False,
                        comment=(
                            "Закупка не согласована с прорабом. Оформите заявку "
                            "заново после уточнения объёмов."
                        ),
                        actor=manager,
                    ),
                )
            elif stage is not None:
                # Потребность согласована — заявка уходит в закуп.
                svc.decide_request(
                    session, request.id, DecisionIn(approve=True, actor=manager)
                )

            if stage in ("priced", "approved", "paid", "stock"):
                svc.apply_sourcing(
                    session,
                    request.id,
                    SourcingIn(
                        lines=[
                            SourcingLineIn(
                                id=line.id,
                                from_stock=SOURCING_PRICES.get(line.title) is None,
                                price=SOURCING_PRICES.get(line.title),
                            )
                            for line in request.lines
                        ],
                        comment=None,
                    ),
                    actor=buyer,
                )

            if stage in ("approved", "paid"):
                svc.decide_request(
                    session, request.id, DecisionIn(approve=True, actor=manager)
                )

            if document:
                svc.pay_request(
                    session,
                    request.id,
                    PaymentIn(
                        method=(
                            PaymentMethod.CARD
                            if document.startswith("ПП")
                            else PaymentMethod.CASH
                        ),
                        document=document,
                        # Выплата проходит после решения, иначе срок
                        # «от одобрения до выплаты» получается отрицательным.
                        paid_at=utcnow(),
                        actor="ФИНАНСЫ",
                    ),
                )

        session.commit()
        log.info(
            "Демо-данные загружены: %s объектов, %s сотрудников, %s заявок",
            len(projects),
            len(employees),
            len(SCENARIO),
        )
        log.warning(
            "Вход в демо-режиме: admin@%s (администратор), a.kovalev@%s "
            "(руководитель), n.rahimova@%s (финансы), пароль у всех «%s». "
            "Только для показа.",
            domain,
            domain,
            domain,
            DEMO_PASSWORD,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    try:
        seed()
    except Exception as exc:  # noqa: BLE001
        log.error("Загрузка демо-данных не удалась: %s", exc)
        sys.exit(1)

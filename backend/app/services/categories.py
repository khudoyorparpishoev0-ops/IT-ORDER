"""Категории расхода: какая форма, какие поля и какой маршрут.

Одна заявка на всю систему — но заполняют её по-разному. «Обед · 1 шт.»
и «Кабель UTP Cat6 · 2 бухты» это не одна форма: в первом случае человек
думает про людей и дни, во втором про метры и штуки. Здесь описано, что
показывать и что требовать для каждого вида расхода.

Почему в коде, а не в таблице базы. Эти флаги решают, нужен ли отдел
закупа и можно ли платить без второго согласования, — то есть
распоряжаются деньгами. Строка в таблице, которую можно переключить
мимо ревью, снимает закуп со всех материалов одним нажатием. Здесь они
лежат рядом с проверками, которые на них опираются, и меняются тем же
путём, что и остальные правила: правкой, ревью и выкаткой.

Сумму по этим полям считает сервер (`amount_of`), а не панель: деньги
считаются в одном месте и на `Decimal`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.core.money import to_decimal
from app.db.models import RequestCategory

#: Вид формы. Определяет и набор полей, и то, как считается сумма.
FormType = str

LINES = "lines"
"""Смета строками: наименование, количество, единица. Цены ставит закуп."""

PEOPLE_DAYS = "people_days"
"""Люди × дни × ставка: питание."""

NIGHTS = "nights"
"""Ночи × ставка × комнаты: проживание."""

TRIP = "trip"
"""Командировка: маршрут, даты и несколько статей расходов."""

ROUTE = "route"
"""Откуда, куда, что везём: доставка, курьер, такси."""

CARGO = "cargo"
"""Международная перевозка: вес, объём, карго, таможня."""

VEHICLE = "vehicle"
"""Автомобиль: вид расхода, литры, сумма."""

SERVICE = "service"
"""Услуга: название, описание, подрядчик, сумма."""

SUBSCRIPTION = "subscription"
"""Хостинг, домен, интернет, связь: сервис, период, сумма."""

FREEFORM = "freeform"
"""Прочее: описание, обоснование, сумма."""


@dataclass(frozen=True)
class Field_:
    """Одно поле формы. Панель рисует по этому описанию, сервер по нему же
    проверяет: набор полей у формы и у проверки обязан быть один."""

    #: Ключ в `expense_requests.details`.
    key: str
    label: str
    #: text · number · money · date · select · people (список сотрудников)
    kind: str
    required: bool = False
    #: Варианты для `select`.
    options: tuple[str, ...] = ()
    #: Подсказка под полем.
    note: str | None = None
    #: Единица рядом с числом: «чел.», «дн.», «кг», «л».
    suffix: str | None = None


@dataclass(frozen=True)
class CategorySpec:
    """Что за расход, как его описывают и куда он идёт дальше."""

    code: RequestCategory
    name: str
    form_type: FormType
    #: Нужен ли отдел закупа. false — руководитель одобряет, и заявка
    #: уходит сразу в бухгалтерию.
    requires_procurement: bool
    #: Нужно ли отдельное согласование суммы после оценки закупа.
    requires_amount_approval: bool
    #: Может ли автор сразу назвать сумму.
    allows_initial_amount: bool
    #: Нужна ли единица измерения у позиции.
    requires_unit: bool
    #: Нужно ли количество у позиции.
    requires_quantity: bool
    #: Поля формы сверх объекта и категории.
    fields: tuple[Field_, ...] = ()
    #: Показывать ли категорию в форме. Выключенная остаётся в старых
    #: заявках и в отчётах — данные не переписываются.
    active: bool = True

    @property
    def workflow_type(self) -> str:
        """«Как заявка идёт»: через закуп или напрямую в бухгалтерию."""
        return "procurement" if self.requires_procurement else "direct"


def _f(key: str, label: str, kind: str, **kw) -> Field_:
    return Field_(key=key, label=label, kind=kind, **kw)


#: Что за расход, чем его описывают и куда он идёт дальше.
#:
#: Порядок здесь — порядок в выпадающем списке: сверху то, что подают
#: чаще всего.
SPECS: dict[RequestCategory, CategorySpec] = {
    RequestCategory.MATERIALS: CategorySpec(
        code=RequestCategory.MATERIALS,
        name="Материалы",
        form_type=LINES,
        requires_procurement=True,
        requires_amount_approval=True,
        allows_initial_amount=False,
        requires_unit=True,
        requires_quantity=True,
    ),
    RequestCategory.EQUIPMENT: CategorySpec(
        code=RequestCategory.EQUIPMENT,
        name="Оборудование",
        form_type=LINES,
        requires_procurement=True,
        requires_amount_approval=True,
        allows_initial_amount=False,
        requires_unit=True,
        requires_quantity=True,
    ),
    RequestCategory.HOUSEHOLD: CategorySpec(
        code=RequestCategory.HOUSEHOLD,
        name="Хозяйственные расходы",
        form_type=LINES,
        requires_procurement=True,
        requires_amount_approval=True,
        allows_initial_amount=False,
        requires_unit=True,
        requires_quantity=True,
    ),
    RequestCategory.MEALS: CategorySpec(
        code=RequestCategory.MEALS,
        name="Питание",
        form_type=PEOPLE_DAYS,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f(
                "meal_type",
                "Тип питания",
                "select",
                required=True,
                options=("Завтрак", "Обед", "Ужин", "Обед и ужин", "Другое"),
            ),
            _f("people", "Человек", "number", required=True, suffix="чел."),
            _f("days", "Дней", "number", required=True, suffix="дн."),
            _f(
                "rate",
                "Стоимость на человека в день",
                "money",
                note="Если известна. Итог считается сам: человек × дней × ставка.",
            ),
        ),
    ),
    RequestCategory.TRIP: CategorySpec(
        code=RequestCategory.TRIP,
        name="Командировка",
        form_type=TRIP,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f("staff", "Кто едет", "text", required=True, note="Через запятую."),
            _f("destination", "Куда", "text", required=True),
            _f("purpose", "Цель поездки", "text", required=True),
            _f("date_from", "Выезд", "date", required=True),
            _f("date_to", "Возвращение", "date", required=True),
            _f("transport", "Транспорт", "money"),
            _f("lodging", "Проживание", "money"),
            _f("per_diem", "Суточные", "money"),
            _f("other", "Прочие расходы", "money"),
        ),
    ),
    RequestCategory.DELIVERY: CategorySpec(
        code=RequestCategory.DELIVERY,
        name="Доставка, курьер, такси",
        form_type=ROUTE,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f("from_place", "Откуда", "text", required=True),
            _f("to_place", "Куда", "text", required=True),
            _f("what", "Что или кого везём", "text", required=True),
            _f("trips", "Поездок", "number", suffix="шт."),
            _f("carrier", "Перевозчик", "text"),
            _f("amount", "Сумма", "money"),
        ),
    ),
    RequestCategory.TRANSPORT: CategorySpec(
        code=RequestCategory.TRANSPORT,
        name="Транспорт, поездки",
        form_type=ROUTE,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f("from_place", "Откуда", "text", required=True),
            _f("to_place", "Куда", "text", required=True),
            _f("what", "Что или кого везём", "text", required=True),
            _f("trips", "Поездок", "number", suffix="шт."),
            _f("carrier", "Перевозчик", "text"),
            _f("amount", "Сумма", "money"),
        ),
    ),
    RequestCategory.CARGO: CategorySpec(
        code=RequestCategory.CARGO,
        name="Карго",
        form_type=CARGO,
        requires_procurement=True,
        requires_amount_approval=True,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f("from_country", "Страна отправления", "text", required=True),
            _f("from_city", "Город отправления", "text"),
            _f("to_city", "Город назначения", "text", required=True),
            _f("what", "Что за груз", "text", required=True),
            _f("places", "Мест", "number", suffix="шт."),
            _f("weight_kg", "Вес", "number", suffix="кг"),
            _f("volume_m3", "Объём", "number", suffix="м³"),
            _f("cargo_cost", "Стоимость карго", "money"),
            _f("customs", "Таможня", "money"),
            _f("extra", "Дополнительные расходы", "money"),
        ),
    ),
    RequestCategory.FUEL: CategorySpec(
        code=RequestCategory.FUEL,
        name="Заправка, обслуживание машины",
        form_type=VEHICLE,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f("vehicle", "Автомобиль", "text", required=True),
            _f("plate", "Госномер", "text"),
            _f(
                "kind",
                "Вид расхода",
                "select",
                required=True,
                options=("Бензин", "Газ", "Дизель", "Масло", "Ремонт", "Другое"),
            ),
            _f("liters", "Литров", "number", suffix="л"),
            _f("amount", "Сумма", "money", required=True),
            _f("route", "Объект или маршрут", "text"),
        ),
    ),
    RequestCategory.SERVICES: CategorySpec(
        code=RequestCategory.SERVICES,
        name="Услуги",
        form_type=SERVICE,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f("service", "Название услуги", "text", required=True),
            _f("description", "Что нужно сделать", "textarea", required=True),
            _f("contractor", "Подрядчик", "text"),
            _f("period", "Период или объём", "text"),
            _f(
                "amount",
                "Сумма",
                "money",
                note="Не знаете — оставьте пустой: цену назовёт отдел закупа.",
            ),
        ),
    ),
    RequestCategory.LODGING: CategorySpec(
        code=RequestCategory.LODGING,
        name="Проживание",
        form_type=NIGHTS,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f("staff", "Кто живёт", "text", required=True, note="Через запятую."),
            _f("city", "Город", "text", required=True),
            _f("hotel", "Гостиница", "text"),
            _f("check_in", "Заезд", "date", required=True),
            _f("check_out", "Выезд", "date", required=True),
            _f("rooms", "Комнат", "number", suffix="шт."),
            _f("nightly_rate", "Цена за ночь", "money"),
        ),
    ),
    RequestCategory.CONNECTIVITY: CategorySpec(
        code=RequestCategory.CONNECTIVITY,
        name="Интернет, хостинг, связь",
        form_type=SUBSCRIPTION,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f(
                "service_kind",
                "Тип услуги",
                "select",
                required=True,
                options=("Хостинг", "Домен", "Интернет", "Телефония", "Starlink", "Другое"),
            ),
            _f("account", "Домен, аккаунт или сервис", "text", required=True),
            _f("period", "Период", "text", note="«1 год», «месяц», «до 01.03.2027»."),
            _f("amount", "Сумма", "money", required=True),
            _f("due_date", "Оплатить до", "date"),
        ),
    ),
    RequestCategory.OTHER: CategorySpec(
        code=RequestCategory.OTHER,
        name="Прочие расходы",
        form_type=FREEFORM,
        requires_procurement=False,
        requires_amount_approval=False,
        allows_initial_amount=True,
        requires_unit=False,
        requires_quantity=False,
        fields=(
            _f("description", "Что нужно", "text", required=True),
            _f("reason", "Обоснование", "textarea", required=True),
            _f("amount", "Сумма", "money"),
        ),
    ),
}


def spec_of(category: RequestCategory | None) -> CategorySpec | None:
    """Описание категории. None — категория не указана: так подавали до
    появления категорийных форм, и такие заявки идут прежним путём."""
    return SPECS.get(category) if category is not None else None


def is_lines_form(category: RequestCategory | None) -> bool:
    """Смета строками. Без категории — тоже она: так работало всегда."""
    spec = spec_of(category)
    return spec is None or spec.form_type == LINES


# --- Проверка и расчёт ---------------------------------------------------
#
# Обе задачи здесь, а не в панели: панель рисует форму по тем же полям,
# но верить ей нельзя. Прямой запрос к API с пустым обязательным полем
# или с суммой из воздуха должен быть отклонён так же, как в форме.


def _text(details: dict, key: str) -> str:
    value = details.get(key)
    return str(value).strip() if value is not None else ""


def _number(details: dict, key: str) -> int:
    """Целое из подробностей. Мусор и отрицательное — ноль: считать по
    нему нельзя, а ошибку про обязательное поле поднимет проверка."""
    try:
        value = int(details.get(key) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _money(details: dict, key: str) -> Decimal:
    """Деньги из подробностей — только через `Decimal`. Пусто и мусор —
    ноль: «сумма неизвестна» и «сумма ноль» для расчёта одно и то же,
    а разницу знает `priced`."""
    raw = details.get(key)
    if raw in (None, ""):
        return Decimal("0.00")
    try:
        value = to_decimal(raw)
    except Exception:
        return Decimal("0.00")
    return value if value > 0 else Decimal("0.00")


def validate(category: RequestCategory | None, details: dict) -> list[str]:
    """Что не заполнено. Пустой список — можно подавать.

    Возвращает список, а не первую ошибку: человек должен увидеть всё
    сразу, а не открывать форму пять раз подряд.
    """
    spec = spec_of(category)
    if spec is None:
        return []

    problems: list[str] = []
    for item in spec.fields:
        if not item.required:
            continue
        if item.kind in ("number",):
            if _number(details, item.key) <= 0:
                problems.append(f"«{item.label}» — укажите число больше нуля")
        elif item.kind == "money":
            if _money(details, item.key) <= 0:
                problems.append(f"«{item.label}» — укажите сумму")
        elif not _text(details, item.key):
            problems.append(f"«{item.label}» — обязательное поле")

    if spec.form_type == TRIP:
        problems.extend(_check_dates(details, "date_from", "date_to", "Возвращение"))
    if spec.form_type == NIGHTS:
        problems.extend(_check_dates(details, "check_in", "check_out", "Выезд"))

    # Отрицательных денег не бывает: минус в смете означает возврат, а
    # возвратов в ORDER нет — значит, это опечатка.
    for item in spec.fields:
        if item.kind == "money":
            raw = details.get(item.key)
            if raw not in (None, ""):
                try:
                    if to_decimal(raw) < 0:
                        problems.append(f"«{item.label}» — сумма не может быть отрицательной")
                except Exception:
                    problems.append(f"«{item.label}» — не похоже на сумму")
    return problems


def _check_dates(details: dict, start: str, end: str, label: str) -> list[str]:
    """Конец не раньше начала. Даты приходят строками «2026-09-11»."""
    first, last = _text(details, start), _text(details, end)
    if first and last and last < first:
        return [f"«{label}» — дата раньше начала"]
    return []


def _span(details: dict, start: str, end: str) -> int:
    """Сколько дней между датами, считая обе. Нечитаемые даты — один
    день: заявку это не отменяет, а расчёт остаётся честным минимумом."""
    from datetime import date

    try:
        first = date.fromisoformat(_text(details, start))
        last = date.fromisoformat(_text(details, end))
    except ValueError:
        return 1
    return max(1, (last - first).days + 1)


def nights_of(details: dict) -> int:
    """Ночей между заездом и выездом. Заезд и выезд в один день — ночь:
    гостиница всё равно возьмёт за сутки."""
    from datetime import date

    try:
        first = date.fromisoformat(_text(details, "check_in"))
        last = date.fromisoformat(_text(details, "check_out"))
    except ValueError:
        return 1
    return max(1, (last - first).days)


def days_of(details: dict) -> int:
    """Дней командировки, считая день выезда и день возвращения."""
    return _span(details, "date_from", "date_to")


def amount_of(category: RequestCategory | None, details: dict) -> Decimal:
    """Сумма заявки по подробностям. Ноль — сумма ещё не известна.

    Считает сервер, а не панель: деньги в ORDER живут в одном месте и
    только в `Decimal`. Панель показывает тот же итог, но он у неё
    справочный — в базу идёт этот.
    """
    spec = spec_of(category)
    if spec is None or spec.form_type == LINES:
        return Decimal("0.00")

    if spec.form_type == PEOPLE_DAYS:
        return _money(details, "rate") * _number(details, "people") * _number(details, "days")
    if spec.form_type == NIGHTS:
        rooms = _number(details, "rooms") or 1
        return _money(details, "nightly_rate") * nights_of(details) * rooms
    if spec.form_type == TRIP:
        return sum(
            (_money(details, key) for key in ("transport", "lodging", "per_diem", "other")),
            Decimal("0.00"),
        )
    if spec.form_type == CARGO:
        return sum(
            (_money(details, key) for key in ("cargo_cost", "customs", "extra")),
            Decimal("0.00"),
        )
    return _money(details, "amount")


def needs_procurement(category: RequestCategory | None, amount: Decimal) -> bool:
    """Идёт ли заявка через отдел закупа.

    Через закуп идут материалы и карго — там цену называет он. И любая
    заявка, где сумму не назвали: без шага оценки она дошла бы до
    бухгалтерии с нулём, а платить по нулю нельзя. Именно так и описаны
    услуги: сумма известна — сразу в бухгалтерию, неизвестна — через
    закуп.
    """
    spec = spec_of(category)
    if spec is None:
        return True
    return spec.requires_procurement or amount <= 0


# --- Строка сметы --------------------------------------------------------


@dataclass(frozen=True)
class DerivedLine:
    """Позиция, собранная сервером из полей категории.

    У заявки любого вида остаётся хотя бы одна строка сметы. Не ради
    красоты: строки читают отчёты, аналитика, поиск, выгрузки в Excel и
    PDF, память помощника и наименование заявки — четырнадцать мест.
    Заявка без строк выпала бы из всех них разом.

    И это честно: питание на четверых два дня — это одна позиция
    «Обед и ужин, 8 чел.-дн. по 50».
    """

    title: str
    quantity: int
    unit: str | None
    price: Decimal | None
    total: Decimal | None


def _join(*parts: str) -> str:
    return ", ".join(p for p in parts if p)


def derive_line(category: RequestCategory | None, details: dict) -> DerivedLine | None:
    """Строка сметы для категорий, где человек не пишет смету руками.

    None — категория со сметой строками: там позиции вводит человек.
    """
    spec = spec_of(category)
    if spec is None or spec.form_type == LINES:
        return None

    amount = amount_of(category, details)
    total = amount if amount > 0 else None
    form = spec.form_type

    if form == PEOPLE_DAYS:
        people, days = _number(details, "people"), _number(details, "days")
        rate = _money(details, "rate")
        return DerivedLine(
            title=_text(details, "meal_type") or "Питание",
            quantity=max(1, people * days),
            unit="чел.-дн.",
            price=rate if rate > 0 else None,
            total=total,
        )

    if form == NIGHTS:
        nights = nights_of(details)
        rooms = _number(details, "rooms") or 1
        rate = _money(details, "nightly_rate")
        return DerivedLine(
            title=_join("Проживание", _text(details, "hotel"), _text(details, "city")),
            quantity=max(1, nights * rooms),
            unit="ночь",
            price=rate if rate > 0 else None,
            total=total,
        )

    if form == TRIP:
        return DerivedLine(
            title=f"Командировка: {_text(details, 'destination')}",
            quantity=days_of(details),
            unit="дн.",
            price=None,
            total=total,
        )

    if form == ROUTE:
        route = f"{_text(details, 'from_place')} → {_text(details, 'to_place')}"
        return DerivedLine(
            title=_join(_text(details, "what"), route),
            quantity=max(1, _number(details, "trips")),
            unit="поездка",
            price=None,
            total=total,
        )

    if form == CARGO:
        route = f"{_text(details, 'from_country')} → {_text(details, 'to_city')}"
        return DerivedLine(
            title=_join("Карго", _text(details, "what"), route),
            quantity=max(1, _number(details, "places")),
            unit="место",
            price=None,
            total=total,
        )

    if form == VEHICLE:
        liters = _number(details, "liters")
        return DerivedLine(
            title=_join(_text(details, "kind"), _text(details, "vehicle")),
            quantity=max(1, liters),
            unit="л" if liters else None,
            price=None,
            total=total,
        )

    if form == SERVICE:
        return DerivedLine(
            title=_text(details, "service") or "Услуга",
            quantity=1,
            unit=None,
            price=None,
            total=total,
        )

    if form == SUBSCRIPTION:
        return DerivedLine(
            title=_join(_text(details, "service_kind"), _text(details, "account")),
            quantity=1,
            unit=None,
            price=None,
            total=total,
        )

    return DerivedLine(
        title=_text(details, "description") or "Расход",
        quantity=1,
        unit=None,
        price=None,
        total=total,
    )


def summary(category: RequestCategory | None, details: dict) -> list[tuple[str, str]]:
    """Подробности словами — для карточки, PDF и уведомлений.

    Показываются только заполненные поля: пустая строка «Госномер: —»
    занимает место и ничего не сообщает.
    """
    spec = spec_of(category)
    if spec is None:
        return []

    rows: list[tuple[str, str]] = []
    for item in spec.fields:
        raw = details.get(item.key)
        if raw in (None, "", 0):
            continue
        if item.kind == "money":
            value = f"{_money(details, item.key):.2f}".replace(".", ",")
        elif item.kind == "number":
            value = f"{_number(details, item.key)}{' ' + item.suffix if item.suffix else ''}"
        else:
            value = str(raw)
        rows.append((item.label, value))

    if spec.form_type == TRIP:
        rows.append(("Дней", str(days_of(details))))
    if spec.form_type == NIGHTS:
        rows.append(("Ночей", str(nights_of(details))))
    return rows

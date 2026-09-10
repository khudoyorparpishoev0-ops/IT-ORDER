import { useState } from "react";
import { Icon, type IconName } from "@/components/Icon";
import { PAYMENT_METHOD } from "@/data/status";
import { plural } from "@/data/format";
import { ROLE_LABEL } from "@/shell/config";
import type {
  EventDetails,
  EventKind,
  RequestEvent,
  RequestViewer,
  Stay,
} from "@/api/types";

/**
 * История заявки: кто что сделал, когда и что именно изменилось.
 *
 * Главное правило этого экрана — у каждой строки есть человек. Не
 * «Сумма утверждена», а «Искандар Саидов · Руководитель · Утвердил
 * сумму»: по журналу без имени невозможно ни спросить, ни поблагодарить,
 * ни понять, к кому идти. Поэтому имя набрано заметнее самого действия.
 *
 * Лента идёт от свежего к старому — так её и читают: «что случилось
 * последним». Действие человека и переход, который сделала система,
 * стоят отдельными строками: «одобрил и передал» — это два разных дела.
 */

type Tab = "all" | "decisions" | "comments" | "views" | "changes" | "system";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "decisions", label: "Решения" },
  { key: "comments", label: "Комментарии" },
  { key: "views", label: "Просмотры" },
  { key: "changes", label: "Изменения" },
  { key: "system", label: "Система" },
];

const OF_TAB: Record<Exclude<Tab, "all" | "views">, EventKind[]> = {
  decisions: [
    "submitted",
    "need_approved",
    "approved",
    "auto_approved",
    "rejected",
    "fulfilled",
  ],
  comments: ["commented"],
  changes: ["created", "edited", "priced"],
  system: ["moved", "sourcing"],
};

const ICON: Record<EventKind, IconName> = {
  created: "ti-plus",
  edited: "ti-checklist",
  submitted: "ti-file-text",
  need_approved: "ti-circle-check",
  sourcing: "ti-server-2",
  moved: "ti-server-2",
  priced: "ti-coin",
  fulfilled: "ti-package",
  approved: "ti-circle-check",
  auto_approved: "ti-circle-check",
  rejected: "ti-circle-x",
  paid: "ti-wallet",
  commented: "ti-message-circle",
  viewed: "ti-eye",
};

/**
 * Цвет события. Зелёный — состоялось, красный — отказ, синий —
 * информация и просмотр, серый — система. Жёлтый в ленте не нужен:
 * ожидание — это не событие, а промежуток между ними, и он показан
 * блоком «Сейчас ждёт».
 */
const TONE: Partial<Record<EventKind, string>> = {
  need_approved: "var(--green)",
  approved: "var(--green)",
  auto_approved: "var(--green)",
  fulfilled: "var(--green)",
  paid: "var(--green)",
  rejected: "var(--dot-err)",
  commented: "var(--blue)",
  priced: "var(--blue)",
  viewed: "var(--blue)",
};

/** Одна строка ленты — событие заявки или сведённый просмотр. */
type Item = {
  key: string;
  kind: EventKind;
  at: string;
  when: string;
  actor: string;
  role: string | null;
  system: boolean;
  text: string;
  details: EventDetails;
  /** Просмотр — не запись в базе событий, а сводка по человеку. */
  synthetic?: boolean;
  /** Порядок внутри одной отметки времени. `now()` в PostgreSQL — время
   *  начала транзакции, поэтому у «одобрил» и «передала дальше» она
   *  совпадает до микросекунды, и без номера лента их переставляет. */
  seq: number;
};

export function Timeline({
  events,
  viewers,
  stays,
}: {
  events: RequestEvent[];
  viewers: RequestViewer[];
  stays: Stay[];
}) {
  const [tab, setTab] = useState<Tab>("all");

  const fromEvents: Item[] = events.map((e, i) => ({
    key: `e${i}`,
    seq: i,
    kind: e.kind,
    at: e.created_at,
    when: when(e),
    actor: actorName(e),
    role: e.actor_role,
    system: e.actor_type === "system",
    text: e.text,
    details: e.details,
  }));

  // Просмотры приходят сведёнными по человеку, а не по каждому открытию:
  // карточку открывают по двадцать раз за день, и запись на каждое
  // открытие вытеснила бы из ленты то, ради чего её открыли.
  const fromViews: Item[] = viewers.map((v) => ({
    key: `v${v.employee_id}`,
    // Просмотры встают между событиями по времени первого открытия;
    // внутри одной отметки они идут первыми — карточку открывают, чтобы
    // что-то с ней сделать, а не наоборот.
    seq: -1,
    kind: "viewed",
    at: v.first_viewed_iso,
    when: v.first_viewed_at,
    actor: v.employee_name,
    role: v.role,
    system: false,
    synthetic: true,
    text:
      v.times > 1
        ? `Открытий карточки: ${v.times}, последнее — ${v.last_viewed_at}`
        : "Первое открытие карточки",
    details: {},
  }));

  const all = [...fromEvents, ...fromViews];
  const shown =
    tab === "all"
      ? all
      : tab === "views"
        ? fromViews
        : fromEvents.filter((e) => OF_TAB[tab].includes(e.kind));

  const count = (key: Tab) =>
    key === "all"
      ? all.length
      : key === "views"
        ? fromViews.length
        : fromEvents.filter((e) => OF_TAB[key].includes(e.kind)).length;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="h3">История</h2>
      </div>

      <div className="panel-body" style={{ display: "grid", gap: 16 }}>
        <div
          className="filter-row"
          role="tablist"
          aria-label="Что показывать в истории"
        >
          {TABS.map((t) => {
            // Вкладку без единой записи не показываем: пустая вкладка
            // обещает содержимое, которого нет, и её нажимают зря.
            const n = count(t.key);
            if (n === 0 && t.key !== "all") return null;
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                className="filter"
                aria-pressed={tab === t.key}
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
              >
                {t.label}
                <span className="num" style={{ color: "var(--slate)" }}>
                  {n}
                </span>
              </button>
            );
          })}
        </div>

        {tab === "all" && stays.length > 0 && <Stays stays={stays} />}

        <ol className="timeline">
          {sortNewestFirst(shown).map((item) => (
            <li key={item.key} className="tl-item">
              <span
                className="tl-icon"
                style={{
                  color: item.system
                    ? "var(--grey)"
                    : (TONE[item.kind] ?? "var(--slate)"),
                }}
              >
                <Icon name={ICON[item.kind] ?? "ti-history"} size={18} />
              </span>
              <div className="tl-body">
                <div className="tl-head">
                  <span className="tl-actor">{item.actor}</span>
                  <span className="meta num">{item.when}</span>
                </div>
                {(item.role || item.system) && (
                  <div className="tl-role">
                    {item.system
                      ? "Системное действие"
                      : (ROLE_LABEL[item.role!] ?? item.role)}
                  </div>
                )}
                <div className="tl-text">{item.text}</div>
                <Details details={item.details} />
              </div>
            </li>
          ))}
          {shown.length === 0 && (
            <li className="muted small">Записей этого вида по заявке нет.</li>
          )}
        </ol>
      </div>
    </section>
  );
}

/** Свежее сверху. Сортируем по времени, а не по порядку в массиве:
 *  просмотры приходят отдельным списком и встают между событиями. */
function sortNewestFirst(items: Item[]): Item[] {
  return [...items].sort((a, b) => {
    if (a.at !== b.at) return a.at < b.at ? 1 : -1;
    // Отметка времени совпала — порядок задаёт номер записи.
    return b.seq - a.seq;
  });
}

/**
 * Имя действующего лица. У системных записей — «Система»; у записей,
 * сделанных до появления истории, имя есть, а ссылки на сотрудника нет —
 * показываем имя. Если нет и его, честно пишем «Автор неизвестен»:
 * подставлять сюда догадку нельзя, журналом пользуются как документом.
 */
function actorName(event: RequestEvent): string {
  if (event.actor_type === "system") return "Система";
  const name = (event.actor || "").trim();
  if (!name || name === "СИСТЕМА") return "Автор неизвестен";
  return name;
}

/** «ИВАН ПЕТРОВ · 04.09.2026, 18:12» → «04.09.2026, 18:12». */
function when(event: RequestEvent): string {
  const m = /(\d{2}\.\d{2}\.\d{4},\s*\d{2}:\d{2})/.exec(event.meta);
  return m ? m[1] : event.meta;
}

/** Сколько заявка простояла на каждом шаге. Отвечает на вопрос «где она
 *  застряла», на который список событий сам по себе не отвечает. */
function Stays({ stays }: { stays: Stay[] }) {
  return (
    <div className="stays">
      <div className="label">Сколько где стояла</div>
      {stays.map((stay, i) => (
        <div key={i} className="stays-row">
          <span className="small">{stay.holder}</span>
          <span className="num small">
            {hours(stay.hours)}
            {stay.ongoing && " · идёт"}
          </span>
        </div>
      ))}
    </div>
  );
}

/** «26,4» → «1 д 2 ч». Минуты показываем только на коротких отрезках:
 *  «2 д 3 ч 17 мин» никто не читает до конца. */
function hours(value: number): string {
  if (value < 1) {
    const m = Math.max(1, Math.round(value * 60));
    return `${m} ${plural(m, "минута", "минуты", "минут")}`;
  }
  const total = Math.round(value);
  const d = Math.floor(total / 24);
  const h = total % 24;
  if (d === 0) return `${h} ${plural(h, "час", "часа", "часов")}`;
  return `${d} ${plural(d, "день", "дня", "дней")}${h ? ` ${h} ч` : ""}`;
}

/**
 * «Было → стало». Показываем только то, что действительно менялось:
 * строка «статус: pending → pending» ничего не сообщает, а место
 * занимает.
 */
function Details({ details }: { details: EventDetails }) {
  const rows: { k: string; v: React.ReactNode }[] = [];

  // Пара «было → стало» показывается, только если пришли обе половины:
  // «Сумма →» с пустыми краями сообщает читателю ровно ничего. Так
  // выглядели бы записи, сделанные до появления истории.
  if (details.amount?.from && details.amount?.to) {
    rows.push({
      k: "Сумма",
      v: (
        <>
          <span className="num">{details.amount.from}</span> →{" "}
          <b className="num">{details.amount.to}</b>
        </>
      ),
    });
  }
  if (details.project && (details.project.from || details.project.to)) {
    rows.push({
      k: "Объект",
      v: (
        <>
          {details.project.from ?? "—"} → <b>{details.project.to ?? "—"}</b>
        </>
      ),
    });
  }
  for (const line of details.prices ?? []) {
    rows.push({
      k: line.title,
      v: (
        <>
          <span className="num">{line.from}</span> →{" "}
          <b className="num">{line.to}</b>
        </>
      ),
    });
  }
  for (const line of details.changed ?? []) {
    rows.push({
      k: line.title,
      v: (
        <>
          <span className="num">{line.from}</span> →{" "}
          <b className="num">{line.to}</b>
        </>
      ),
    });
  }
  for (const line of details.added ?? []) {
    rows.push({ k: "Добавлено", v: `${line.title} — ${line.amount}` });
  }
  for (const line of details.removed ?? []) {
    rows.push({ k: "Удалено", v: `${line.title} — ${line.amount}` });
  }
  if (details.amount_total && !details.amount?.to) {
    rows.push({ k: "Сумма", v: <b className="num">{details.amount_total}</b> });
  }
  if (details.method) {
    const method = PAYMENT_METHOD[details.method as "card" | "cash"];
    rows.push({ k: "Способ", v: method ?? details.method });
  }
  if (details.document) {
    rows.push({
      k: "Документ",
      v: <span className="num">{details.document}</span>,
    });
  }
  if (details.stage) {
    rows.push({ k: "Этап", v: details.stage });
  }
  if (details.author) {
    rows.push({ k: "Автор заявки", v: details.author });
  }
  if (details.waiting?.length) {
    rows.push({ k: "Может взять", v: details.waiting.join(", ") });
  }

  if (rows.length === 0) return null;
  return (
    <dl className="tl-details">
      {rows.map((row, i) => (
        <div key={i}>
          <dt>{row.k}</dt>
          <dd>{row.v}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Кто открывал заявку — отдельный список, а не лента. Отвечает автору
 * на вопрос, которого раньше нельзя было задать: она просто лежит в
 * очереди или её действительно смотрели.
 *
 * Адреса и браузера здесь нет намеренно: сотруднику они ничего не
 * объясняют, а показывать их «на всякий случай» — это уже слежка за
 * людьми, а не история заявки.
 */
export function Viewers({ viewers }: { viewers: RequestViewer[] }) {
  if (viewers.length === 0) return null;
  return (
    <div className="table-wrap">
      <table
        className="tbl fit compact"
        style={{ ["--tbl-min" as string]: "420px" }}
      >
        <thead>
          <tr>
            <th>Кто</th>
            <th>Впервые</th>
            <th>В последний раз</th>
            <th className="right">Раз</th>
          </tr>
        </thead>
        <tbody>
          {viewers.map((v) => (
            <tr key={v.employee_id}>
              <td>{v.employee_name}</td>
              <td className="num">{v.first_viewed_at}</td>
              <td className="num">{v.last_viewed_at}</td>
              <td className="right num">{v.times}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

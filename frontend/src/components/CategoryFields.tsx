import { Field } from '@/components/Field';
import { money, plural } from '@/data/format';
import type { CategoryField, ExpenseCategory } from '@/api/types';

/**
 * Поля формы под выбранную категорию расхода.
 *
 * Набор полей приходит с сервера — панель своего списка не держит.
 * Иначе форма и проверка однажды разойдутся, и человек будет получать
 * «обязательное поле» про поле, которого на экране нет.
 *
 * Раскладка в один столбец: это форма, которую заполняют с телефона на
 * объекте, а не таблица. Числа и деньги идут парами по ширине, где
 * помещаются.
 */
export function CategoryFields({
  spec,
  values,
  onChange,
}: {
  spec: ExpenseCategory;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
}) {
  if (spec.fields.length === 0) return null;

  return (
    <section className="card" style={{ display: 'grid', gap: 12 }}>
      <div className="label">{spec.name}</div>
      <div className="cat-fields">
        {spec.fields.map((item) => (
          <One key={item.key} item={item} value={values[item.key]} onChange={onChange} />
        ))}
      </div>
      <Total spec={spec} values={values} />
    </section>
  );
}

function One({
  item,
  value,
  onChange,
}: {
  item: CategoryField;
  value: unknown;
  onChange: (key: string, value: unknown) => void;
}) {
  const text = value === undefined || value === null ? '' : String(value);
  const wide = item.kind === 'textarea' || item.kind === 'select' || item.kind === 'text';

  // Под заполненной датой повторяем её по-русски. Браузер рисует поле
  // даты в своей локали, и на телефоне с английской это «mm/dd/yyyy»:
  // человек введёт 11 сентября, а получит 9 ноября и не заметит.
  // Значение при этом всегда ISO, портиться нечему — портится чтение.
  const note =
    item.kind === 'date' && text ? readable(text) ?? item.note ?? undefined : item.note ?? undefined;

  return (
    <div className={wide ? 'cat-field wide' : 'cat-field'}>
      <Field label={item.label} required={item.required} note={note}>
        {(id) => {
          if (item.kind === 'select') {
            return (
              <select
                id={id}
                className="field"
                value={text}
                onChange={(e) => onChange(item.key, e.target.value || null)}
              >
                <option value="">Выберите</option>
                {item.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            );
          }
          if (item.kind === 'textarea') {
            return (
              <textarea
                id={id}
                className="field"
                rows={3}
                value={text}
                onChange={(e) => onChange(item.key, e.target.value)}
              />
            );
          }
          if (item.kind === 'date') {
            return (
              <input
                id={id}
                className="field"
                type="date"
                value={text}
                onChange={(e) => onChange(item.key, e.target.value)}
              />
            );
          }
          // Числа и деньги — `inputMode`, а не `type="number"`: у
          // числового поля на телефоне колёсико прокрутки меняет
          // значение, а запятая в сумме не вводится вовсе.
          return (
            <div className="cat-num">
              <input
                id={id}
                className="field"
                inputMode={item.kind === 'money' ? 'decimal' : 'numeric'}
                value={text}
                onChange={(e) => onChange(item.key, e.target.value)}
              />
              {(item.suffix || item.kind === 'money') && (
                <span className="cat-suffix">{item.suffix ?? 'TJS'}</span>
              )}
            </div>
          );
        }}
      </Field>
    </div>
  );
}

/**
 * Итог по полям — тот же расчёт, что на сервере, только для глаз.
 *
 * В базу идёт сумма, посчитанная сервером: деньги в ORDER считаются в
 * одном месте. Здесь она нужна, чтобы человек увидел «400,00» до того,
 * как нажмёт «Отправить», и заметил опечатку в ставке.
 */
function Total({ spec, values }: { spec: ExpenseCategory; values: Record<string, unknown> }) {
  const total = estimate(spec, values);
  const span = spanOf(spec, values);
  if (total === null && span === null) return null;
  return (
    <div className="cat-total">
      <span className="small" style={{ color: 'var(--slate)' }}>
        {span ?? 'Итого'}
      </span>
      {total !== null ? (
        <span className="num-lg">{money(total.toFixed(2))} TJS</span>
      ) : (
        <span className="small" style={{ color: 'var(--slate)' }}>
          сумму назовёт отдел закупа
        </span>
      )}
    </div>
  );
}

/** «3 дня» у командировки, «3 ночи» у проживания — по датам. Заодно это
 *  проверка самих дат: увидев «1 день» вместо трёх, человек заметит, что
 *  ввёл не то. */
function spanOf(spec: ExpenseCategory, values: Record<string, unknown>): string | null {
  if (spec.form_type === 'trip') {
    const d = days(values, 'date_from', 'date_to');
    return d ? `Итого за ${d + 1} ${plural(d + 1, 'день', 'дня', 'дней')}` : null;
  }
  if (spec.form_type === 'nights') {
    const n = days(values, 'check_in', 'check_out');
    return n ? `Итого за ${n} ${plural(n, 'ночь', 'ночи', 'ночей')}` : null;
  }
  return null;
}

/** «2026-09-11» → «11.09.2026». Непонятное — молчим. */
function readable(iso: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : null;
}

function num(values: Record<string, unknown>, key: string): number {
  const raw = Number(String(values[key] ?? '').replace(',', '.'));
  return Number.isFinite(raw) && raw > 0 ? raw : 0;
}

function days(values: Record<string, unknown>, from: string, to: string): number {
  const a = Date.parse(String(values[from] ?? ''));
  const b = Date.parse(String(values[to] ?? ''));
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 0;
  return Math.max(0, Math.round((b - a) / 86_400_000));
}

/** Сколько получится. null — по этой форме итог не складывается. */
export function estimate(
  spec: ExpenseCategory,
  values: Record<string, unknown>,
): number | null {
  switch (spec.form_type) {
    case 'people_days':
      return num(values, 'rate') * num(values, 'people') * num(values, 'days') || null;
    case 'nights': {
      const nights = Math.max(1, days(values, 'check_in', 'check_out'));
      const rooms = num(values, 'rooms') || 1;
      return num(values, 'nightly_rate') * nights * rooms || null;
    }
    case 'trip':
      return (
        num(values, 'transport') +
          num(values, 'lodging') +
          num(values, 'per_diem') +
          num(values, 'other') || null
      );
    case 'cargo':
      return num(values, 'cargo_cost') + num(values, 'customs') + num(values, 'extra') || null;
    case 'lines':
      return null;
    default:
      return num(values, 'amount') || null;
  }
}

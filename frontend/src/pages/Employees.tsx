import { useMemo, useState } from 'react';
import { Field } from '@/components/Field';
import { Icon } from '@/components/Icon';
import { Overlay } from '@/components/Overlay';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useAuth } from '@/api/auth';
import {
  useCreateEmployee,
  useDeleteEmployee,
  useEmployeeAccess,
  useEmployees,
  useHealth,
  useResetEmployee2fa,
  useSetEmployeePassword,
  useUpdateEmployee,
} from '@/api/hooks';
import type { Employee, EmployeeAccess, EmployeeInput, EmployeeRole } from '@/api/types';
import { formatDateTime, money } from '@/data/format';
import { ROLE_LABEL } from '@/shell/config';
import { useShell } from '@/shell/ShellContext';

/** Столько же требует сервер (MIN_PASSWORD_LENGTH). Расходиться им нельзя:
 *  иначе панель разрешит ввод, который тут же отклонит API. */
const MIN_PASSWORD = 10;

const ROLES: EmployeeRole[] = ['employee', 'manager', 'finance', 'admin'];

/** Что роль даёт — подсказка под выбором, чтобы права не назначали наугад. */
const ROLE_NOTE: Record<EmployeeRole, string> = {
  employee: 'Подаёт заявки и видит только свои.',
  manager: 'Видит все заявки, утверждает и отклоняет, смотрит отчёты.',
  finance: 'Видит все заявки, проводит выплаты, смотрит отчёты.',
  admin: 'Всё перечисленное плюс справочники, роли и пароли.',
};

export function Employees() {
  const { user } = useAuth();
  const { flash } = useShell();
  const list = useEmployees();
  const access = useEmployeeAccess();
  const health = useHealth();

  const [search, setSearch] = useState('');
  const [withDisabled, setWithDisabled] = useState(false);
  const [editing, setEditing] = useState<Employee | 'new' | null>(null);

  const accessById = useMemo(() => {
    const map = new Map<number, EmployeeAccess>();
    for (const a of access.data ?? []) map.set(a.id, a);
    return map;
  }, [access.data]);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (list.data ?? []).filter((e) => {
      if (!withDisabled && !e.active) return false;
      if (!needle) return true;
      return `${e.full_name} ${e.position} ${e.email ?? ''}`.toLowerCase().includes(needle);
    });
  }, [list.data, search, withDisabled]);

  const disabledCount = (list.data ?? []).filter((e) => !e.active).length;

  return (
    <>
      <PageHeader
        kicker="СПРАВОЧНИК"
        title="Сотрудники"
        lead="Кто заведён в системе, кто может входить и с какими правами"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
            <Icon name="ti-plus" />
            Добавить сотрудника
          </button>
        }
      />

      <div
        style={{
          display: 'flex',
          gap: 8,
          flexWrap: 'wrap',
          alignItems: 'center',
          marginBottom: 'var(--gap)',
        }}
      >
        <label style={{ flex: '1 1 240px', maxWidth: 360 }}>
          <span className="sr-only">Поиск по имени, должности или почте</span>
          <input
            className="field"
            type="search"
            placeholder="Имя, должность или почта"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {disabledCount > 0 && (
          <button
            type="button"
            className="chip"
            aria-pressed={withDisabled}
            onClick={() => setWithDisabled((v) => !v)}
          >
            Показать отключённых ({disabledCount})
          </button>
        )}
      </div>

      <QueryState
        isLoading={list.isLoading}
        error={list.error ?? access.error}
        isEmpty={rows.length === 0}
        emptyTitle={search ? 'Никто не найден' : 'Сотрудники не заведены'}
        emptyNote={
          search
            ? 'Проверьте написание или очистите поиск.'
            : 'Заведите коллег, чтобы они могли входить в систему и подавать заявки.'
        }
        emptyAction={
          <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
            Добавить сотрудника
          </button>
        }
        onRetry={() => {
          list.refetch();
          access.refetch();
        }}
      >
        <section className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ minWidth: 760 }}>
              <thead>
                <tr>
                  <th style={{ width: '26%' }}>СОТРУДНИК</th>
                  <th style={{ width: '20%' }}>ПОЧТА</th>
                  <th style={{ width: '14%' }}>РОЛЬ</th>
                  <th className="right" style={{ width: '12%' }}>
                    ЛИМИТ, TJS
                  </th>
                  <th style={{ width: '16%' }}>ДОСТУП</th>
                  <th style={{ width: '12%' }}>ВТОРОЙ ФАКТОР</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => {
                  const a = accessById.get(e.id);
                  return (
                    <tr
                      key={e.id}
                      className="clickable"
                      tabIndex={0}
                      onClick={() => setEditing(e)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setEditing(e);
                        }
                      }}
                    >
                      <td>
                        <div style={{ fontWeight: 600 }}>{e.full_name}</div>
                        <div className="caption">{e.position || '—'}</div>
                      </td>
                      <td className="num">{e.email ?? '—'}</td>
                      <td>
                        {ROLE_LABEL[e.role] ?? e.role}
                        {user?.id === e.id && <div className="caption">это вы</div>}
                      </td>
                      <td className="right num">{e.monthly_limit ? money(e.monthly_limit) : '—'}</td>
                      <td>
                        <AccessMark employee={e} access={a} />
                      </td>
                      <td>
                        <TwoFactorMark access={a} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </QueryState>

      <p className="caption" style={{ marginTop: 'var(--gap)' }}>
        Уволенного сотрудника отключают, а не удаляют: заявки неизменяемы и
        должны сохранить автора. Удаление доступно только для записи, по
        которой ещё не подано ни одной заявки.
      </p>

      {editing && (
        <EmployeeModal
          employee={editing === 'new' ? null : editing}
          access={editing === 'new' ? undefined : accessById.get(editing.id)}
          isSelf={editing !== 'new' && user?.id === editing.id}
          timezone={health.data?.timezone}
          onClose={() => setEditing(null)}
          onFlash={flash}
        />
      )}
    </>
  );
}

/** Состояние всегда цвет И текст — цвет сам по себе брендбук запрещает. */
function Mark({ color, text, note }: { color: string; text: string; note?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span aria-hidden="true" style={{ width: 8, height: 8, flex: 'none', background: color }} />
      <span>
        {text}
        {note && <div className="caption">{note}</div>}
      </span>
    </div>
  );
}

function AccessMark({ employee, access }: { employee: Employee; access?: EmployeeAccess }) {
  if (!employee.active) return <Mark color="var(--dot-off)" text="Отключён" />;
  if (access?.locked_until && new Date(access.locked_until) > new Date()) {
    return <Mark color="var(--dot-err)" text="Заблокирован" note="перебор пароля" />;
  }
  if (!employee.email) return <Mark color="var(--dot-warn)" text="Без почты" note="войти не сможет" />;
  if (access && !access.has_password) {
    return <Mark color="var(--dot-warn)" text="Пароль не задан" />;
  }
  return <Mark color="var(--dot-ok)" text="Вход открыт" />;
}

function TwoFactorMark({ access }: { access?: EmployeeAccess }) {
  if (!access) return <span className="caption">—</span>;
  if (access.two_factor_enabled) {
    return (
      <Mark
        color="var(--dot-ok)"
        text="Включён"
        note={`кодов: ${access.recovery_codes_left}`}
      />
    );
  }
  if (access.two_factor_required) {
    return <Mark color="var(--dot-warn)" text="Настроит при входе" />;
  }
  return <Mark color="var(--dot-off)" text="Выключен" />;
}

type ModalProps = {
  employee: Employee | null;
  access?: EmployeeAccess;
  isSelf: boolean;
  timezone?: string;
  onClose: () => void;
  onFlash: (text: string, color: string) => void;
};

function EmployeeModal({ employee, access, isSelf, timezone, onClose, onFlash }: ModalProps) {
  const create = useCreateEmployee();
  const update = useUpdateEmployee();
  const setPassword = useSetEmployeePassword();

  const [fullName, setFullName] = useState(employee?.full_name ?? '');
  const [position, setPosition] = useState(employee?.position ?? '');
  const [email, setEmail] = useState(employee?.email ?? '');
  const [phone, setPhone] = useState(employee?.phone ?? '');
  const [role, setRole] = useState<EmployeeRole>(employee?.role ?? 'employee');
  const [limit, setLimit] = useState(employee?.monthly_limit ?? '');
  const [active, setActive] = useState(employee?.active ?? true);
  const [password, setPasswordValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const payload = (): EmployeeInput => ({
    full_name: fullName.trim(),
    position: position.trim(),
    email: email.trim() ? email.trim() : null,
    phone: phone.trim() ? phone.trim() : null,
    role,
    // Запятую из русской раскладки сервер не поймёт — переводим в точку.
    monthly_limit: limit.trim() ? limit.trim().replace(',', '.') : null,
    active,
  });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      if (employee) {
        await update.mutateAsync({ id: employee.id, ...payload() });
        onFlash('Карточка сохранена', 'var(--dot-ok)');
        onClose();
        return;
      }

      const created = await create.mutateAsync(payload());
      if (!password) {
        onFlash('Сотрудник заведён', 'var(--dot-ok)');
        onClose();
        return;
      }
      try {
        await setPassword.mutateAsync({ id: created.id, password });
        onFlash('Сотрудник заведён, доступ выдан', 'var(--dot-ok)');
        onClose();
      } catch (err) {
        // Карточка уже создана — сообщаем об этом прямо, иначе
        // администратор попробует завести человека повторно.
        setError(
          `Сотрудник заведён, но пароль не задан: ${message(err)}. ` +
            'Закройте окно и выдайте пароль из его карточки.',
        );
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Overlay label={employee ? `Сотрудник ${employee.full_name}` : 'Новый сотрудник'} onClose={onClose}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <div className="label">{employee ? 'КАРТОЧКА СОТРУДНИКА' : 'НОВЫЙ СОТРУДНИК'}</div>
          <div className="h3" style={{ marginTop: 4 }}>
            {employee ? employee.full_name : 'Заведение сотрудника'}
          </div>
        </div>
        <button
          type="button"
          className="btn btn-icon"
          onClick={onClose}
          aria-label="Закрыть"
          style={{ border: 'none' }}
        >
          <Icon name="ti-x" />
        </button>
      </div>

      <form onSubmit={submit} style={{ display: 'grid', gap: 16, marginTop: 24 }}>
        <Field label="Имя и фамилия">
          {(id) => (
            <input
              id={id}
              className="field"
              required
              autoFocus
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          )}
        </Field>

        <Field label="Должность">
          {(id) => (
            <input
              id={id}
              className="field"
              value={position}
              onChange={(e) => setPosition(e.target.value)}
            />
          )}
        </Field>

        <Field
          label="Рабочая почта"
          note="Она же логин. Личные ящики система не принимает. Без почты сотрудник может только фигурировать в заявках."
        >
          {(id) => (
            <input
              id={id}
              className="field num"
              type="email"
              autoComplete="off"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </Field>

        <Field label="Телефон">
          {(id) => (
            <input
              id={id}
              className="field num"
              autoComplete="off"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          )}
        </Field>

        <Field label="Роль" note={ROLE_NOTE[role]}>
          {(id) => (
            <select
              id={id}
              className="field"
              value={role}
              onChange={(e) => setRole(e.target.value as EmployeeRole)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r] ?? r}
                </option>
              ))}
            </select>
          )}
        </Field>

        <Field label="Месячный лимит, TJS" note="Пусто — лимит не задан, расход не ограничен.">
          {(id) => (
            <input
              id={id}
              className="field num"
              inputMode="decimal"
              value={limit ?? ''}
              onChange={(e) => setLimit(e.target.value)}
            />
          )}
        </Field>

        <SquareCheck
          label="Работает в компании"
          checked={active}
          onToggle={() => setActive((v) => !v)}
          note="Снятая отметка закрывает вход и убирает сотрудника из списков — заявки при этом сохраняются."
        />

        {!employee && (
          <PasswordField
            value={password}
            onChange={setPasswordValue}
            disabled={!email.trim()}
            note={
              email.trim()
                ? 'Можно оставить пустым и выдать пароль позже.'
                : 'Пароль выдаётся только вместе с рабочей почтой — она служит логином.'
            }
          />
        )}

        {isSelf && (
          <p className="caption" style={{ margin: 0, color: 'var(--dot-warn)' }}>
            Это ваша учётная запись. Понизив себе роль или сняв отметку, вы
            потеряете доступ к этому разделу.
          </p>
        )}

        {error && (
          <div className="field-error-text" role="alert">
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="submit" className="btn btn-primary" disabled={saving || !fullName.trim()}>
            {saving ? 'Сохраняем…' : employee ? 'Сохранить' : 'Завести сотрудника'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
        </div>
      </form>

      {employee && (
        <AccessSection
          employee={employee}
          access={access}
          timezone={timezone}
          onFlash={onFlash}
          onDeleted={onClose}
        />
      )}
    </Overlay>
  );
}

/** Доступ существующего сотрудника: пароль, второй фактор, удаление. */
function AccessSection({
  employee,
  access,
  timezone,
  onFlash,
  onDeleted,
}: {
  employee: Employee;
  access?: EmployeeAccess;
  timezone?: string;
  onFlash: (text: string, color: string) => void;
  onDeleted: () => void;
}) {
  const setPassword = useSetEmployeePassword();
  const reset2fa = useResetEmployee2fa();
  const remove = useDeleteEmployee();

  const [password, setPasswordValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<unknown>, done: () => void) => {
    setError(null);
    setBusy(true);
    try {
      await action();
      done();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section style={{ marginTop: 32, borderTop: '1px solid var(--line)', paddingTop: 24 }}>
      <div className="label">ДОСТУП В СИСТЕМУ</div>

      <dl style={{ display: 'grid', gap: 12, margin: '16px 0 0' }}>
        <div>
          <dt className="caption">Последний вход</dt>
          <dd className="num" style={{ margin: '2px 0 0' }}>
            {access?.last_login_at ? formatDateTime(access.last_login_at, timezone) : 'ни разу'}
          </dd>
        </div>
        <div>
          <dt className="caption">Второй фактор</dt>
          <dd style={{ margin: '2px 0 0' }}>
            {access?.two_factor_enabled
              ? `включён, кодов восстановления осталось ${access.recovery_codes_left}`
              : access?.two_factor_required
                ? 'не настроен — система попросит настроить при первом входе'
                : 'выключен'}
          </dd>
        </div>
      </dl>

      <div style={{ marginTop: 24 }}>
        <PasswordField
          value={password}
          onChange={setPasswordValue}
          disabled={!employee.email}
          label={access?.has_password ? 'Новый пароль' : 'Пароль для входа'}
          note={
            employee.email
              ? 'Передайте пароль лично и попросите сменить его в «Параметрах». Прежний пароль перестанет работать сразу.'
              : 'Сначала заполните рабочую почту — она служит логином.'
          }
        />
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginTop: 16 }}
          disabled={busy || password.length < MIN_PASSWORD}
          onClick={() =>
            run(
              () => setPassword.mutateAsync({ id: employee.id, password }),
              () => {
                setPasswordValue('');
                onFlash('Пароль назначен', 'var(--dot-ok)');
              },
            )
          }
        >
          {access?.has_password ? 'Заменить пароль' : 'Выдать пароль'}
        </button>
      </div>

      {error && (
        <div className="field-error-text" role="alert" style={{ marginTop: 16 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 24, flexWrap: 'wrap' }}>
        {access?.two_factor_enabled && (
          <Confirm
            label="Сбросить второй фактор"
            question="Сбросить? Сотрудник настроит приложение заново."
            danger={false}
            disabled={busy}
            onConfirm={() =>
              run(
                () => reset2fa.mutateAsync(employee.id),
                () => onFlash('Второй фактор сброшен', 'var(--dot-warn)'),
              )
            }
          />
        )}
        <Confirm
          label="Удалить запись"
          question="Удалить безвозвратно?"
          danger
          disabled={busy}
          onConfirm={() =>
            run(
              () => remove.mutateAsync(employee.id),
              () => {
                onFlash('Запись удалена', 'var(--dot-warn)');
                onDeleted();
              },
            )
          }
        />
      </div>
      <p className="caption" style={{ margin: '8px 0 0' }}>
        Сброс второго фактора нужен, когда сотрудник потерял и телефон, и коды
        восстановления. Удаление работает только для записи без заявок.
      </p>
    </section>
  );
}

function PasswordField({
  value,
  onChange,
  disabled,
  label = 'Пароль для входа',
  note,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  label?: string;
  note?: string;
}) {
  const short = value.length > 0 && value.length < MIN_PASSWORD;
  return (
    <Field
      label={label}
      note={
        short
          ? `Нужно не меньше ${MIN_PASSWORD} символов.`
          : note
      }
    >
      {(id) => (
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            id={id}
            className={`field num${short ? ' field-error' : ''}`}
            type="text"
            autoComplete="off"
            spellCheck={false}
            disabled={disabled}
            value={value}
            onChange={(e) => onChange(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-secondary"
            disabled={disabled}
            onClick={() => onChange(generatePassword())}
          >
            Сгенерировать
          </button>
        </div>
      )}
    </Field>
  );
}

/**
 * Случайный пароль. Показывается открытым текстом: администратор должен
 * его прочитать и передать сотруднику — второй раз система его не покажет,
 * в базе лежит только хэш. Похожие символы (0/O, 1/l/I) исключены, чтобы
 * пароль не переписали с ошибкой.
 */
function generatePassword(length = 14): string {
  const alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const bytes = new Uint32Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (n) => alphabet[n % alphabet.length]).join('');
}

/** Опасное действие подтверждается на месте: окно confirm() выпадает из
 *  оформления, а без подтверждения кнопку задевают случайно. */
function Confirm({
  label,
  question,
  danger,
  disabled,
  onConfirm,
}: {
  label: string;
  question: string;
  danger: boolean;
  disabled?: boolean;
  onConfirm: () => void;
}) {
  const [asking, setAsking] = useState(false);

  if (!asking) {
    return (
      <button
        type="button"
        className={danger ? 'btn btn-danger' : 'btn btn-secondary'}
        disabled={disabled}
        onClick={() => setAsking(true)}
      >
        {label}
      </button>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span className="caption">{question}</span>
      <button
        type="button"
        className={danger ? 'btn btn-danger' : 'btn btn-primary'}
        disabled={disabled}
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        Да
      </button>
      <button type="button" className="btn btn-ghost" onClick={() => setAsking(false)}>
        Отмена
      </button>
    </div>
  );
}

/** Тумблеры-«таблетки» брендбук запрещает — только квадратный чекбокс. */
function SquareCheck({
  label,
  note,
  checked,
  onToggle,
}: {
  label: string;
  note?: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <div>
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        onClick={onToggle}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          minHeight: 44,
          padding: '0 4px',
          border: 'none',
          background: 'transparent',
          textAlign: 'left',
          cursor: 'pointer',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 20,
            height: 20,
            flex: 'none',
            display: 'grid',
            placeItems: 'center',
            borderRadius: 'var(--r-field)',
            border: checked ? '1px solid var(--green)' : '1px solid var(--grey)',
            background: checked ? 'var(--green)' : 'transparent',
            color: '#FFFFFF',
          }}
        >
          <Icon name="ti-check" size={14} style={{ opacity: checked ? 1 : 0 }} />
        </span>
        {label}
      </button>
      {note && (
        <div className="caption" style={{ marginTop: 4 }}>
          {note}
        </div>
      )}
    </div>
  );
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Не удалось выполнить действие';
}

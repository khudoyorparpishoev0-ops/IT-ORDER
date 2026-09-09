import { useEffect, useState, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { Field } from '@/components/Field';
import { PageHeader } from '@/components/PageHeader';
import {
  useHealth,
  useJobRuns,
  usePushConfig,
  usePushSubscribe,
  usePushTest,
  usePushUnsubscribe,
  useRunJob,
  useTelegramLink,
  useTelegramSetup,
  useTelegramStatus,
  useTelegramUnlink,
} from '@/api/hooks';
import { useAuth } from '@/api/auth';
import { formatDateTime } from '@/data/format';
import { api } from '@/api/client';
import { ROLE_LABEL } from '@/shell/config';
import { RecoveryCodes } from '@/components/RecoveryCodes';
import { TotpSetup } from '@/components/TotpSetup';

/** Ключи совпадают с полями API. */
const NOTIFICATIONS = [
  { key: 'new_requests', label: 'Новые заявки на утверждение' },
  { key: 'stale_requests', label: 'Напоминание о заявках старше 3 дней' },
  { key: 'weekly_budget', label: 'Еженедельный отчёт по бюджету' },
] as const;
import type { Theme } from '@/shell/config';
import { useShell } from '@/shell/ShellContext';
import {
  currentPushSubscription,
  getInstallState,
  promptInstall,
  pushPermission,
  pushSupport,
  subscribeInstall,
  subscribePush,
  subscriptionPayload,
  unsubscribePush,
} from '@/pwa';

export function Settings() {
  const { theme, setTheme, flash } = useShell();
  const { user } = useAuth();
  const health = useHealth();

  return (
    <>
      <PageHeader title="Параметры" lead="Профиль, вход, оформление и уведомления" />

      <div className="grid-auto">
        <Card title="Профиль">
          <dl style={{ display: 'grid', gap: 12, margin: 0 }}>
            <Row k="Имя и фамилия" v={<span style={{ fontWeight: 600 }}>{user?.full_name}</span>} />
            <Row k="Должность" v={user?.position || '—'} />
            <Row k="Рабочая почта" v={<span className="num">{user?.email ?? '—'}</span>} />
            <Row k="Роль" v={user ? (ROLE_LABEL[user.role] ?? user.role) : '—'} />
          </dl>
          <p className="caption" style={{ margin: 0 }}>
            Имя, должность и роль меняет администратор системы.
          </p>
        </Card>

        <PasswordCard onDone={() => flash('Пароль изменён', 'var(--dot-ok)')} />

        <TwoFactorCard onFlash={flash} />

        <Card title="Тема оформления">
          <div className="filter-row" role="group" aria-label="Тема оформления">
            {(
              [
                ['light', 'Светлая'],
                ['dark', 'Тёмная'],
              ] as [Theme, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className="filter"
                aria-pressed={theme === value}
                onClick={() => setTheme(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="caption" style={{ margin: 0 }}>
            Тёмная тема спроектирована отдельно, а не инверсией светлой. Выбор
            запоминается в этом браузере.
          </p>
        </Card>

        <NotificationsCard onFlash={flash} />
        <TelegramCard onFlash={flash} />
        <InstallCard onFlash={flash} />
        <PushCard onFlash={flash} />
        <JobsCard onFlash={flash} />

        <Card title="О системе">
          <dl style={{ display: 'grid', gap: 12, margin: 0 }}>
            <Row k="Часовой пояс расчётов" v={<span className="num">{health.data?.timezone ?? '—'}</span>} />
            <Row
              k="Состояние базы"
              v={
                <Status
                  on={health.data?.database === 'ok'}
                  text={health.data?.database === 'ok' ? 'Доступна' : 'Недоступна'}
                  offColor="var(--dot-err)"
                />
              }
            />
            <Row k="Версия схемы" v={<span className="num">{health.data?.db_revision ?? '—'}</span>} />
          </dl>
        </Card>
      </div>
    </>
  );
}

/* ---------- Кирпичики страницы ---------- */

/** Карточка раздела: заголовок H3 и содержимое столбиком с шагом 16. */
function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card" style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
      <h2 className="h3">{title}</h2>
      {children}
    </section>
  );
}

/** Строка «подпись — значение» в описательном списке. */
function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'baseline' }}>
      <dt className="small" style={{ color: 'var(--slate)' }}>
        {k}
      </dt>
      <dd style={{ margin: 0, textAlign: 'right', minWidth: 0, overflowWrap: 'anywhere' }}>{v}</dd>
    </div>
  );
}

/** Кнопки в карточке: строкой, не растягиваясь на ширину сетки. */
function Actions({ children }: { children: ReactNode }) {
  return <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{children}</div>;
}

/** Состояние словом и точкой: цвет никогда не идёт без подписи. */
function Status({ on, text, offColor = 'var(--dot-off)' }: { on: boolean; text: string; offColor?: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
      <span className="dot" style={{ ['--dot' as string]: on ? 'var(--dot-ok)' : offColor }} aria-hidden="true" />
      {text}
    </span>
  );
}

/** Предупреждение: жёлтая точка перед текстом. Жёлтым текстом на светлом
 *  фоне писать нельзя — контраста не хватает. */
function Warn({ children }: { children: ReactNode }) {
  return (
    <p className="caption" style={{ display: 'flex', gap: 8, alignItems: 'flex-start', margin: 0 }}>
      <span className="dot" style={{ ['--dot' as string]: 'var(--yellow)', marginTop: 7 }} aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

/** Смена собственного пароля. Требует текущий — иначе оставленная без
 *  присмотра сессия позволила бы захватить учётную запись. */
function PasswordCard({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next !== repeat) {
      setError('Новый пароль и повтор не совпадают');
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await api('/api/auth/password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      setCurrent('');
      setNext('');
      setRepeat('');
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сменить пароль');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Смена пароля">
      <form onSubmit={submit} style={{ display: 'grid', gap: 16 }}>
        <Field label="Текущий пароль" required>
          {(id) => (
            <input
              id={id}
              className="field"
              type="password"
              autoComplete="current-password"
              required
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          )}
        </Field>
        <Field label="Новый пароль" required>
          {(id) => (
            <input
              id={id}
              className={`field${error ? ' field-error' : ''}`}
              type="password"
              autoComplete="new-password"
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
              aria-invalid={Boolean(error)}
            />
          )}
        </Field>
        <Field
          label="Повторите новый пароль"
          required
          error={error}
          note="Возьмите фразу от десяти символов: длинную проще запомнить и труднее подобрать."
        >
          {(id) => (
            <input
              id={id}
              className={`field${error ? ' field-error' : ''}`}
              type="password"
              autoComplete="new-password"
              required
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              aria-invalid={Boolean(error)}
            />
          )}
        </Field>
        <Actions>
          <button type="submit" className="btn btn-primary" disabled={saving || !current || !next || !repeat}>
            {saving ? 'Сохраняем…' : 'Сменить пароль'}
          </button>
        </Actions>
      </form>
    </Card>
  );
}

/**
 * Второй фактор: включение, перевыпуск кодов восстановления, отключение.
 * Ролям, которым он обязателен, отключение недоступно.
 */
function TwoFactorCard({ onFlash }: { onFlash: (text: string, color: string) => void }) {
  const { user, refresh } = useAuth();
  const [mode, setMode] = useState<'idle' | 'setup'>('idle');
  const [password, setPassword] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  const act = async (path: string, done: (data: { codes?: string[] }) => void) => {
    setError(null);
    setBusy(true);
    try {
      const data = await api<{ codes?: string[] }>(path, {
        method: 'POST',
        body: JSON.stringify({ password }),
      });
      setPassword('');
      done(data);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось выполнить действие');
    } finally {
      setBusy(false);
    }
  };

  if (codes) {
    return (
      <section className="card">
        <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />
      </section>
    );
  }

  if (mode === 'setup') {
    return (
      <Card title="Двухфакторный вход">
        <TotpSetup
          onCancel={() => setMode('idle')}
          onDone={() => {
            setMode('idle');
            refresh();
            onFlash('Двухфакторный вход включён', 'var(--dot-ok)');
          }}
        />
      </Card>
    );
  }

  return (
    <Card title="Двухфакторный вход">
      <div style={{ display: 'grid', gap: 8 }}>
        <Status on={user.two_factor_enabled} text={user.two_factor_enabled ? 'Включён' : 'Выключен'} />
        <p className="caption" style={{ margin: 0 }}>
          {user.two_factor_enabled
            ? `Кодов восстановления осталось: ${user.recovery_codes_left}.`
            : 'Пароль можно подсмотреть или подобрать. Код из приложения на телефоне закрывает вход, даже если пароль стал известен.'}
          {user.two_factor_required && ' Для вашей роли он обязателен.'}
        </p>
      </div>

      {!user.two_factor_enabled && (
        <Actions>
          <button type="button" className="btn btn-primary" onClick={() => setMode('setup')}>
            Включить
          </button>
        </Actions>
      )}

      {user.two_factor_enabled && (
        <>
          <Field label="Подтвердите паролем" error={error}>
            {(id) => (
              <input
                id={id}
                className={`field${error ? ' field-error' : ''}`}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (error) setError(null);
                }}
                aria-invalid={Boolean(error)}
              />
            )}
          </Field>

          <Actions>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy || !password}
              onClick={() => act('/api/auth/2fa/recovery-codes', (data) => setCodes(data.codes ?? []))}
            >
              Новые коды восстановления
            </button>
            {!user.two_factor_required && (
              <button
                type="button"
                className="btn btn-danger"
                disabled={busy || !password}
                onClick={() =>
                  act('/api/auth/2fa/disable', () => onFlash('Двухфакторный вход отключён', 'var(--dot-warn)'))
                }
              >
                Отключить
              </button>
            )}
          </Actions>
        </>
      )}
    </Card>
  );
}

/**
 * Уведомления на почту. Переключатели сохраняются сразу: отдельная кнопка
 * «Сохранить» для трёх флажков — лишний шаг, о котором забывают.
 */
function NotificationsCard({ onFlash }: { onFlash: (text: string, color: string) => void }) {
  const { user, refresh, can } = useAuth();
  const [saving, setSaving] = useState<string | null>(null);

  if (!user) return null;
  const prefs = user.notifications;

  const toggle = async (key: (typeof NOTIFICATIONS)[number]['key']) => {
    setSaving(key);
    try {
      await api('/api/auth/notifications', {
        method: 'PATCH',
        body: JSON.stringify({ [key]: !prefs[key] }),
      });
      refresh();
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Не удалось сохранить настройку', 'var(--dot-err)');
    } finally {
      setSaving(null);
    }
  };

  return (
    <Card title="Уведомления на почту">
      {!prefs.mail_configured && (
        <Warn>
          Почта не настроена — письма не отправляются, какие бы переключатели ни стояли. Настройки
          SMTP задаёт администратор сервера.
        </Warn>
      )}

      <div style={{ opacity: prefs.mail_configured ? 1 : 0.6 }}>
        {NOTIFICATIONS.map((n) => {
          const on = prefs[n.key];
          const id = `notify-${n.key}`;
          return (
            <div key={n.key} className="toggle-row">
              <label htmlFor={id} style={{ cursor: 'pointer' }}>
                {n.label}
              </label>
              <button
                id={id}
                type="button"
                role="switch"
                aria-checked={on}
                className="toggle"
                disabled={saving !== null}
                onClick={() => toggle(n.key)}
              />
            </div>
          );
        })}
      </div>

      <p className="caption" style={{ margin: 0 }}>
        Напоминание уходит тому, у кого заявка стоит, одним списком в день. Сводка — по понедельникам
        тем, кто видит отчёты. Те же сообщения приходят в Telegram, если он подключён.
      </p>

      {can('manage_reference') && <MailCheck onFlash={onFlash} />}
    </Card>
  );
}

/**
 * Уведомления в Telegram. Привязка идёт через самого бота: панель выдаёт
 * одноразовую ссылку, человек открывает её, бот присылает нам id чата.
 * Так никому не нужно знать и вводить внутренние идентификаторы.
 */
function TelegramCard({ onFlash }: { onFlash: (text: string, color: string) => void }) {
  const { can } = useAuth();
  const [waiting, setWaiting] = useState(false);
  const status = useTelegramStatus(waiting);
  const link = useTelegramLink();
  const unlink = useTelegramUnlink();

  const linked = status.data?.linked ?? false;

  // Привязка происходит на стороне Telegram: пока человек ходит по ссылке,
  // панель опрашивает статус и сама гасит ожидание, когда чат подключился.
  useEffect(() => {
    if (waiting && linked) {
      setWaiting(false);
      onFlash('Telegram подключён', 'var(--dot-ok)');
    }
  }, [waiting, linked, onFlash]);

  const connect = async () => {
    try {
      const data = await link.mutateAsync();
      setWaiting(true);
      window.open(data.url, '_blank', 'noopener');
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Не удалось получить ссылку', 'var(--dot-err)');
    }
  };

  const disconnect = async () => {
    try {
      await unlink.mutateAsync();
      setWaiting(false);
      onFlash('Уведомления в Telegram отключены', 'var(--dot-off)');
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Не удалось отключить', 'var(--dot-err)');
    }
  };

  return (
    <Card title="Уведомления в Telegram">
      <p className="caption" style={{ margin: 0 }}>
        Бот пишет автору заявки на каждом шаге: согласование покупки, оценка закупа, решение по
        сумме, выплата. Тем, к кому заявка пришла, — что она у них.
      </p>

      {!status.data?.configured ? (
        <Warn>
          Бот не настроен — уведомления не отправляются. Токен бота (TELEGRAM_BOT_TOKEN) задаёт
          администратор сервера.
        </Warn>
      ) : linked ? (
        <>
          <Status on text={`Подключено${status.data?.username ? ` · @${status.data.username}` : ''}`} />
          <Actions>
            <button type="button" className="btn btn-secondary" disabled={unlink.isPending} onClick={disconnect}>
              {unlink.isPending ? 'Отключаем…' : 'Отключить'}
            </button>
          </Actions>
        </>
      ) : (
        <>
          <Actions>
            <button type="button" className="btn btn-primary" disabled={link.isPending} onClick={connect}>
              {link.isPending ? 'Готовим ссылку…' : 'Подключить Telegram'}
            </button>
          </Actions>
          {waiting && (
            <p className="caption" style={{ margin: 0 }}>
              Откройте бота и нажмите «Старт». Ссылка одноразовая и живёт полчаса — если не успели,
              нажмите «Подключить» ещё раз.
              {link.data ? (
                <>
                  {' '}
                  <a href={link.data.url} target="_blank" rel="noopener noreferrer">
                    Открыть бота
                  </a>
                </>
              ) : null}
            </p>
          )}
        </>
      )}

      {can('manage_reference') && <WebhookSetup onFlash={onFlash} />}
    </Card>
  );
}

/**
 * Фоновые задачи. Администратору важно видеть, что рассылка вообще
 * происходит, и уметь запустить её сейчас: ждать девяти утра, чтобы
 * проверить настройку почты и бота, неразумно.
 */
function JobsCard({ onFlash }: { onFlash: (text: string, color: string) => void }) {
  const { can } = useAuth();
  const allowed = can('manage_reference');
  const runs = useJobRuns(allowed);
  const run = useRunJob();
  const health = useHealth();

  if (!allowed) return null;

  const start = async (job: string) => {
    try {
      const result = await run.mutateAsync(job);
      onFlash(`${result.label}: ${result.details}`, 'var(--dot-ok)');
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Задача не выполнена', 'var(--dot-err)');
    }
  };

  const TONE: Record<string, string> = {
    DONE: 'var(--dot-ok)',
    RUNNING: 'var(--dot-warn)',
    FAILED: 'var(--dot-err)',
    SKIPPED: 'var(--dot-off)',
  };

  return (
    <Card title="Фоновые задачи">
      <p className="caption" style={{ margin: 0 }}>
        Напоминания и недельная сводка уходят сами. Кнопки ниже запускают задачу сейчас — так
        проверяют, что почта и бот настроены.
      </p>

      <Actions>
        <button type="button" className="btn btn-secondary" disabled={run.isPending} onClick={() => start('stale_requests')}>
          Разослать напоминания сейчас
        </button>
        <button type="button" className="btn btn-secondary" disabled={run.isPending} onClick={() => start('weekly_budget')}>
          Отправить недельную сводку сейчас
        </button>
      </Actions>

      {runs.data && runs.data.length > 0 && (
        <div>
          <div className="label" style={{ marginBottom: 8 }}>
            Последние запуски
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid' }}>
            {runs.data.slice(0, 6).map((item) => (
              <li
                key={item.id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '6px 1fr',
                  columnGap: 8,
                  alignItems: 'start',
                  padding: '8px 0',
                  borderBottom: '1px solid var(--line)',
                }}
              >
                <span className="dot" style={{ ['--dot' as string]: TONE[item.status] ?? 'var(--dot-off)', marginTop: 7 }} aria-hidden="true" />
                <div style={{ minWidth: 0 }}>
                  <div className="small">{item.label}</div>
                  <div className="meta">
                    {formatDateTime(item.started_at, health.data?.timezone)}
                    {item.details ? ` · ${item.details}` : ''}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {runs.data && runs.data.length === 0 && (
        <p className="caption" style={{ margin: 0 }}>
          Задачи ещё не запускались: первая рассылка уйдёт в ближайшие назначенные часы.
        </p>
      )}
    </Card>
  );
}

/**
 * Установка вебхука. Пока Telegram не знает адрес сервера, бот не получит
 * ни одного «Старт», и привязка не сработает ни у кого. Кнопка нужна и
 * после смены SECRET_KEY или адреса панели: адрес вебхука зависит от них.
 */
function WebhookSetup({ onFlash }: { onFlash: (text: string, color: string) => void }) {
  const setup = useTelegramSetup();

  const run = async () => {
    try {
      await setup.mutateAsync();
      onFlash('Telegram теперь знает адрес сервера', 'var(--dot-ok)');
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Не удалось настроить вебхук', 'var(--dot-err)');
    }
  };

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <Actions>
        <button type="button" className="btn btn-secondary" disabled={setup.isPending} onClick={run}>
          {setup.isPending ? 'Настраиваем…' : 'Настроить бота на этот сервер'}
        </button>
      </Actions>
      <p className="caption" style={{ margin: 0 }}>
        Нажимается один раз после запуска и после смены адреса панели или SECRET_KEY: Telegram
        запоминает, куда слать сообщения боту.
      </p>
    </div>
  );
}

/**
 * Проверка настроек почты. Письмо приходит самому администратору,
 * а ошибка SMTP показывается с причиной — иначе непонятно, почему
 * уведомления не доходят.
 */
function MailCheck({ onFlash }: { onFlash: (text: string, color: string) => void }) {
  const [busy, setBusy] = useState(false);

  const check = async () => {
    setBusy(true);
    try {
      await api('/api/mail/test', { method: 'POST' });
      onFlash('Проверочное письмо отправлено вам на почту', 'var(--dot-ok)');
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Не удалось отправить письмо', 'var(--dot-err)');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Actions>
      <button type="button" className="btn btn-secondary" disabled={busy} onClick={check}>
        {busy ? 'Отправляем…' : 'Отправить проверочное письмо'}
      </button>
    </Actions>
  );
}

/**
 * Установка панели на экран телефона. Три ситуации:
 *  - уже открыто как приложение — сказать об этом;
 *  - браузер умеет ставить сам (Chrome на Android, Edge) — кнопка;
 *  - iPhone — только через «Поделиться → На экран «Домой»», кнопки у
 *    Safari нет, поэтому объясняем словами.
 */
function InstallCard({ onFlash }: { onFlash: (text: string, color: string) => void }) {
  const state = useSyncExternalStore(subscribeInstall, getInstallState, getInstallState);
  const [busy, setBusy] = useState(false);

  const install = async () => {
    setBusy(true);
    try {
      const accepted = await promptInstall();
      if (accepted) onFlash('Панель добавлена на экран', 'var(--dot-ok)');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Приложение на телефоне">
      {state.standalone ? (
        <>
          <Status on text="Открыто как приложение" />
          <p className="caption" style={{ margin: 0 }}>
            Панель стоит на экране телефона и обновляется сама вместе с сервером. При обрыве связи
            она покажет заглушку, а не ошибку браузера.
          </p>
        </>
      ) : (
        <>
          <p className="caption" style={{ margin: 0 }}>
            Панель можно поставить на экран телефона как обычное приложение: своя иконка, без
            адресной строки, открывается одним нажатием. Ярлык «Новая заявка» ведёт сразу в форму.
          </p>
          {state.canPrompt ? (
            <Actions>
              <button type="button" className="btn btn-primary" onClick={install} disabled={busy}>
                {busy ? 'Ждём ответа…' : 'Установить на экран'}
              </button>
            </Actions>
          ) : state.ios ? (
            <ol className="caption" style={{ margin: 0, paddingLeft: 20 }}>
              <li>Откройте панель в Safari.</li>
              <li>Нажмите «Поделиться» — квадрат со стрелкой вверх.</li>
              <li>Выберите «На экран «Домой»» и подтвердите.</li>
            </ol>
          ) : (
            <p className="caption" style={{ margin: 0 }}>
              В Chrome и Edge на компьютере команда «Установить HONA ORDER» есть в меню браузера и в
              адресной строке. На телефоне откройте этот раздел в Chrome (Android) или Safari
              (iPhone).
            </p>
          )}
        </>
      )}
    </Card>
  );
}

/**
 * Уведомления на телефон (Web Push). Подписка живёт в браузере, сервер
 * лишь запоминает её, поэтому состояние «включено» проверяется у
 * браузера, а не по данным сервера: с сервера видно только число
 * устройств. На iPhone работает только у панели, поставленной на экран.
 */
function PushCard({ onFlash }: { onFlash: (text: string, color: string) => void }) {
  const config = usePushConfig();
  const subscribe = usePushSubscribe();
  const unsubscribe = usePushUnsubscribe();
  const test = usePushTest();
  const support = pushSupport();
  const [onDevice, setOnDevice] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  // Есть ли подписка именно у этого браузера — узнаём у service worker.
  useEffect(() => {
    let cancelled = false;
    if (support !== 'ok') {
      setOnDevice(false);
      return;
    }
    currentPushSubscription()
      .then((sub) => {
        if (!cancelled) setOnDevice(sub !== null);
      })
      .catch(() => {
        if (!cancelled) setOnDevice(false);
      });
    return () => {
      cancelled = true;
    };
  }, [support]);

  const enable = async () => {
    const key = config.data?.public_key;
    if (!key) return;
    setBusy(true);
    try {
      const sub = await subscribePush(key);
      if (!sub) {
        onFlash('Браузер не дал разрешения на уведомления', 'var(--dot-warn)');
        return;
      }
      await subscribe.mutateAsync(subscriptionPayload(sub));
      setOnDevice(true);
      onFlash('Уведомления на этом устройстве включены', 'var(--dot-ok)');
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Не удалось включить', 'var(--dot-err)');
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      const endpoint = await unsubscribePush();
      if (endpoint) await unsubscribe.mutateAsync(endpoint);
      setOnDevice(false);
      onFlash('Уведомления на этом устройстве отключены', 'var(--dot-off)');
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Не удалось отключить', 'var(--dot-err)');
    } finally {
      setBusy(false);
    }
  };

  const check = async () => {
    try {
      await test.mutateAsync();
      onFlash('Проверочное уведомление отправлено', 'var(--dot-ok)');
    } catch (err) {
      onFlash(err instanceof Error ? err.message : 'Не удалось отправить', 'var(--dot-err)');
    }
  };

  const devices = config.data?.devices ?? 0;
  const denied = pushPermission() === 'denied';

  let body: JSX.Element;
  if (config.data && !config.data.enabled) {
    body = (
      <Warn>
        Push не настроен — уведомления на телефон не отправляются. Ключ (VAPID_PRIVATE_KEY) задаёт
        администратор сервера.
      </Warn>
    );
  } else if (support === 'unsupported') {
    body = (
      <p className="caption" style={{ margin: 0 }}>
        Этот браузер уведомления не поддерживает. Откройте панель в Chrome (Android) или поставьте
        её на экран iPhone.
      </p>
    );
  } else if (support === 'ios-needs-install') {
    body = (
      <p className="caption" style={{ margin: 0 }}>
        На iPhone уведомления приходят только в панель, поставленную на экран: сначала «Поделиться
        → На экран «Домой»» (карточка выше), затем включите их здесь уже из установленного
        приложения.
      </p>
    );
  } else if (onDevice) {
    body = (
      <>
        <Status on text={`Включены на этом устройстве${devices > 1 ? ` · всего устройств: ${devices}` : ''}`} />
        <Actions>
          <button type="button" className="btn btn-secondary" disabled={test.isPending} onClick={check}>
            {test.isPending ? 'Отправляем…' : 'Проверить'}
          </button>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={disable}>
            {busy ? 'Отключаем…' : 'Отключить'}
          </button>
        </Actions>
      </>
    );
  } else if (denied) {
    body = (
      <Warn>
        Уведомления для панели запрещены в настройках браузера. Разрешите их в настройках сайта и
        вернитесь сюда.
      </Warn>
    );
  } else {
    body = (
      <>
        <Actions>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || onDevice === null || !config.data}
            onClick={enable}
          >
            {busy ? 'Включаем…' : 'Включить уведомления'}
          </button>
        </Actions>
        {devices > 0 && (
          <p className="caption" style={{ margin: 0 }}>
            Уже включены на других устройствах: {devices}.
          </p>
        )}
      </>
    );
  }

  return (
    <Card title="Уведомления на телефоне">
      <p className="caption" style={{ margin: 0 }}>
        Те же сообщения, что в Telegram и на почту, — прямо на экран телефона: судьба ваших
        заявок, заявки, которые ждут вас, напоминания и недельная сводка.
      </p>
      {body}
    </Card>
  );
}

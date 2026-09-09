import { useEffect, useState, useSyncExternalStore } from 'react';
import { Icon } from '@/components/Icon';
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
import { VARIANTS } from '@/shell/config';
import type { ShellVariant, Theme } from '@/shell/config';
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
  const { theme, setTheme, variant, setVariant, flash } = useShell();
  const { user } = useAuth();
  const health = useHealth();

  return (
    <>
      <PageHeader
        title="Параметры"
        lead="Профиль согласующего, оформление панели и уведомления"
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 'var(--gap)',
        }}
      >
        <section className="card">
          <div className="label">ПРОФИЛЬ</div>
          <dl style={{ display: 'grid', gap: 16, margin: '16px 0 0' }}>
            <div>
              <dt className="caption">Имя и фамилия</dt>
              <dd style={{ margin: '2px 0 0', fontWeight: 600 }}>{user?.full_name}</dd>
            </div>
            <div>
              <dt className="caption">Должность</dt>
              <dd style={{ margin: '2px 0 0' }}>{user?.position || '—'}</dd>
            </div>
            <div>
              <dt className="caption">Рабочая почта</dt>
              <dd className="num" style={{ margin: '2px 0 0' }}>{user?.email ?? '—'}</dd>
            </div>
            <div>
              <dt className="caption">Роль</dt>
              <dd style={{ margin: '2px 0 0' }}>
                {user ? (ROLE_LABEL[user.role] ?? user.role) : '—'}
              </dd>
            </div>
          </dl>
          <p className="caption" style={{ margin: '16px 0 0' }}>
            Имя, должность и роль меняет администратор системы.
          </p>
        </section>

        <PasswordCard onDone={() => flash('Пароль изменён', 'var(--dot-ok)')} />

        <TwoFactorCard onFlash={flash} />

        <section className="card">
          <div className="label">ТЕМА ОФОРМЛЕНИЯ</div>
          <div
            role="radiogroup"
            aria-label="Тема оформления"
            style={{ display: 'grid', gap: 8, marginTop: 16 }}
          >
            {(
              [
                ['light', 'Светлая'],
                ['dark', 'Тёмная'],
              ] as [Theme, string][]
            ).map(([value, label]) => (
              <SquareRadio
                key={value}
                label={label}
                active={theme === value}
                onSelect={() => setTheme(value)}
              />
            ))}
          </div>

          <div className="label" style={{ marginTop: 24 }}>
            ВАРИАНТ ПАНЕЛИ
          </div>
          <div
            role="radiogroup"
            aria-label="Вариант панели"
            style={{ display: 'grid', gap: 8, marginTop: 16 }}
          >
            {(Object.keys(VARIANTS) as ShellVariant[]).map((v) => (
              <SquareRadio
                key={v}
                label={VARIANTS[v].label}
                active={variant === v}
                onSelect={() => setVariant(v)}
              />
            ))}
          </div>
        </section>

        <NotificationsCard onFlash={flash} />
        <TelegramCard onFlash={flash} />
        <InstallCard onFlash={flash} />
        <PushCard onFlash={flash} />
        <JobsCard onFlash={flash} />
        <section className="card">
          <div className="label">О СИСТЕМЕ</div>
          <dl style={{ display: 'grid', gap: 12, marginTop: 16, margin: '16px 0 0' }}>
            <div>
              <dt className="caption">Часовой пояс расчётов</dt>
              <dd className="num" style={{ margin: '2px 0 0' }}>
                {health.data?.timezone ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="caption">Состояние базы</dt>
              <dd className="num" style={{ margin: '2px 0 0' }}>
                {health.data?.database === 'ok' ? 'Доступна' : 'Недоступна'}
              </dd>
            </div>
            <div>
              <dt className="caption">Версия схемы</dt>
              <dd className="num" style={{ margin: '2px 0 0' }}>
                {health.data?.db_revision ?? '—'}
              </dd>
            </div>
          </dl>
        </section>
      </div>
    </>
  );
}

function SquareRadio({
  label,
  active,
  onSelect,
}: {
  label: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onSelect}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        minHeight: 44,
        padding: '0 12px',
        border: active ? '2px solid var(--green)' : '1px solid var(--grey)',
        borderRadius: 'var(--r-field)',
        background: active ? 'var(--mist)' : 'transparent',
        textAlign: 'left',
        cursor: 'pointer',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 18,
          height: 18,
          flex: 'none',
          display: 'grid',
          placeItems: 'center',
          border: active ? '2px solid var(--green)' : '1px solid var(--grey)',
        }}
      >
        <span
          style={{ width: 10, height: 10, background: active ? 'var(--green)' : 'transparent' }}
        />
      </span>
      <span style={{ fontWeight: 600 }}>{label}</span>
    </button>
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
    <section className="card">
      <div className="label">СМЕНА ПАРОЛЯ</div>
      <form onSubmit={submit} style={{ display: 'grid', gap: 16, marginTop: 16 }}>
        <label>
          <div className="caption" style={{ marginBottom: 4 }}>
            Текущий пароль
          </div>
          <input
            className="field"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
        <label>
          <div className="caption" style={{ marginBottom: 4 }}>
            Новый пароль
          </div>
          <input
            className={`field${error ? ' field-error' : ''}`}
            type="password"
            autoComplete="new-password"
            required
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </label>
        <label>
          <div className="caption" style={{ marginBottom: 4 }}>
            Повторите новый пароль
          </div>
          <input
            className={`field${error ? ' field-error' : ''}`}
            type="password"
            autoComplete="new-password"
            required
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
          />
        </label>
        {error && (
          <div className="field-error-text" role="alert">
            {error}
          </div>
        )}
        <p className="caption" style={{ margin: 0 }}>
          Возьмите фразу от десяти символов: длинную проще запомнить и труднее
          подобрать.
        </p>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={saving || !current || !next || !repeat}
        >
          {saving ? 'Сохраняем…' : 'Сменить пароль'}
        </button>
      </form>
    </section>
  );
}

/**
 * Второй фактор: включение, перевыпуск кодов восстановления, отключение.
 * Ролям, которым он обязателен, отключение недоступно.
 */
function TwoFactorCard({
  onFlash,
}: {
  onFlash: (text: string, color: string) => void;
}) {
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
      <section className="card">
        <div className="label">ДВУХФАКТОРНЫЙ ВХОД</div>
        <div style={{ marginTop: 16 }}>
          <TotpSetup
            onCancel={() => setMode('idle')}
            onDone={() => {
              setMode('idle');
              refresh();
              onFlash('Двухфакторный вход включён', 'var(--dot-ok)');
            }}
          />
        </div>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="label">ДВУХФАКТОРНЫЙ ВХОД</div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
        <span
          aria-hidden="true"
          style={{
            width: 8,
            height: 8,
            background: user.two_factor_enabled ? 'var(--dot-ok)' : 'var(--dot-off)',
          }}
        />
        <span style={{ fontWeight: 600 }}>
          {user.two_factor_enabled ? 'Включён' : 'Выключен'}
        </span>
      </div>

      <p className="caption" style={{ margin: '8px 0 0' }}>
        {user.two_factor_enabled
          ? `Кодов восстановления осталось: ${user.recovery_codes_left}.`
          : 'Пароль можно подсмотреть или подобрать. Код из приложения на телефоне закрывает вход, даже если пароль стал известен.'}
        {user.two_factor_required && ' Для вашей роли он обязателен.'}
      </p>

      {!user.two_factor_enabled && (
        <button
          type="button"
          className="btn btn-primary"
          style={{ marginTop: 24 }}
          onClick={() => setMode('setup')}
        >
          Включить
        </button>
      )}

      {user.two_factor_enabled && (
        <>
          <label style={{ display: 'block', marginTop: 24 }}>
            <div className="caption" style={{ marginBottom: 4 }}>
              Подтвердите паролем
            </div>
            <input
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
          </label>
          {error && (
            <div className="field-error-text" role="alert">
              {error}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy || !password}
              onClick={() =>
                act('/api/auth/2fa/recovery-codes', (data) =>
                  setCodes(data.codes ?? []),
                )
              }
            >
              Новые коды восстановления
            </button>
            {!user.two_factor_required && (
              <button
                type="button"
                className="btn btn-danger"
                disabled={busy || !password}
                onClick={() =>
                  act('/api/auth/2fa/disable', () =>
                    onFlash('Двухфакторный вход отключён', 'var(--dot-warn)'),
                  )
                }
              >
                Отключить
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}

/**
 * Уведомления на почту. Переключатели сохраняются сразу: отдельная кнопка
 * «Сохранить» для трёх флажков — лишний шаг, о котором забывают.
 */
function NotificationsCard({
  onFlash,
}: {
  onFlash: (text: string, color: string) => void;
}) {
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
      onFlash(
        err instanceof Error ? err.message : 'Не удалось сохранить настройку',
        'var(--dot-err)',
      );
    } finally {
      setSaving(null);
    }
  };

  return (
    <section className="card">
      <div className="label">УВЕДОМЛЕНИЯ НА ПОЧТУ</div>

      {!prefs.mail_configured && (
        <p className="caption" style={{ margin: '16px 0 0', color: 'var(--dot-warn)' }}>
          Почта не настроена — письма не отправляются, какие бы переключатели ни
          стояли. Настройки SMTP задаёт администратор сервера.
        </p>
      )}

      <div style={{ display: 'grid', marginTop: 16 }}>
        {NOTIFICATIONS.map((n) => {
          const on = prefs[n.key];
          return (
            <button
              key={n.key}
              type="button"
              role="checkbox"
              aria-checked={on}
              disabled={saving !== null}
              onClick={() => toggle(n.key)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                minHeight: 44,
                padding: '0 4px',
                border: 'none',
                background: 'transparent',
                textAlign: 'left',
                cursor: saving ? 'progress' : 'pointer',
                opacity: prefs.mail_configured ? 1 : 0.6,
              }}
            >
              {/* Тумблеры-«таблетки» брендбук запрещает — только квадратный чекбокс. */}
              <span
                aria-hidden="true"
                style={{
                  width: 20,
                  height: 20,
                  flex: 'none',
                  display: 'grid',
                  placeItems: 'center',
                  borderRadius: 'var(--r-field)',
                  border: on ? '1px solid var(--green)' : '1px solid var(--grey)',
                  background: on ? 'var(--green)' : 'transparent',
                  color: '#FFFFFF',
                }}
              >
                <Icon name="ti-check" size={14} style={{ opacity: on ? 1 : 0 }} />
              </span>
              {n.label}
            </button>
          );
        })}
      </div>

      <p className="caption" style={{ margin: '16px 0 0' }}>
        Напоминание уходит тому, у кого заявка стоит, одним списком в день.
        Сводка — по понедельникам тем, кто видит отчёты. Те же сообщения
        приходят в Telegram, если он подключён.
      </p>

      {can('manage_reference') && <MailCheck onFlash={onFlash} />}
    </section>
  );
}


/**
 * Уведомления в Telegram. Привязка идёт через самого бота: панель выдаёт
 * одноразовую ссылку, человек открывает её, бот присылает нам id чата.
 * Так никому не нужно знать и вводить внутренние идентификаторы.
 */
function TelegramCard({
  onFlash,
}: {
  onFlash: (text: string, color: string) => void;
}) {
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
      onFlash(
        err instanceof Error ? err.message : 'Не удалось получить ссылку',
        'var(--dot-err)',
      );
    }
  };

  const disconnect = async () => {
    try {
      await unlink.mutateAsync();
      setWaiting(false);
      onFlash('Уведомления в Telegram отключены', 'var(--dot-off)');
    } catch (err) {
      onFlash(
        err instanceof Error ? err.message : 'Не удалось отключить',
        'var(--dot-err)',
      );
    }
  };

  return (
    <section className="card">
      <div className="label">УВЕДОМЛЕНИЯ В TELEGRAM</div>

      <p className="caption" style={{ margin: '16px 0 0' }}>
        Бот пишет автору заявки на каждом шаге: согласование покупки, оценка
        закупа, решение по сумме, выплата. Тем, к кому заявка пришла, — что она
        у них.
      </p>

      {!status.data?.configured ? (
        <p className="caption" style={{ margin: '16px 0 0', color: 'var(--dot-warn)' }}>
          Бот не настроен — уведомления не отправляются. Токен бота
          (TELEGRAM_BOT_TOKEN) задаёт администратор сервера.
        </p>
      ) : linked ? (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              minHeight: 44,
              marginTop: 8,
            }}
          >
            <span
              aria-hidden="true"
              style={{ width: 8, height: 8, background: 'var(--dot-ok)' }}
            />
            <span style={{ fontWeight: 600 }}>
              Подключено
              {status.data?.username ? ` · @${status.data.username}` : ''}
            </span>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={unlink.isPending}
            onClick={disconnect}
          >
            {unlink.isPending ? 'Отключаем…' : 'Отключить'}
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            className="btn btn-primary"
            style={{ marginTop: 16 }}
            disabled={link.isPending}
            onClick={connect}
          >
            {link.isPending ? 'Готовим ссылку…' : 'Подключить Telegram'}
          </button>
          {waiting && (
            <p className="caption" style={{ margin: '12px 0 0' }}>
              Откройте бота и нажмите «Старт». Ссылка одноразовая и живёт
              полчаса — если не успели, нажмите «Подключить» ещё раз.
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
    </section>
  );
}

/**
 * Фоновые задачи. Администратору важно видеть, что рассылка вообще
 * происходит, и уметь запустить её сейчас: ждать девяти утра, чтобы
 * проверить настройку почты и бота, неразумно.
 */
function JobsCard({
  onFlash,
}: {
  onFlash: (text: string, color: string) => void;
}) {
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
      onFlash(
        err instanceof Error ? err.message : 'Задача не выполнена',
        'var(--dot-err)',
      );
    }
  };

  const TONE: Record<string, string> = {
    DONE: 'var(--dot-ok)',
    RUNNING: 'var(--dot-warn)',
    FAILED: 'var(--dot-err)',
    SKIPPED: 'var(--dot-off)',
  };

  return (
    <section className="card">
      <div className="label">ФОНОВЫЕ ЗАДАЧИ</div>

      <p className="caption" style={{ margin: '16px 0 0' }}>
        Напоминания и недельная сводка уходят сами. Кнопки ниже запускают
        задачу сейчас — так проверяют, что почта и бот настроены.
      </p>

      <div style={{ display: 'grid', gap: 8, marginTop: 16 }}>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={run.isPending}
          onClick={() => start('stale_requests')}
        >
          Разослать напоминания сейчас
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={run.isPending}
          onClick={() => start('weekly_budget')}
        >
          Отправить недельную сводку сейчас
        </button>
      </div>

      {runs.data && runs.data.length > 0 && (
        <table style={{ marginTop: 16, width: '100%' }}>
          <tbody>
            {runs.data.slice(0, 6).map((item) => (
              <tr key={item.id}>
                <td style={{ padding: '6px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      aria-hidden="true"
                      style={{
                        width: 8,
                        height: 8,
                        flex: 'none',
                        background: TONE[item.status] ?? 'var(--dot-off)',
                      }}
                    />
                    <span>{item.label}</span>
                  </div>
                  <div className="caption" style={{ paddingLeft: 16 }}>
                    {formatDateTime(item.started_at, health.data?.timezone)}
                    {item.details ? ` · ${item.details}` : ''}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {runs.data && runs.data.length === 0 && (
        <p className="caption" style={{ margin: '16px 0 0' }}>
          Задачи ещё не запускались: первая рассылка уйдёт в ближайшие
          назначенные часы.
        </p>
      )}
    </section>
  );
}

/**
 * Установка вебхука. Пока Telegram не знает адрес сервера, бот не получит
 * ни одного «Старт», и привязка не сработает ни у кого. Кнопка нужна и
 * после смены SECRET_KEY или адреса панели: адрес вебхука зависит от них.
 */
function WebhookSetup({
  onFlash,
}: {
  onFlash: (text: string, color: string) => void;
}) {
  const setup = useTelegramSetup();

  const run = async () => {
    try {
      await setup.mutateAsync();
      onFlash('Telegram теперь знает адрес сервера', 'var(--dot-ok)');
    } catch (err) {
      onFlash(
        err instanceof Error ? err.message : 'Не удалось настроить вебхук',
        'var(--dot-err)',
      );
    }
  };

  return (
    <>
      <button
        type="button"
        className="btn btn-secondary"
        style={{ marginTop: 16 }}
        disabled={setup.isPending}
        onClick={run}
      >
        {setup.isPending ? 'Настраиваем…' : 'Настроить бота на этот сервер'}
      </button>
      <p className="caption" style={{ margin: '8px 0 0' }}>
        Нажимается один раз после запуска и после смены адреса панели или
        SECRET_KEY: Telegram запоминает, куда слать сообщения боту.
      </p>
    </>
  );
}

/**
 * Проверка настроек почты. Письмо приходит самому администратору,
 * а ошибка SMTP показывается с причиной — иначе непонятно, почему
 * уведомления не доходят.
 */
function MailCheck({
  onFlash,
}: {
  onFlash: (text: string, color: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  const check = async () => {
    setBusy(true);
    try {
      await api('/api/mail/test', { method: 'POST' });
      onFlash('Проверочное письмо отправлено вам на почту', 'var(--dot-ok)');
    } catch (err) {
      onFlash(
        err instanceof Error ? err.message : 'Не удалось отправить письмо',
        'var(--dot-err)',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      className="btn btn-secondary"
      style={{ marginTop: 16 }}
      disabled={busy}
      onClick={check}
    >
      {busy ? 'Отправляем…' : 'Отправить проверочное письмо'}
    </button>
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
    <section className="card">
      <div className="label">ПРИЛОЖЕНИЕ НА ТЕЛЕФОНЕ</div>
      {state.standalone ? (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 }}>
            <span aria-hidden="true" style={{ width: 8, height: 8, background: 'var(--dot-ok)' }} />
            <b>Открыто как приложение</b>
          </div>
          <p className="caption" style={{ margin: '12px 0 0' }}>
            Панель стоит на экране телефона и обновляется сама вместе с сервером. При обрыве
            связи она покажет заглушку, а не ошибку браузера.
          </p>
        </>
      ) : (
        <>
          <p className="caption" style={{ margin: '12px 0 0' }}>
            Панель можно поставить на экран телефона как обычное приложение: своя иконка, без
            адресной строки, открывается одним нажатием. Ярлык «Новая заявка» ведёт сразу в форму.
          </p>
          {state.canPrompt ? (
            <button
              type="button"
              className="btn btn-primary"
              style={{ marginTop: 16 }}
              onClick={install}
              disabled={busy}
            >
              {busy ? 'Ждём ответа…' : 'Установить на экран'}
            </button>
          ) : state.ios ? (
            <ol className="caption" style={{ margin: '12px 0 0', paddingLeft: 20 }}>
              <li>Откройте панель в Safari.</li>
              <li>Нажмите «Поделиться» — квадрат со стрелкой вверх.</li>
              <li>Выберите «На экран «Домой»» и подтвердите.</li>
            </ol>
          ) : (
            <p className="caption" style={{ margin: '12px 0 0' }}>
              В Chrome и Edge на компьютере команда «Установить HONA ORDER» есть в меню браузера
              и в адресной строке. На телефоне откройте этот раздел в Chrome (Android) или Safari
              (iPhone).
            </p>
          )}
        </>
      )}
    </section>
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
      <p className="caption" style={{ margin: '16px 0 0', color: 'var(--dot-warn)' }}>
        Push не настроен — уведомления на телефон не отправляются. Ключ
        (VAPID_PRIVATE_KEY) задаёт администратор сервера.
      </p>
    );
  } else if (support === 'unsupported') {
    body = (
      <p className="caption" style={{ margin: '16px 0 0' }}>
        Этот браузер уведомления не поддерживает. Откройте панель в Chrome
        (Android) или поставьте её на экран iPhone.
      </p>
    );
  } else if (support === 'ios-needs-install') {
    body = (
      <p className="caption" style={{ margin: '16px 0 0' }}>
        На iPhone уведомления приходят только в панель, поставленную на экран:
        сначала «Поделиться → На экран «Домой»» (карточка выше), затем
        включите их здесь уже из установленного приложения.
      </p>
    );
  } else if (onDevice) {
    body = (
      <>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minHeight: 44, marginTop: 8 }}>
          <span aria-hidden="true" style={{ width: 8, height: 8, background: 'var(--dot-ok)' }} />
          <span style={{ fontWeight: 600 }}>
            Включены на этом устройстве
            {devices > 1 ? ` · всего устройств: ${devices}` : ''}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={test.isPending}
            onClick={check}
          >
            {test.isPending ? 'Отправляем…' : 'Проверить'}
          </button>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={disable}>
            {busy ? 'Отключаем…' : 'Отключить'}
          </button>
        </div>
      </>
    );
  } else if (denied) {
    body = (
      <p className="caption" style={{ margin: '16px 0 0', color: 'var(--dot-warn)' }}>
        Уведомления для панели запрещены в настройках браузера. Разрешите их
        в настройках сайта и вернитесь сюда.
      </p>
    );
  } else {
    body = (
      <>
        <button
          type="button"
          className="btn btn-primary"
          style={{ marginTop: 16 }}
          disabled={busy || onDevice === null || !config.data}
          onClick={enable}
        >
          {busy ? 'Включаем…' : 'Включить уведомления'}
        </button>
        {devices > 0 && (
          <p className="caption" style={{ margin: '12px 0 0' }}>
            Уже включены на других устройствах: {devices}.
          </p>
        )}
      </>
    );
  }

  return (
    <section className="card">
      <div className="label">УВЕДОМЛЕНИЯ НА ТЕЛЕФОНЕ</div>
      <p className="caption" style={{ margin: '16px 0 0' }}>
        Те же сообщения, что в Telegram и на почту, — прямо на экран
        телефона: судьба ваших заявок, заявки, которые ждут вас, напоминания
        и недельная сводка.
      </p>
      {body}
    </section>
  );
}

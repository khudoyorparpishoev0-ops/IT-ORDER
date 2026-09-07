import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { useHealth } from '@/api/hooks';
import { useAuth } from '@/api/auth';
import { api } from '@/api/client';
import { ROLE_LABEL } from '@/shell/config';

const NOTIFICATIONS = [
  { label: 'Новые заявки на утверждение', on: true },
  { label: 'Напоминание о заявках старше 3 дней', on: true },
  { label: 'Еженедельный отчёт по бюджету', on: false },
];
import { VARIANTS } from '@/shell/config';
import type { ShellVariant, Theme } from '@/shell/config';
import { useShell } from '@/shell/ShellContext';

export function Settings() {
  const { theme, setTheme, variant, setVariant, flash } = useShell();
  const { user } = useAuth();
  const health = useHealth();
  const [toggles, setToggles] = useState(NOTIFICATIONS.map((n) => n.on));

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

        <section className="card">
          <div className="label">УВЕДОМЛЕНИЯ</div>
          <div style={{ display: 'grid', marginTop: 16 }}>
            {NOTIFICATIONS.map((n, i) => (
              <button
                key={n.label}
                type="button"
                role="checkbox"
                aria-checked={toggles[i]}
                onClick={() =>
                  setToggles((prev) => prev.map((v, j) => (j === i ? !v : v)))
                }
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
                    border: toggles[i] ? '1px solid var(--green)' : '1px solid var(--grey)',
                    background: toggles[i] ? 'var(--green)' : 'transparent',
                    color: '#FFFFFF',
                  }}
                >
                  <Icon name="ti-check" size={14} style={{ opacity: toggles[i] ? 1 : 0 }} />
                </span>
                {n.label}
              </button>
            ))}
          </div>
        </section>
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

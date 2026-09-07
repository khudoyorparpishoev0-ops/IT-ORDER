import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { useHealth } from '@/api/hooks';

/** Профиль до фазы 3 не редактируется на сервере: вход ещё не сделан. */
const PROFILE = [
  { label: 'Имя и фамилия', value: 'Артём Ковалёв' },
  { label: 'Рабочая почта', value: 'a.kovalev@it-hona.tj' },
];

const NOTIFICATIONS = [
  { label: 'Новые заявки на утверждение', on: true },
  { label: 'Напоминание о заявках старше 3 дней', on: true },
  { label: 'Еженедельный отчёт по бюджету', on: false },
];
import { VARIANTS } from '@/shell/config';
import type { ShellVariant, Theme } from '@/shell/config';
import { useShell } from '@/shell/ShellContext';

export function Settings() {
  const { theme, setTheme, variant, setVariant } = useShell();
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
          <div style={{ display: 'grid', gap: 16, marginTop: 16 }}>
            {PROFILE.map((f) => (
              <label key={f.label}>
                <div className="caption" style={{ marginBottom: 4 }}>
                  {f.label}
                </div>
                <input className="field" defaultValue={f.value} />
              </label>
            ))}
          </div>
        </section>

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

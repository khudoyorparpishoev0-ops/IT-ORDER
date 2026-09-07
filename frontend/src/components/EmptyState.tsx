import type { ReactNode } from 'react';

type Props = {
  kicker: string;
  title: string;
  note?: string;
  action?: ReactNode;
};

/** Пустое состояние: штриховка 60°, рубрика, пояснение, действие. */
export function EmptyState({ kicker, title, note, action }: Props) {
  return (
    <div
      className="hatch"
      style={{
        padding: '64px var(--pad)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-card)',
        background: 'var(--paper)',
        textAlign: 'center',
      }}
    >
      <div className="label">{kicker}</div>
      <div className="h3" style={{ marginTop: 8 }}>
        {title}
      </div>
      {note && (
        <p className="caption" style={{ maxWidth: '52ch', margin: '8px auto 0' }}>
          {note}
        </p>
      )}
      {action && <div style={{ marginTop: 24 }}>{action}</div>}
    </div>
  );
}

import type { ReactNode } from 'react';

type Props = {
  kicker: string;
  title: string;
  note?: string;
  action?: ReactNode;
};

/** Пустое состояние: рубрика, заголовок, пояснение, действие. */
export function EmptyState({ kicker, title, note, action }: Props) {
  return (
    <div className="empty">
      <div className="label">{kicker}</div>
      <div className="h3" style={{ marginTop: 8 }}>
        {title}
      </div>
      {note && (
        <p className="caption" style={{ maxWidth: '52ch', margin: '8px auto 0' }}>
          {note}
        </p>
      )}
      {action && <div style={{ marginTop: 24, display: 'flex', justifyContent: 'center' }}>{action}</div>}
    </div>
  );
}

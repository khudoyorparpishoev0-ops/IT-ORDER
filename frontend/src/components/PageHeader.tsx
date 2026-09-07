import type { ReactNode } from 'react';

type Props = {
  /** Рубрика моно-капслоком над заголовком */
  kicker?: string;
  title: string;
  lead?: string;
  actions?: ReactNode;
};

export function PageHeader({ kicker, title, lead, actions }: Props) {
  return (
    <header className="row-between" style={{ marginBottom: 'var(--gap)' }}>
      <div>
        <div className="accent-rule" />
        {kicker && <div className="label">{kicker}</div>}
        <h1 className="h1" style={{ marginTop: kicker ? 8 : 0 }}>
          {title}
        </h1>
        {lead && <p className="lead-sm">{lead}</p>}
      </div>
      {actions && <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{actions}</div>}
    </header>
  );
}

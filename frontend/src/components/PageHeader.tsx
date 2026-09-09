import type { ReactNode } from 'react';

type Props = {
  title: string;
  /** Контекст под заголовком: «128 записей · сентябрь 2026». */
  lead?: string;
  actions?: ReactNode;
  /** Заголовок-вывод отчёта: зелёный штрих сверху. */
  accent?: boolean;
  /** Ссылка «назад» над заголовком. */
  back?: ReactNode;
  /** Строка над заголовком: номер и статус в карточке заявки. */
  above?: ReactNode;
};

export function PageHeader({ title, lead, actions, accent, back, above }: Props) {
  return (
    <header className="row-between">
      <div style={{ minWidth: 0 }}>
        {back && <div style={{ marginBottom: 16 }}>{back}</div>}
        {accent && <div className="accent-rule" />}
        {above && <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>{above}</div>}
        <h1 className="h1" style={accent ? { maxWidth: '34ch' } : undefined}>
          {title}
        </h1>
        {lead && <p className="lead-sm">{lead}</p>}
      </div>
      {actions && <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>{actions}</div>}
    </header>
  );
}

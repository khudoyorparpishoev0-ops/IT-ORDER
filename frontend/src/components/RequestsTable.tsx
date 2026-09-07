import { Icon } from './Icon';
import { StatusBadge } from './StatusBadge';
import { useAuth } from '@/api/auth';
import { money } from '@/data/format';
import type { RequestListItem } from '@/api/types';

export type SortKey = 'name' | 'amount' | null;

type Props = {
  rows: RequestListItem[];
  sort: SortKey;
  dir: 1 | -1;
  onSort: (key: Exclude<SortKey, null>) => void;
  onOpen: (r: RequestListItem) => void;
  /** Показывать должность отдельной строкой (раздел «Заявки») */
  withRole?: boolean;
  minWidth?: number;
};

export function RequestsTable({
  rows,
  sort,
  dir,
  onSort,
  onOpen,
  withRole = false,
  minWidth = 520,
}: Props) {
  const { can } = useAuth();
  // «Рассмотреть» обещает действие, которого у сотрудника нет.
  const canDecide = can('decide_request');
  const ariaSort = (key: Exclude<SortKey, null>) =>
    sort === key ? (dir === 1 ? 'ascending' : 'descending') : 'none';

  return (
    <div className="table-wrap">
      <table className="tbl" style={{ minWidth }}>
        <thead>
          <tr>
            <th
              className="sortable"
              style={{ width: withRole ? '42%' : '40%' }}
              aria-sort={ariaSort('name')}
              onClick={() => onSort('name')}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                СОТРУДНИК · ОБЪЕКТ
                <Icon name="ti-arrows-sort" size={14} />
              </span>
            </th>
            <th
              className="sortable right"
              style={{ width: '22%' }}
              aria-sort={ariaSort('amount')}
              onClick={() => onSort('amount')}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                СУММА
                <Icon name="ti-arrows-sort" size={14} />
              </span>
            </th>
            <th style={{ width: withRole ? '36%' : '38%' }}>СТАТУС</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              className="clickable"
              tabIndex={0}
              onClick={() => onOpen(r)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpen(r);
                }
              }}
            >
              <td>
                <div>{r.employee_name}</div>
                <div className="caption">{withRole ? `${r.employee_position} · ${r.project_name}` : r.project_name}</div>
                <div className="meta">
                  {r.number} · {r.date}
                </div>
              </td>
              <td className="right num">{money(r.amount)}</td>
              <td>
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}
                >
                  <StatusBadge status={r.status} />
                  <span
                    style={{ fontSize: 13, fontWeight: 600, color: 'var(--green-d)' }}
                  >
                    {r.status === 'pending' && canDecide ? 'Рассмотреть →' : 'Открыть →'}
                  </span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

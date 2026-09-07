import { useMemo, useState } from 'react';
import { byName } from '@/data/format';
import type { ExpenseRequest } from '@/data/types';
import type { SortKey } from '@/components/RequestsTable';

/** Сортировка списка заявок: по имени (локаль ru) или по сумме, с инверсией. */
export function useSortedRequests(source: ExpenseRequest[]) {
  const [sort, setSort] = useState<SortKey>(null);
  const [dir, setDir] = useState<1 | -1>(1);

  const onSort = (key: Exclude<SortKey, null>) => {
    if (sort === key) {
      setDir((d) => (d === 1 ? -1 : 1));
    } else {
      setSort(key);
      setDir(1);
    }
  };

  const rows = useMemo(() => {
    if (!sort) return source;
    return [...source].sort((a, b) =>
      sort === 'amount' ? (a.amount - b.amount) * dir : byName(a.name, b.name) * dir,
    );
  }, [source, sort, dir]);

  return { rows, sort, dir, onSort };
}

import { Icon } from './Icon';

/** Пагинация: слева «1—20 из 128» моно, справа кнопки 36×36. */
export function Pager({
  total,
  offset,
  limit,
  onChange,
}: {
  total: number;
  offset: number;
  limit: number;
  onChange: (offset: number) => void;
}) {
  if (total === 0) return null;
  const page = Math.floor(offset / limit);
  const pages = Math.max(1, Math.ceil(total / limit));
  const from = offset + 1;
  const to = Math.min(total, offset + limit);
  const around = [page - 1, page, page + 1].filter((p) => p >= 0 && p < pages);
  return (
    <nav className="pager" aria-label="Страницы">
      <span className="pager-info">
        {from}—{to} из {total}
      </span>
      {pages > 1 && (
        <div className="pager-pages">
          <button
            type="button"
            className="pager-btn"
            disabled={page === 0}
            onClick={() => onChange((page - 1) * limit)}
            aria-label="Предыдущая страница"
          >
            <Icon name="ti-chevron-left" size={18} />
          </button>
          {around.map((p) => (
            <button
              key={p}
              type="button"
              className="pager-btn"
              aria-current={p === page ? 'page' : undefined}
              onClick={() => onChange(p * limit)}
            >
              {p + 1}
            </button>
          ))}
          <button
            type="button"
            className="pager-btn"
            disabled={page >= pages - 1}
            onClick={() => onChange((page + 1) * limit)}
            aria-label="Следующая страница"
          >
            <Icon name="ti-chevron-right" size={18} />
          </button>
        </div>
      )}
    </nav>
  );
}

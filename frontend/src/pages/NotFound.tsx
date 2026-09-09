import { Link } from 'react-router-dom';
import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';

export function NotFound() {
  return (
    <>
      <PageHeader title="Раздел не найден" lead="Такого адреса в ORDER нет" />
      <EmptyState
        kicker="Нет данных"
        title="Такой страницы в ORDER нет"
        note="Проверьте адрес или вернитесь на дашборд."
        action={
          <Link to="/" className="btn btn-primary">
            На дашборд
          </Link>
        }
      />
    </>
  );
}

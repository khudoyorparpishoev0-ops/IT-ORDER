import { useNavigate } from 'react-router-dom';
import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';

export function NotFound() {
  const navigate = useNavigate();
  return (
    <>
      <PageHeader title="Раздел не найден" />
      <EmptyState
        kicker="НЕТ ДАННЫХ"
        title="Такой страницы в ORDER нет"
        note="Проверьте адрес или вернитесь на панель управления."
        action={
          <button type="button" className="btn btn-primary" onClick={() => navigate('/')}>
            На панель
          </button>
        }
      />
    </>
  );
}

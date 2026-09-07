import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';

/** Ответы менеджерам. Порог автоодобрения задаётся в .env, поэтому в тексте
 *  на конкретную сумму не ссылаемся. */
const FAQ = [
  {
    q: 'Как одобрить заявку сотрудника?',
    a: 'Раздел «Согласование» → выберите заявку в очереди → отметьте решение и нажмите «Одобрить». Заявки на сумму не выше порога автоодобрения закрываются без вашего участия.',
  },
  {
    q: 'Что означают статусы заявок?',
    a: 'На утверждении — требует решения. Одобрена — утверждена, ждёт выплаты. Оплачена — возмещение перечислено. Отклонена — отказано с комментарием. Черновик — сотрудник ещё не отправил заявку.',
  },
  {
    q: 'Как изменить лимит сотрудника?',
    a: 'Раздел «Команда» показывает текущие лимиты и расход по ним. Изменение лимита выполняет администратор через справочник сотрудников; сумма указывается в сомони.',
  },
  {
    q: 'Почему заявку нельзя отредактировать?',
    a: 'Править можно только черновик. После отправки на согласование состав заявки неизменяем: иначе решение руководителя относилось бы к другому документу. Ошибку исправляют новой заявкой.',
  },
  {
    q: 'Кто видит комментарии к заявке?',
    a: 'Сотрудник-автор и все согласующие в цепочке утверждения. Комментарий к отклонению обязателен: укажите факт, причину, что делаем и срок.',
  },
];

export function Help() {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<string | null>(FAQ[0].q);

  const q = query.trim().toLowerCase();
  const items = q
    ? FAQ.filter((f) => f.q.toLowerCase().includes(q) || f.a.toLowerCase().includes(q))
    : FAQ;

  return (
    <>
      <PageHeader
        title="Справка"
        lead="Ответы на частые вопросы менеджеров. Спорные случаи — brand@it-hona.tj"
      />

      <label style={{ display: 'block', maxWidth: 440, marginBottom: 'var(--gap)' }}>
        <span className="sr-only">Поиск по справке</span>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <Icon name="ti-search" style={{ position: 'absolute', left: 12, color: 'var(--slate)' }} />
          <input
            className="field"
            style={{ paddingLeft: 40 }}
            placeholder="Поиск по вопросам"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </label>

      <div style={{ display: 'grid', gap: 'var(--gap)' }}>
        {items.map((f) => {
          const expanded = open === f.q;
          return (
            <section key={f.q} className="card">
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : f.q)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 16,
                  width: '100%',
                  padding: 0,
                  border: 'none',
                  background: 'transparent',
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
              >
                <span className="h3">{f.q}</span>
                <Icon
                  name="ti-chevron-down"
                  style={{
                    transform: expanded ? 'rotate(180deg)' : 'none',
                    transition: 'transform 150ms ease-out',
                  }}
                />
              </button>
              {expanded && (
                <p style={{ maxWidth: '72ch', color: 'var(--slate)', margin: '12px 0 0' }}>
                  {f.a}
                </p>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}

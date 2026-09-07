import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { FAQ } from '@/data/mock';

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

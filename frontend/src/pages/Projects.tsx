import { useMemo, useState } from 'react';
import { Field } from '@/components/Field';
import { Icon } from '@/components/Icon';
import { Overlay } from '@/components/Overlay';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useCreateProject, useProjects, useUpdateProject } from '@/api/hooks';
import type { Project } from '@/api/types';
import { money, plural } from '@/data/format';
import { useShell } from '@/shell/ShellContext';

/**
 * Объекты, на которые списываются расходы. Без них нельзя подать заявку,
 * поэтому раздел ведёт администратор: завести, переименовать, отключить.
 *
 * Удаления нет намеренно: объект попадает в заявки, а они неизменяемы и
 * должны сохранить, на что был расход. Закрытый объект отключают.
 */
export function Projects() {
  const list = useProjects();
  const { flash } = useShell();
  const [search, setSearch] = useState('');
  const [withDisabled, setWithDisabled] = useState(false);
  const [editing, setEditing] = useState<Project | 'new' | null>(null);

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (list.data ?? []).filter((p) => {
      if (!withDisabled && !p.active) return false;
      return !needle || p.name.toLowerCase().includes(needle);
    });
  }, [list.data, search, withDisabled]);

  const disabledCount = (list.data ?? []).filter((p) => !p.active).length;

  return (
    <>
      <PageHeader
        kicker="СПРАВОЧНИК"
        title="Объекты"
        lead="Стройки и площадки, на которые списываются расходы"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
            <Icon name="ti-plus" />
            Добавить объект
          </button>
        }
      />

      <div
        style={{
          display: 'flex',
          gap: 8,
          flexWrap: 'wrap',
          alignItems: 'center',
          marginBottom: 'var(--gap)',
        }}
      >
        <label style={{ flex: '1 1 240px', maxWidth: 360 }}>
          <span className="sr-only">Поиск по названию</span>
          <input
            className="field"
            type="search"
            placeholder="Название объекта"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {disabledCount > 0 && (
          <button
            type="button"
            className="chip"
            aria-pressed={withDisabled}
            onClick={() => setWithDisabled((v) => !v)}
          >
            Показать отключённые ({disabledCount})
          </button>
        )}
      </div>

      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        isEmpty={rows.length === 0}
        emptyTitle={search ? 'Ничего не найдено' : 'Объекты не заведены'}
        emptyNote={
          search
            ? 'Проверьте написание или очистите поиск.'
            : 'Заведите первый объект — без него сотрудники не смогут подать заявку.'
        }
        emptyAction={
          <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
            Добавить объект
          </button>
        }
        onRetry={() => list.refetch()}
      >
        <section className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ minWidth: 560 }}>
              <thead>
                <tr>
                  <th style={{ width: '46%' }}>ОБЪЕКТ</th>
                  <th className="right" style={{ width: '14%' }}>
                    ЗАЯВОК
                  </th>
                  <th className="right" style={{ width: '20%' }}>
                    РАСХОД, TJS
                  </th>
                  <th style={{ width: '20%' }}>СОСТОЯНИЕ</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr
                    key={p.id}
                    className="clickable"
                    tabIndex={0}
                    onClick={() => setEditing(p)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setEditing(p);
                      }
                    }}
                  >
                    <td style={{ fontWeight: 600 }}>{p.name}</td>
                    <td className="right num">{p.requests_count}</td>
                    <td className="right num">{money(p.spent)}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span
                          aria-hidden="true"
                          style={{
                            width: 8,
                            height: 8,
                            flex: 'none',
                            background: p.active ? 'var(--dot-ok)' : 'var(--dot-off)',
                          }}
                        />
                        {p.active ? 'В работе' : 'Отключён'}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </QueryState>

      <p className="caption" style={{ marginTop: 'var(--gap)' }}>
        Закрытый объект отключают, а не удаляют: заявки неизменяемы и должны
        сохранить, на что был расход. Отключённый объект пропадает из выбора при
        подаче новой заявки, старые заявки остаются на месте.
      </p>

      {editing && (
        <ProjectModal
          project={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onFlash={flash}
        />
      )}
    </>
  );
}

function ProjectModal({
  project,
  onClose,
  onFlash,
}: {
  project: Project | null;
  onClose: () => void;
  onFlash: (text: string, color: string) => void;
}) {
  const create = useCreateProject();
  const update = useUpdateProject();
  const [name, setName] = useState(project?.name ?? '');
  const [active, setActive] = useState(project?.active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const dirty = name !== (project?.name ?? '') || active !== (project?.active ?? true);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      if (project) {
        await update.mutateAsync({ id: project.id, name: name.trim(), active });
        onFlash('Объект сохранён', 'var(--dot-ok)');
      } else {
        await create.mutateAsync({ name: name.trim(), active });
        onFlash('Объект заведён', 'var(--dot-ok)');
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить объект');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Overlay
      label={project ? `Объект ${project.name}` : 'Новый объект'}
      onClose={onClose}
      dirty={dirty}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <div className="label">{project ? 'ОБЪЕКТ' : 'НОВЫЙ ОБЪЕКТ'}</div>
          <div className="h3" style={{ marginTop: 4 }}>
            {project ? project.name : 'Заведение объекта'}
          </div>
        </div>
        <button
          type="button"
          className="btn btn-icon"
          onClick={onClose}
          aria-label="Закрыть"
          style={{ border: 'none' }}
        >
          <Icon name="ti-x" />
        </button>
      </div>

      <form onSubmit={submit} style={{ display: 'grid', gap: 16, marginTop: 24 }}>
        <Field
          label="Название"
          note="Так объект увидят в заявках и отчётах: «Вилла Колхозная», «Рекова 132»."
        >
          {(id) => (
            <input
              id={id}
              className="field"
              required
              autoFocus
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
        </Field>

        <div>
          <button
            type="button"
            role="checkbox"
            aria-checked={active}
            onClick={() => setActive((v) => !v)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              minHeight: 44,
              padding: '0 4px',
              border: 'none',
              background: 'transparent',
              textAlign: 'left',
              cursor: 'pointer',
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 20,
                height: 20,
                flex: 'none',
                display: 'grid',
                placeItems: 'center',
                borderRadius: 'var(--r-field)',
                border: active ? '1px solid var(--green)' : '1px solid var(--grey)',
                background: active ? 'var(--green)' : 'transparent',
                color: '#FFFFFF',
              }}
            >
              <Icon name="ti-check" size={14} style={{ opacity: active ? 1 : 0 }} />
            </span>
            Объект в работе
          </button>
          <div className="caption" style={{ marginTop: 4 }}>
            Снятая отметка убирает объект из выбора при подаче новой заявки.
            Поданные заявки остаются как есть.
          </div>
        </div>

        {project && project.requests_count > 0 && (
          <p className="caption" style={{ margin: 0 }}>
            По объекту {project.requests_count}{' '}
            {plural(project.requests_count, 'заявка', 'заявки', 'заявок')} на{' '}
            {money(project.spent)} TJS. Переименование меняет название и в них —
            это одна и та же запись справочника.
          </p>
        )}

        {error && (
          <div className="field-error-text" role="alert">
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="submit" className="btn btn-primary" disabled={saving || !name.trim()}>
            {saving ? 'Сохраняем…' : project ? 'Сохранить' : 'Завести объект'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
        </div>
      </form>
    </Overlay>
  );
}

import { useId, useMemo, useState } from 'react';
import { Field } from '@/components/Field';
import { Icon } from '@/components/Icon';
import { Modal } from '@/components/Modal';
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

  const all = list.data ?? [];
  const disabledCount = all.filter((p) => !p.active).length;
  const requestsTotal = all.reduce((sum, p) => sum + p.requests_count, 0);

  return (
    <>
      <PageHeader
        title="Объекты"
        lead={
          list.data
            ? `${all.length} ${plural(all.length, 'объект', 'объекта', 'объектов')} · ${requestsTotal} ${plural(requestsTotal, 'заявка', 'заявки', 'заявок')}`
            : undefined
        }
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
            <Icon name="ti-plus" size={18} />
            Добавить объект
          </button>
        }
      />

      <div className="filter-row">
        <label className="sr-only" htmlFor="p-search">
          Поиск по названию
        </label>
        <input
          id="p-search"
          className="field"
          type="search"
          placeholder="Название объекта"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ height: 36, fontSize: 14, flex: '1 1 200px', maxWidth: 280 }}
        />
        {disabledCount > 0 && (
          <button
            type="button"
            className="filter"
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
        <div className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ ['--tbl-min' as string]: '640px' }}>
              <thead>
                <tr>
                  <th style={{ width: '46%' }}>Объект</th>
                  <th className="right" style={{ width: '14%' }}>
                    Заявок
                  </th>
                  <th className="right" style={{ width: '20%' }}>
                    Расход, TJS
                  </th>
                  <th style={{ width: '20%' }}>Состояние</th>
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
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                        <span
                          className="dot"
                          style={{ ['--dot' as string]: p.active ? 'var(--dot-ok)' : 'var(--dot-off)' }}
                        />
                        {p.active ? 'В работе' : 'Отключён'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </QueryState>

      <p className="caption" style={{ margin: 0 }}>
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
  const formId = useId();
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
    <Modal
      title={project ? project.name : 'Новый объект'}
      onClose={onClose}
      dirty={dirty}
      wide
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" form={formId} className="btn btn-primary" disabled={saving || !name.trim()}>
            {saving ? 'Сохраняем…' : project ? 'Сохранить' : 'Завести объект'}
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} style={{ display: 'grid', gap: 16 }}>
        <Field
          label="Название"
          required
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
          <div className="check-row" onClick={() => setActive((v) => !v)}>
            <button
              type="button"
              role="checkbox"
              aria-checked={active}
              aria-label="Объект в работе"
              className="check"
              onClick={(e) => {
                e.stopPropagation();
                setActive((v) => !v);
              }}
            >
              <Icon name="ti-check" size={14} style={{ opacity: active ? 1 : 0 }} />
            </button>
            <span className="small">Объект в работе</span>
          </div>
          <div className="caption">
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
      </form>
    </Modal>
  );
}

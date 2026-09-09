import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Field } from '@/components/Field';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { AiButton } from '@/components/AiButton';
import { RequestAssistant } from '@/components/RequestAssistant';
import { useAuth } from '@/api/auth';
import {
  useAiApplied,
  useAssistantStatus,
  useCreateRequest,
  useEmployees,
  useMaterialAdvice,
  useMaterials,
  useProjects,
  useRequest,
  useSubmitRequest,
  useUpdateRequest,
} from '@/api/hooks';
import type { AssistantLine, ExpenseLineInput, MaterialAdvice, RequestDetail } from '@/api/types';
import { plural } from '@/data/format';
import { useShell } from '@/shell/ShellContext';

type Line = {
  title: string;
  quantity: string;
  unit: string;
  /** Совет помощника по этому названию; 'loading' — ждём ответ. */
  advice?: MaterialAdvice | 'loading';
  /** Для какого написания получен совет: повторно не спрашиваем. */
  checked?: string;
};
const EMPTY: Line = { title: '', quantity: '1', unit: '' };

function fromDetail(edit: RequestDetail): Line[] {
  return edit.lines.map((l) => ({ title: l.title, quantity: String(l.quantity), unit: l.unit ?? '' }));
}

/** Страница формы: новая заявка или правка черновика (/requests/:id/edit). */
export function RequestForm() {
  const { id } = useParams();
  const editId = id ? Number(id) : null;
  const query = useRequest(editId);
  if (editId === null) return <Form />;
  return (
    <QueryState isLoading={query.isLoading} error={query.error} isEmpty={!query.isLoading && !query.data} emptyTitle="Черновик не найден" onRetry={() => query.refetch()}>
      {query.data && <Form edit={query.data} />}
    </QueryState>
  );
}

/**
 * Подача заявки и правка черновика — одна форма: объект и позиции
 * «что нужно — сколько — в чём». Цен нет намеренно: их назовёт отдел
 * закупа. Кнопки внизу на телефоне липкие.
 */
function Form({ edit }: { edit?: RequestDetail }) {
  const navigate = useNavigate();
  const { user, can } = useAuth();
  const { flash } = useShell();
  const projects = useProjects();
  const employees = useEmployees();
  const materials = useMaterials();
  const assistant = useAssistantStatus();
  const advise = useMaterialAdvice();
  const applied = useAiApplied();
  const create = useCreateRequest();
  const update = useUpdateRequest();
  const send = useSubmitRequest();

  const forOthers = can('create_request_for_others') && !edit;
  const [employeeId, setEmployeeId] = useState<number | null>(edit ? edit.employee_id : (user?.id ?? null));
  const [projectId, setProjectId] = useState<number | null>(edit ? edit.project_id : null);
  const [lines, setLines] = useState<Line[]>(edit ? fromDetail(edit) : [{ ...EMPTY }]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<'send' | 'draft' | null>(null);
  //  null — панель закрыта; строка — с чего начать разговор.
  const [helper, setHelper] = useState<string | null>(null);

  const activeProjects = (projects.data ?? []).filter((p) => p.active);
  const projectsNote = projects.isLoading
    ? 'Загружаем список объектов…'
    : projects.error
      ? `Не удалось загрузить объекты: ${projects.error instanceof Error ? projects.error.message : 'ошибка связи'}. Обновите страницу.`
      : activeProjects.length
        ? undefined
        : (projects.data ?? []).length
          ? 'Все объекты отключены. Включить нужный можно в разделе «Объекты» — это делает администратор.'
          : can('manage_reference')
            ? 'Объектов нет. Заведите их в разделе «Объекты» — без объекта заявку не подать.'
            : 'Объекты не заведены. Их создаёт администратор — без объекта заявку не подать.';
  const activeEmployees = (employees.data ?? []).filter((e) => e.active);

  const setLine = (index: number, patch: Partial<Line>) =>
    setLines((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const setTitle = (index: number, title: string) => {
    const known = (materials.data ?? []).find((m) => m.title.toLowerCase() === title.trim().toLowerCase());
    setLines((rows) =>
      rows.map((row, i) =>
        i === index
          ? { ...row, title, unit: row.unit || known?.unit || '', advice: row.checked === title.trim() ? row.advice : undefined }
          : row,
      ),
    );
  };

  // Помощник проверяет написание, когда человек закончил печатать
  // (поле потеряло фокус): спрашивать модель на каждую букву — дорого и
  // бессмысленно. Совет показывается рядом, применяется кнопкой.
  const checkTitle = async (index: number) => {
    const line = lines[index];
    const title = line?.title.trim() ?? '';
    if (!assistant.data?.enabled || title.length < 3 || line.checked === title) return;
    setLine(index, { advice: 'loading', checked: title });
    try {
      const advice = await advise.mutateAsync({ title, unit: line.unit.trim() || null });
      setLines((rows) =>
        rows.map((row, i) =>
          i === index && row.title.trim() === title
            ? { ...row, advice, unit: row.unit || (advice.available && !advice.changed ? advice.unit ?? '' : '') }
            : row,
        ),
      );
    } catch {
      setLines((rows) => rows.map((row, i) => (i === index ? { ...row, advice: undefined } : row)));
    }
  };

  const applyAdvice = (index: number) => {
    const line = lines[index];
    const advice = line?.advice;
    if (!advice || advice === 'loading' || !advice.suggested) return;
    // Отметка служебная: её сбой не должен мешать применить написание.
    if (advice.interaction_id !== null) applied.mutate(advice.interaction_id, { onError: () => {} });
    setLines((rows) =>
      rows.map((row, i) =>
        i === index
          ? {
              ...row,
              title: advice.suggested ?? row.title,
              unit: row.unit || advice.unit || '',
              checked: advice.suggested ?? row.checked,
              advice: { ...advice, title: advice.suggested ?? advice.title, changed: false },
            }
          : row,
      ),
    );
  };

  // Помощник предлагает позиции, переносит их человек: заменяем пустые
  // строки, остальное дописываем в конец.
  const applyAssistant = (proposed: AssistantLine[]) => {
    const rows = lines.filter((l) => l.title.trim());
    setLines([
      ...rows,
      ...proposed.map((line) => ({
        title: line.title,
        quantity: String(line.quantity),
        unit: line.unit ?? '',
        checked: line.title,
      })),
    ]);
    setHelper(null);
    flash('Позиции добавлены — проверьте и отправьте заявку', 'var(--dot-ok)');
  };

  const filled = lines.filter((l) => l.title.trim());

  const submit = async (sendNow: boolean) => {
    if (!employeeId || !projectId) {
      setError('Выберите объект');
      return;
    }
    if (!filled.length) {
      setError('Добавьте хотя бы одну позицию: что нужно купить');
      return;
    }
    setError(null);
    setSaving(sendNow ? 'send' : 'draft');
    try {
      const payload: ExpenseLineInput[] = filled.map((l) => ({
        title: l.title.trim(),
        quantity: Number(l.quantity) || 1,
        unit: l.unit.trim() || null,
      }));
      let saved: RequestDetail;
      if (edit) {
        saved = await update.mutateAsync({ id: edit.id, project_id: projectId, lines: payload });
        if (sendNow) saved = await send.mutateAsync(edit.id);
      } else {
        saved = await create.mutateAsync({ employee_id: employeeId, project_id: projectId, lines: payload, submit: sendNow });
      }
      flash(
        saved.status === 'draft' ? `Черновик ${saved.number} сохранён` : `Заявка ${saved.number} отправлена на согласование`,
        'var(--dot-ok)',
      );
      navigate(`/requests/${saved.id}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить заявку');
    } finally {
      setSaving(null);
    }
  };

  return (
    <>
      <PageHeader
        back={
          <Link to={edit ? `/requests/${edit.id}` : '/requests'} className="small" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--slate)', fontWeight: 500 }}>
            <Icon name="ti-chevron-left" size={18} />
            {edit ? `Заявка ${edit.number}` : 'Все заявки'}
          </Link>
        }
        title={edit ? `Черновик ${edit.number}` : 'Новая заявка'}
        lead="Что нужно купить, сколько и в чём считать. Цены назовёт отдел закупа."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(true);
        }}
        className="stack"
        style={{ maxWidth: 760 }}
      >
        <section className="card" style={{ display: 'grid', gap: 16 }}>
          {forOthers ? (
            <Field label="Сотрудник" note="Заявка подаётся от его имени.">
              {(id) => (
                <select id={id} className="field" value={employeeId ?? ''} onChange={(e) => setEmployeeId(Number(e.target.value) || null)}>
                  <option value="">— выберите —</option>
                  {activeEmployees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name}
                      {e.position ? ` · ${e.position}` : ''}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          ) : (
            <div>
              <div className="label field-label">Сотрудник</div>
              <div style={{ fontWeight: 600 }}>{edit ? edit.employee_name : user?.full_name}</div>
            </div>
          )}

          <Field label="Объект" required note={projectsNote}>
            {(id) => (
              <select id={id} className="field" value={projectId ?? ''} onChange={(e) => setProjectId(Number(e.target.value) || null)}>
                <option value="">Выберите объект</option>
                {activeProjects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </section>

        <section className="card" style={{ display: 'grid', gap: 12 }}>
          <div className="row-between" style={{ alignItems: 'center' }}>
            <div className="label">
              Позиции заявки
              <span aria-hidden="true" style={{ color: 'var(--red)', marginLeft: 4 }}>*</span>
            </div>
            {assistant.data?.enabled && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {/* Зелёной кнопка становится, когда в форме уже что-то есть:
                    тогда помощнику есть с чем работать. На пустой форме он
                    тоже поможет, но звать его нечем — кнопка спокойная. */}
                <AiButton
                  small
                  active={lines.some((l) => l.title.trim())}
                  label={lines.some((l) => l.title.trim()) ? 'Проверить заявку' : 'Помощь AI'}
                  onClick={() => setHelper('open')}
                />
              </div>
            )}
          </div>
          <div aria-hidden="true" className="caption line-head" style={{ marginTop: 0 }}>
            <span className="line-title">Что нужно</span>
            <span className="line-qty">Кол-во</span>
            <span className="line-unit">Единица</span>
            <span className="line-del" />
          </div>
          <datalist id="known-materials">
            {(materials.data ?? []).map((m) => (
              <option key={m.title} value={m.title}>
                {m.unit ? `${m.unit} · заказывали ${m.uses} ${plural(m.uses, 'раз', 'раза', 'раз')}` : undefined}
              </option>
            ))}
          </datalist>
          <div style={{ display: 'grid', gap: 8 }}>
            {lines.map((line, index) => (
              <div key={index} className="line-block">
              <div className="line-row">
                <input
                  className="field line-title"
                  aria-label={`Описание строки ${index + 1}`}
                  placeholder="Что нужно"
                  list="known-materials"
                  autoComplete="off"
                  value={line.title}
                  onChange={(e) => setTitle(index, e.target.value)}
                  onBlur={() => void checkTitle(index)}
                />
                <input
                  className="field mono line-qty"
                  inputMode="numeric"
                  aria-label={`Количество в строке ${index + 1}`}
                  value={line.quantity}
                  onChange={(e) => setLine(index, { quantity: e.target.value })}
                />
                <input
                  className="field line-unit"
                  aria-label={`Единица в строке ${index + 1}`}
                  placeholder="шт."
                  value={line.unit}
                  onChange={(e) => setLine(index, { unit: e.target.value })}
                />
                <button
                  type="button"
                  className="btn btn-icon line-del"
                  aria-label={`Убрать строку ${index + 1}`}
                  disabled={lines.length === 1}
                  onClick={() => setLines((rows) => rows.filter((_, i) => i !== index))}
                >
                  <Icon name="ti-x" size={18} />
                </button>
              </div>
              <AdviceHint advice={line.advice} onApply={() => applyAdvice(index)} />
              </div>
            ))}
          </div>
          <button type="button" className="btn btn-dashed" onClick={() => setLines((rows) => [...rows, { ...EMPTY }])}>
            <Icon name="ti-plus" size={18} />
            Добавить позицию
          </button>
          {assistant.data?.enabled ? (
            <p className="caption" style={{ margin: 0 }}>
              Начните печатать — панель подскажет, как это называли раньше. Когда закончите строку, помощник
              проверит написание и предложит поправку; применить её или оставить своё — решаете вы.
            </p>
          ) : (
            (materials.data ?? []).length > 0 && (
              <p className="caption" style={{ margin: 0 }}>
                Начните печатать — панель подскажет, как это называли раньше, и подставит единицу измерения.
              </p>
            )
          )}
        </section>

        {error && (
          <div className="field-error-text" role="alert">
            {error}
          </div>
        )}

        <div className="sticky-actions">
          <button type="submit" className="btn btn-primary" disabled={saving !== null}>
            {saving === 'send' ? 'Отправляем…' : 'Отправить на согласование'}
          </button>
          <button type="button" className="btn btn-secondary" disabled={saving !== null} onClick={() => void submit(false)}>
            {saving === 'draft' ? 'Сохраняем…' : edit ? 'Сохранить черновик' : 'Сохранить черновиком'}
          </button>
        </div>
        <p className="caption" style={{ margin: 0 }}>
          Черновик виден только вам и в согласование не попадает. Отправленную заявку править уже нельзя.
        </p>
      </form>

      {helper !== null && (
        <RequestAssistant
          projectName={activeProjects.find((p) => p.id === projectId)?.name ?? null}
          lines={lines}
          onApply={applyAssistant}
          onClose={() => setHelper(null)}
        />
      )}
    </>
  );
}

/**
 * Совет помощника под строкой. Молчит, когда модель недоступна: сбой
 * подсказки не должен выглядеть как проблема формы.
 */
function AdviceHint({ advice, onApply }: { advice?: MaterialAdvice | 'loading'; onApply: () => void }) {
  if (!advice) return null;
  if (advice === 'loading') {
    return (
      <div className="line-hint muted" aria-live="polite">
        Помощник проверяет написание…
      </div>
    );
  }
  if (!advice.available) return null;
  const hasNotes = advice.notes.length > 0;
  if (!advice.changed && !hasNotes) {
    return (
      <div className="line-hint muted" aria-live="polite">
        Написание верное
      </div>
    );
  }
  return (
    <div className="line-hint" aria-live="polite">
      {advice.changed && advice.suggested && (
        <div className="line-hint-row">
          <span>
            {advice.matches_existing ? 'Так это уже заказывали: ' : 'Возможно, правильнее: '}
            <b>{advice.suggested}</b>
            {advice.unit ? ` · ${advice.unit}` : ''}
          </span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onApply}>
            Применить
          </button>
        </div>
      )}
      {advice.notes.map((note) => (
        <div key={note} className="caption" style={{ margin: 0 }}>
          {note}
        </div>
      ))}
    </div>
  );
}

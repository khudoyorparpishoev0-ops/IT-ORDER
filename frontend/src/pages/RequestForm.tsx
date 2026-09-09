import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Field } from '@/components/Field';
import { Modal } from '@/components/Modal';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { AiButton } from '@/components/AiButton';
import { FrequentMaterials } from '@/components/FrequentMaterials';
import { RepeatCard } from '@/components/RepeatCard';
import { TemplatePicker } from '@/components/TemplatePicker';
import { RequestAssistant } from '@/components/RequestAssistant';
import { useAuth } from '@/api/auth';
import {
  useAiApplied,
  useDuplicateCheck,
  useRepeat,
  useSaveTemplate,
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
import type {
  AssistantLine,
  ExpenseLineInput,
  MaterialAdvice,
  MemoryItem,
  RepeatOption,
  RequestDetail,
  SimilarRequest,
  TemplateLine,
} from '@/api/types';
import { days, plural } from '@/data/format';
import { STATUS } from '@/data/status';
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
  const duplicates = useDuplicateCheck();
  const repeat = useRepeat();
  const saveTemplate = useSaveTemplate();
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
  // Похожие заявки за неделю. Спрашиваем до подачи: два одинаковых
  // счёта замечают обычно тогда, когда оба уже оплачены.
  const [repeats, setRepeats] = useState<SimilarRequest[]>([]);
  // Найденные прошлые варианты по кнопке «Как в прошлый раз».
  const [previous, setPrevious] = useState<RepeatOption[] | null>(null);
  const [naming, setNaming] = useState<string | null>(null);

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

  // Спрашиваем по событию (человек закончил строку или сменил объект), а
  // не на каждую букву: это запрос к базе, но всё равно запрос.
  const checkRepeats = async (rows: Line[] = lines, project = projectId) => {
    const titles = rows.map((l) => l.title.trim()).filter(Boolean);
    if (!titles.length) {
      setRepeats([]);
      return;
    }
    try {
      // Сама правящаяся заявка сюда попасть не может: в повторы идут
      // только поданные, а правят у нас только черновик.
      const found = await duplicates.mutateAsync({ titles, project_id: project });
      setRepeats(found.requests);
    } catch {
      // Подсказка о повторе — не повод мешать подаче заявки.
      setRepeats([]);
    }
  };

  // Состав из шаблона или прошлой заявки подставляется целиком: это
  // готовая заготовка, а не подсказка по одной строке.
  const useLines = (proposed: TemplateLine[], project: number | null, note?: string | null) => {
    const rows = proposed.map((line) => ({
      title: line.title,
      quantity: String(line.quantity),
      unit: line.unit ?? '',
      checked: line.title,
    }));
    setLines(rows.length ? rows : [{ ...EMPTY }]);
    if (project !== null) setProjectId(project);
    setPrevious(null);
    void checkRepeats(rows, project ?? projectId);
    if (note) flash(note, 'var(--dot-warn)');
  };

  const askPrevious = async () => {
    try {
      const found = await repeat.mutateAsync({
        text: lines.map((l) => l.title).join(' '),
        project_id: projectId,
      });
      if (found.options.length) setPrevious(found.options);
      else flash('Похожей заявки не нашли', 'var(--dot-off)');
    } catch {
      flash('Не удалось найти прошлые заявки', 'var(--dot-err)');
    }
  };

  const storeTemplate = async (name: string) => {
    try {
      await saveTemplate.mutateAsync({
        name,
        project_id: projectId,
        lines: filled.map((l) => ({
          title: l.title.trim(),
          quantity: Number(l.quantity) || 1,
          unit: l.unit.trim() || null,
        })),
      });
      setNaming(null);
      flash(`Шаблон «${name}» сохранён`, 'var(--dot-ok)');
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Шаблон не сохранён', 'var(--dot-err)');
    }
  };

  const pickFromHistory = (item: MemoryItem) => {
    setLines((rows) => {
      const empty = rows.findIndex((r) => !r.title.trim());
      const filled = {
        title: item.title,
        quantity: '1',
        unit: item.unit ?? '',
        checked: item.title,
      };
      const next = empty >= 0 ? rows.map((r, i) => (i === empty ? filled : r)) : [...rows, filled];
      void checkRepeats(next);
      return next;
    });
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
              <select
                id={id}
                className="field"
                value={projectId ?? ''}
                onChange={(e) => {
                  const next = Number(e.target.value) || null;
                  setProjectId(next);
                  void checkRepeats(lines, next);
                }}
              >
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
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {/* Повтор прошлой заявки моделью не считается: находит его
                  база, и работает он с выключенным помощником тоже. */}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={repeat.isPending}
                onClick={() => void askPrevious()}
              >
                {repeat.isPending ? 'Ищем…' : 'Как в прошлый раз'}
              </button>
              {filled.length > 0 && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setNaming(filled[0].title.trim().slice(0, 60))}
                >
                  Сохранить шаблоном
                </button>
              )}
              {assistant.data?.enabled && (
                /* Зелёной кнопка становится, когда в форме уже что-то есть:
                   тогда помощнику есть с чем работать. На пустой форме он
                   тоже поможет, но звать его нечем — кнопка спокойная. */
                <AiButton
                  small
                  active={lines.some((l) => l.title.trim())}
                  label={lines.some((l) => l.title.trim()) ? 'Проверить заявку' : 'Помощь AI'}
                  onClick={() => setHelper('open')}
                />
              )}
            </div>
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
                  onBlur={() => {
                    void checkTitle(index);
                    void checkRepeats();
                  }}
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

          {previous && previous.length > 0 && (
            <RepeatCard
              options={previous}
              onUse={(proposed, project) => useLines(proposed, project)}
              onClose={() => setPrevious(null)}
            />
          )}

          <TemplatePicker
            onApply={(proposed, project, warning) => useLines(proposed, project, warning)}
          />

          <FrequentMaterials
            projectId={projectId}
            projectName={activeProjects.find((p) => p.id === projectId)?.name ?? null}
            onPick={pickFromHistory}
          />

          {repeats.length > 0 && (
            <div className="dup-warning" role="status">
              <div style={{ fontWeight: 600 }}>
                {repeats.length === 1 ? 'Похожую заявку уже подавали' : 'Похожие заявки уже подавали'}
              </div>
              {repeats.map((r) => (
                <div key={r.id} className="caption" style={{ margin: 0 }}>
                  <Link to={`/requests/${r.id}`}>{r.number}</Link> · {r.project} ·{' '}
                  {r.days_ago === 0 ? 'сегодня' : `${days(r.days_ago)} назад`} · {r.employee} ·{' '}
                  {STATUS[r.status].label}
                  {r.materials.length > 0 ? ` · ${r.materials.join(', ')}` : ''}
                </div>
              ))}
              <div className="caption" style={{ margin: 0 }}>
                Проверьте, не то же ли это самое. Если нужно ещё — подавайте, это только подсказка.
              </div>
            </div>
          )}
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

      {naming !== null && (
        <Modal
          title="Сохранить шаблоном"
          onClose={() => setNaming(null)}
          footer={
            <>
              <button type="button" className="btn btn-secondary" onClick={() => setNaming(null)}>
                Отмена
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!naming.trim() || saveTemplate.isPending}
                onClick={() => void storeTemplate(naming.trim())}
              >
                {saveTemplate.isPending ? 'Сохраняем…' : 'Сохранить'}
              </button>
            </>
          }
        >
          <Field label="Название шаблона" required note="Так его будет видно в списке и в боте">
            {(id) => (
              <input
                id={id}
                className="field"
                autoFocus
                maxLength={200}
                value={naming}
                onChange={(e) => setNaming(e.target.value)}
              />
            )}
          </Field>
          <p className="caption" style={{ margin: 0 }}>
            Сохранятся позиции и объект. Заявка при этом не подаётся.
          </p>
        </Modal>
      )}

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

import { useState } from 'react';
import { Field } from './Field';
import { Icon } from './Icon';
import { Overlay } from './Overlay';
import { useAuth } from '@/api/auth';
import { useCreateRequest, useEmployees, useMaterials, useProjects } from '@/api/hooks';
import type { ExpenseLineInput } from '@/api/types';
import { plural } from '@/data/format';
import { useShell } from '@/shell/ShellContext';

type Line = { title: string; quantity: string; unit: string };

const EMPTY: Line = { title: '', quantity: '1', unit: '' };

/**
 * Подача заявки. Сумму по строкам считаем и здесь — чтобы человек видел
 * итог до отправки, — но в базу идёт расчёт сервера: копейки в браузере
 * округляются иначе.
 */
export function NewRequestModal({ onClose }: { onClose: () => void }) {
  const { user, can } = useAuth();
  const { flash } = useShell();
  const projects = useProjects();
  const employees = useEmployees();
  const materials = useMaterials();
  const create = useCreateRequest();

  const forOthers = can('create_request_for_others');
  const [employeeId, setEmployeeId] = useState<number | null>(user?.id ?? null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [lines, setLines] = useState<Line[]>([{ ...EMPTY }]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const activeProjects = (projects.data ?? []).filter((p) => p.active);
  // Пустой список бывает по трём разным причинам, и лечатся они
  // по-разному. Раньше во всех случаях писали «объекты не заведены» —
  // и человек шёл искать не там.
  const projectsNote = projects.isLoading
    ? 'Загружаем список объектов…'
    : projects.error
      ? `Не удалось загрузить объекты: ${
          projects.error instanceof Error ? projects.error.message : 'ошибка связи'
        }. Обновите страницу.`
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

  /**
   * Название из подсказки тянет за собой единицу измерения: в прошлый раз
   * этот же материал считали в мешках, и заново вспоминать это незачем.
   * Уже введённую единицу не трогаем — человек мог поправить её намеренно.
   */
  const setTitle = (index: number, title: string) => {
    const known = (materials.data ?? []).find(
      (m) => m.title.toLowerCase() === title.trim().toLowerCase(),
    );
    setLines((rows) =>
      rows.map((row, i) =>
        i === index
          ? { ...row, title, unit: row.unit || known?.unit || '' }
          : row,
      ),
    );
  };

  const filled = lines.filter((l) => l.title.trim());

  const submit = async (send: boolean) => {
    if (!employeeId || !projectId) {
      setError('Выберите сотрудника и объект');
      return;
    }
    if (!filled.length) {
      setError('Добавьте хотя бы одну строку: что нужно купить');
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const payload: ExpenseLineInput[] = filled.map((l) => ({
        title: l.title.trim(),
        quantity: Number(l.quantity) || 1,
        unit: l.unit.trim() || null,
      }));
      const created = await create.mutateAsync({
        employee_id: employeeId,
        project_id: projectId,
        lines: payload,
        submit: send,
      });
      flash(
        created.status === 'draft'
          ? `Черновик ${created.number} сохранён`
          : `Заявка ${created.number} отправлена на согласование`,
        'var(--dot-ok)',
      );
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить заявку');
    } finally {
      setSaving(false);
    }
  };

  // Что-то введено — окно не закроется молча по клику мимо или Escape.
  const dirty =
    projectId !== null ||
    lines.some((l) => l.title.trim() || l.unit.trim() || l.quantity !== '1') ||
    (forOthers && employeeId !== (user?.id ?? null));

  return (
    <Overlay label="Новая заявка" onClose={onClose} dirty={dirty}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <div className="label">НОВАЯ ЗАЯВКА</div>
          <div className="h3" style={{ marginTop: 4 }}>
            Что нужно купить
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

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(true);
        }}
        style={{ display: 'grid', gap: 16, marginTop: 24 }}
      >
        {forOthers ? (
          <Field label="Сотрудник" note="Заявка подаётся от его имени и считается в его лимит.">
            {(id) => (
              <select
                id={id}
                className="field"
                value={employeeId ?? ''}
                onChange={(e) => setEmployeeId(Number(e.target.value) || null)}
              >
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
            <div className="caption">Сотрудник</div>
            <div style={{ fontWeight: 600, marginTop: 2 }}>{user?.full_name}</div>
          </div>
        )}

        <Field label="Объект" note={projectsNote}>
          {(id) => (
            <select
              id={id}
              className="field"
              value={projectId ?? ''}
              onChange={(e) => setProjectId(Number(e.target.value) || null)}
            >
              <option value="">— выберите —</option>
              {activeProjects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </Field>

        <div>
          <div className="label">СОСТАВ РАСХОДОВ</div>
          {/* Подписи столбцов: плейсхолдер исчезает при вводе, и без них
              непонятно, где количество, а где цена. */}
          <div aria-hidden="true" className="caption line-head">
            <span className="line-title">Что нужно</span>
            <span className="line-qty">Кол-во</span>
            <span className="line-unit">Единица</span>
            <span className="line-del" />
          </div>
          {/* Один список на все строки формы: id в datalist общий. */}
          <datalist id="known-materials">
            {(materials.data ?? []).map((m) => (
              <option key={m.title} value={m.title}>
                {m.unit ? `${m.unit} · заказывали ${m.uses} ${plural(m.uses, 'раз', 'раза', 'раз')}` : undefined}
              </option>
            ))}
          </datalist>

          <div style={{ display: 'grid', gap: 8, marginTop: 4 }}>
            {lines.map((line, index) => (
              <div key={index} className="line-row">
                <input
                  className="field line-title"
                  aria-label={`Описание строки ${index + 1}`}
                  // Плейсхолдер, а не только подпись столбца: на телефоне
                  // подписи скрыты, поля идут в столбик.
                  placeholder="Что нужно"

                  // Подсказки из прошлых заявок: браузер сам фильтрует
                  // список по мере ввода. Так одно и то же не пишут
                  // тремя способами, и отчёты не рассыпаются.
                  list="known-materials"
                  autoComplete="off"
                  value={line.title}
                  onChange={(e) => setTitle(index, e.target.value)}
                />
                <input
                  className="field num line-qty"
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
            ))}
          </div>
          {(materials.data ?? []).length > 0 && (
            <div className="caption" style={{ marginTop: 8 }}>
              Начните печатать — панель подскажет, как это называли раньше, и
              подставит единицу измерения.
            </div>
          )}

          <button
            type="button"
            className="btn btn-ghost"
            style={{ marginTop: 8 }}
            onClick={() => setLines((rows) => [...rows, { ...EMPTY }])}
          >
            <Icon name="ti-plus" size={18} />
            Ещё строка
          </button>
        </div>

        <div
          style={{
            borderTop: '1px solid var(--line)',
            paddingTop: 16,
            color: 'var(--slate)',
          }}
        >
          Цены указывать не нужно: заявку сперва согласует руководитель, потом
          отдел закупа проверит склад и проставит стоимость того, чего нет.
        </div>

        {error && (
          <div className="field-error-text" role="alert">
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Сохраняем…' : 'Отправить на согласование'}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={saving}
            onClick={() => submit(false)}
          >
            Сохранить черновиком
          </button>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Отмена
          </button>
        </div>
        <p className="caption" style={{ margin: 0 }}>
          Черновик виден только вам и в согласование не попадает. Отправленную
          заявку править уже нельзя.
        </p>
      </form>
    </Overlay>
  );
}

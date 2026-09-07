import { useState } from 'react';
import { Field } from './Field';
import { Icon } from './Icon';
import { Overlay } from './Overlay';
import { useAuth } from '@/api/auth';
import { useCreateRequest, useEmployees, useProjects } from '@/api/hooks';
import type { ExpenseLineInput } from '@/api/types';
import { money } from '@/data/format';
import { useShell } from '@/shell/ShellContext';

type Line = { title: string; quantity: string; price: string };

const EMPTY: Line = { title: '', quantity: '1', price: '' };

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
  const create = useCreateRequest();

  const forOthers = can('create_request_for_others');
  const [employeeId, setEmployeeId] = useState<number | null>(user?.id ?? null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [lines, setLines] = useState<Line[]>([{ ...EMPTY }]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const activeProjects = (projects.data ?? []).filter((p) => p.active);
  const activeEmployees = (employees.data ?? []).filter((e) => e.active);

  const total = lines.reduce((sum, line) => {
    const price = Number(line.price.replace(',', '.'));
    const quantity = Number(line.quantity);
    if (!Number.isFinite(price) || !Number.isFinite(quantity)) return sum;
    return sum + price * quantity;
  }, 0);

  const setLine = (index: number, patch: Partial<Line>) =>
    setLines((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const filled = lines.filter((l) => l.title.trim() && l.price.trim());

  const submit = async (send: boolean) => {
    if (!employeeId || !projectId) {
      setError('Выберите сотрудника и объект');
      return;
    }
    if (!filled.length) {
      setError('Добавьте хотя бы одну строку с описанием и суммой');
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const payload: ExpenseLineInput[] = filled.map((l) => ({
        title: l.title.trim(),
        quantity: Number(l.quantity) || 1,
        // Запятую из русской раскладки сервер не поймёт — переводим в точку.
        price: l.price.trim().replace(',', '.'),
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
          : created.status === 'approved'
            ? `Заявка ${created.number} одобрена автоматически`
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
    lines.some((l) => l.title.trim() || l.price.trim() || l.quantity !== '1') ||
    (forOthers && employeeId !== (user?.id ?? null));

  return (
    <Overlay label="Новая заявка" onClose={onClose} dirty={dirty}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <div className="label">НОВАЯ ЗАЯВКА</div>
          <div className="h3" style={{ marginTop: 4 }}>
            Расходы к согласованию
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

        <Field
          label="Объект"
          note={
            activeProjects.length
              ? undefined
              : 'Объекты не заведены. Их создаёт администратор — без объекта заявку не подать.'
          }
        >
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
          <div
            aria-hidden="true"
            className="caption"
            style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}
          >
            <span style={{ flex: '3 1 200px' }}>Что покупаем</span>
            <span style={{ flex: '0 1 80px' }}>Кол-во</span>
            <span style={{ flex: '1 1 120px' }}>Цена, TJS</span>
            <span style={{ width: 44 }} />
          </div>
          <div style={{ display: 'grid', gap: 8, marginTop: 4 }}>
            {lines.map((line, index) => (
              <div
                key={index}
                style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flexWrap: 'wrap' }}
              >
                <input
                  className="field"
                  style={{ flex: '3 1 200px' }}
                  aria-label={`Описание строки ${index + 1}`}
                  value={line.title}
                  onChange={(e) => setLine(index, { title: e.target.value })}
                />
                <input
                  className="field num"
                  style={{ flex: '0 1 80px' }}
                  inputMode="numeric"
                  aria-label={`Количество в строке ${index + 1}`}
                  value={line.quantity}
                  onChange={(e) => setLine(index, { quantity: e.target.value })}
                />
                <input
                  className="field num"
                  style={{ flex: '1 1 120px' }}
                  inputMode="decimal"
                  aria-label={`Цена в строке ${index + 1}`}
                  value={line.price}
                  onChange={(e) => setLine(index, { price: e.target.value })}
                />
                <button
                  type="button"
                  className="btn btn-icon"
                  aria-label={`Убрать строку ${index + 1}`}
                  disabled={lines.length === 1}
                  onClick={() => setLines((rows) => rows.filter((_, i) => i !== index))}
                >
                  <Icon name="ti-x" size={18} />
                </button>
              </div>
            ))}
          </div>
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

        <div className="row-between" style={{ borderTop: '1px solid var(--line)', paddingTop: 16 }}>
          <span className="label">ИТОГО, TJS</span>
          <span className="num" style={{ fontSize: 18, fontWeight: 600 }}>
            {money(total)}
          </span>
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

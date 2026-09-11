import { useId, useState } from 'react';
import { Field } from '@/components/Field';
import { Icon } from '@/components/Icon';
import { Modal } from '@/components/Modal';
import { useEmployees, useProjects, useWarehouseSave, useWarehouses } from '@/api/hooks';

/**
 * Склад как место хранения. Заводит администратор: это структура
 * компании, как объект, а не операция кладовщика.
 *
 * Удаления нет: склад живёт в документах, а они неизменяемы. Отключить
 * можно только пустой — остаток сначала выдают или перемещают.
 */
export function WarehouseModal({
  warehouseId,
  onClose,
  onFlash,
}: {
  warehouseId: number | null;
  onClose: () => void;
  onFlash: (text: string, color: string) => void;
}) {
  const list = useWarehouses();
  const projects = useProjects();
  const employees = useEmployees();
  const save = useWarehouseSave();
  const formId = useId();

  const warehouse = (list.data ?? []).find((row) => row.id === warehouseId) ?? null;

  const [name, setName] = useState(warehouse?.name ?? '');
  const [projectId, setProjectId] = useState<number | ''>(warehouse?.project_id ?? '');
  const [keeperId, setKeeperId] = useState<number | ''>(warehouse?.keeper_id ?? '');
  const [address, setAddress] = useState(warehouse?.address ?? '');
  const [active, setActive] = useState(warehouse?.active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await save.mutateAsync({
        id: warehouseId ?? undefined,
        name: name.trim(),
        project_id: projectId === '' ? null : Number(projectId),
        keeper_id: keeperId === '' ? null : Number(keeperId),
        address: address.trim() || null,
        active,
      });
      onFlash(warehouseId ? 'Склад сохранён' : 'Склад заведён', 'var(--dot-ok)');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить склад');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={warehouse ? warehouse.name : 'Новый склад'}
      onClose={onClose}
      dirty
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
          <button
            type="submit"
            form={formId}
            className="btn btn-primary"
            disabled={saving || !name.trim()}
          >
            {saving ? 'Сохраняем…' : warehouseId ? 'Сохранить' : 'Завести склад'}
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} style={{ display: 'grid', gap: 16 }}>
        <Field label="Название" required note="«Центральный склад», «Склад на Рекова».">
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

        <Field label="Объект" note="Пусто — склад центральный, он не про объект.">
          {(id) => (
            <select
              id={id}
              className="field"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <option value="">Центральный</option>
              {(projects.data ?? [])
                .filter((project) => project.active)
                .map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
            </select>
          )}
        </Field>

        <Field label="Ответственный" note="Кто отвечает за то, что здесь лежит.">
          {(id) => (
            <select
              id={id}
              className="field"
              value={keeperId}
              onChange={(e) => setKeeperId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <option value="">Не назначен</option>
              {(employees.data ?? []).map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name}
                </option>
              ))}
            </select>
          )}
        </Field>

        <Field label="Адрес">
          {(id) => (
            <input
              id={id}
              className="field"
              maxLength={200}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
            />
          )}
        </Field>

        <div>
          <div className="check-row" onClick={() => setActive((v) => !v)}>
            <button
              type="button"
              role="checkbox"
              aria-checked={active}
              aria-label="Склад работает"
              className="check"
              onClick={(e) => {
                e.stopPropagation();
                setActive((v) => !v);
              }}
            >
              <Icon name="ti-check" size={14} style={{ opacity: active ? 1 : 0 }} />
            </button>
            <span className="small">Склад работает</span>
          </div>
          <div className="caption">
            Отключить можно только пустой склад: остаток сначала выдают или
            перемещают. Документы отключённого склада остаются на месте.
          </div>
        </div>

        {error && (
          <div className="field-error-text" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}

import { useState } from 'react';
import { ConfirmModal } from '@/components/ConfirmModal';
import { Icon } from '@/components/Icon';
import { useApplyTemplate, useDeleteTemplate, useTemplates } from '@/api/hooks';
import type { RequestTemplate, TemplateLine } from '@/api/types';

type Props = {
  onApply: (lines: TemplateLine[], projectId: number | null, warning: string | null) => void;
};

/**
 * Шаблоны заявок: повторяющееся дело в одно нажатие.
 *
 * «Заправка Opel», «Обед сотрудников» — заявки, которые подают каждую
 * неделю одними и теми же словами. Шаблон подставляет состав в форму, но
 * заявку не отправляет: подставить — не то же, что подать.
 *
 * Свои у каждого: общий список пришлось бы кому-то вести, а
 * повторяющиеся дела у всех разные.
 */
export function TemplatePicker({ onApply }: Props) {
  const templates = useTemplates();
  const apply = useApplyTemplate();
  const remove = useDeleteTemplate();
  const [confirm, setConfirm] = useState<RequestTemplate | null>(null);

  const rows = templates.data ?? [];
  if (!rows.length) return null;

  const use = async (template: RequestTemplate) => {
    try {
      const result = await apply.mutateAsync(template.id);
      onApply(result.template.lines, result.template.project_id, result.warning);
    } catch {
      // Шаблон могли удалить в другой вкладке: список обновится сам.
    }
  };

  return (
    <>
      <div className="chip-row">
        <span className="caption chip-row-label">Шаблоны</span>
        {rows.slice(0, 6).map((template) => (
          <span key={template.id} className="chip-pair">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={apply.isPending}
              onClick={() => void use(template)}
            >
              {template.name}
              {template.project_name ? <span className="caption">{template.project_name}</span> : null}
            </button>
            <button
              type="button"
              className="btn btn-icon btn-sm"
              aria-label={`Удалить шаблон «${template.name}»`}
              onClick={() => setConfirm(template)}
            >
              <Icon name="ti-x" size={14} />
            </button>
          </span>
        ))}
      </div>

      {confirm && (
        <ConfirmModal
          title="Удалить шаблон"
          text={`Шаблон «${confirm.name}» пропадёт. Поданные по нему заявки останутся.`}
          confirmLabel="Удалить"
          danger
          onConfirm={() => {
            remove.mutate(confirm.id);
            setConfirm(null);
          }}
          onClose={() => setConfirm(null)}
        />
      )}
    </>
  );
}

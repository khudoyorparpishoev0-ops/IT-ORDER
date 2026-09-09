import { useMemory } from '@/api/hooks';
import type { MemoryItem } from '@/api/types';

type Props = {
  projectId: number | null;
  projectName: string | null;
  onPick: (item: MemoryItem) => void;
};

/**
 * «Часто заказываете» — подсказки из истории заявок, не от модели.
 *
 * Считает их база (`services/ai_memory.py`), поэтому они работают всегда:
 * кончился баланс у Anthropic или не задан ключ — лента остаётся. Ради
 * этого она и сделана отдельно от помощника: самая частая заявка — это
 * повтор прошлой, и на неё должно хватать одного нажатия.
 *
 * Порядок источников — от точного к общему: что берут на этом объекте,
 * потом что заказывает сам сотрудник, потом что просят в компании.
 * Смешивать их нельзя: подпись объясняет, откуда подсказка, а без
 * подписи это просто список слов неизвестного происхождения.
 */
export function FrequentMaterials({ projectId, projectName, onPick }: Props) {
  const memory = useMemory(projectId);
  const data = memory.data;
  if (!data) return null;

  const source: { label: string; items: MemoryItem[] } | null =
    data.project.length > 0 && projectName
      ? { label: `Часто на объекте «${projectName}»`, items: data.project }
      : data.mine.length > 0
        ? { label: 'Вы обычно заказываете', items: data.mine }
        : data.frequent.length > 0
          ? { label: 'Часто заказывают', items: data.frequent }
          : null;

  if (!source) return null;

  return (
    <div className="chip-row">
      <span className="caption chip-row-label">{source.label}</span>
      {source.items.slice(0, 6).map((item) => (
        <button
          key={item.title}
          type="button"
          className="btn btn-secondary btn-sm"
          title={
            item.last_number
              ? `Последний раз: ${item.last_number}, всего заказов: ${item.times}`
              : undefined
          }
          onClick={() => onPick(item)}
        >
          {item.title}
          {item.unit ? <span className="caption">{item.unit}</span> : null}
        </button>
      ))}
    </div>
  );
}

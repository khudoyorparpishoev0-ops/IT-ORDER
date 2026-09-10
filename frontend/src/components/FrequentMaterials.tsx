import { useMemory } from '@/api/hooks';
import type { MemoryItem } from '@/api/types';

type Props = {
  projectId: number | null;
  projectName: string | null;
  onPick: (item: MemoryItem) => void;
};

/** Одна лента подсказок: подпись слева, варианты кнопками. */
function Lane({
  label,
  items,
  onPick,
}: {
  label: string;
  items: MemoryItem[];
  onPick: (item: MemoryItem) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="chip-row">
      <span className="caption chip-row-label">{label}</span>
      {items.slice(0, 5).map((item) => (
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

/**
 * Подсказки из истории заявок, не от модели.
 *
 * Считает их база (`services/ai_memory.py`), поэтому они работают всегда:
 * кончился баланс у Anthropic или не задан ключ — ленты остаются. Ради
 * этого они и сделаны отдельно от помощника: самая частая заявка — это
 * повтор прошлой, и на неё должно хватать одного нажатия.
 *
 * Лент три, и каждая отвечает на свой вопрос: что берут на этом объекте,
 * что человек заказывал недавно, что он заказывает часто. Смешивать их
 * нельзя — подпись объясняет, откуда подсказка, а без неё это просто
 * список слов неизвестного происхождения.
 *
 * Имён и сумм здесь нет ни в одной ленте: это знание о материалах, а не
 * о людях. Сервер их и не присылает.
 */
export function FrequentMaterials({ projectId, projectName, onPick }: Props) {
  const memory = useMemory(projectId);
  const data = memory.data;
  if (!data) return null;

  // Объект точнее личной привычки: на стройке потребности площадки важнее.
  // Если объект не выбран, его место занимает корпоративная частота.
  const first =
    data.project.length > 0 && projectName
      ? { label: `Часто на объекте «${projectName}»`, items: data.project }
      : { label: 'Часто заказывают', items: data.frequent };

  // «Недавно» и «часто» — разные вопросы, но если ответы совпали,
  // показывать одно и то же дважды незачем.
  const recent = data.recent.filter(
    (item) => !first.items.some((shown) => shown.title === item.title),
  );
  const often = data.mine.filter(
    (item) =>
      !first.items.some((shown) => shown.title === item.title) &&
      !recent.some((shown) => shown.title === item.title),
  );

  return (
    <div className="stack">
      <Lane label={first.label} items={first.items} onPick={onPick} />
      <Lane label="Недавно заказывали" items={recent} onPick={onPick} />
      <Lane label="Часто используете" items={often} onPick={onPick} />
    </div>
  );
}

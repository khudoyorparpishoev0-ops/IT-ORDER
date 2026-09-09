import { useState } from 'react';
import { Link } from 'react-router-dom';
import { days } from '@/data/format';
import type { RepeatOption, TemplateLine } from '@/api/types';

type Props = {
  options: RepeatOption[];
  onUse: (lines: TemplateLine[], projectId: number) => void;
  onClose: () => void;
};

/**
 * «Как в прошлый раз»: найденный прошлый вариант.
 *
 * Заявка по нему не создаётся никогда — только показывается человеку с
 * кнопками. Угадать можно и неверно, а деньги тратятся настоящие.
 *
 * «Другой вариант» листает остальные находки: первая — самая вероятная,
 * но не единственная, и выбирать должен человек.
 */
export function RepeatCard({ options, onUse, onClose }: Props) {
  const [index, setIndex] = useState(0);
  const option = options[index];
  if (!option) return null;

  return (
    <div className="repeat-card" role="status">
      <div style={{ fontWeight: 600 }}>Нашли предыдущий вариант</div>
      <div className="caption" style={{ margin: 0 }}>
        <Link to={`/requests/${option.request_id}`}>{option.number}</Link> · {option.project} ·{' '}
        {option.days_ago === 0 ? 'сегодня' : `${days(option.days_ago)} назад`}
        {option.reasons.length ? ` · ${option.reasons[0]}` : ''}
      </div>
      <div className="repeat-lines">
        {option.lines.map((line, i) => (
          <div key={i} className="caption" style={{ margin: 0 }}>
            {line.title} — {line.quantity}
            {line.unit ? ` ${line.unit}` : ''}
          </div>
        ))}
      </div>
      <div className="chat-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => onUse(option.lines, option.project_id)}
        >
          Использовать
        </button>
        {options.length > 1 && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setIndex((i) => (i + 1) % options.length)}
          >
            Другой вариант
            <span className="caption">
              {index + 1} из {options.length}
            </span>
          </button>
        )}
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          Отмена
        </button>
      </div>
      <div className="caption" style={{ margin: 0 }}>
        Заявку не подаём: проверьте состав и отправьте сами.
      </div>
    </div>
  );
}

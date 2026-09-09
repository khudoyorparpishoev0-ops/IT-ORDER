import { useState } from 'react';
import { useAiFeedback, useFeedbackReasons } from '@/api/hooks';

/**
 * Оценка ответа помощника: помог или нет.
 *
 * Доля применённых ответов говорит, чем пользуются; оценка говорит, что
 * именно не так — не понял запрос, назвал не тот материал, задал лишние
 * вопросы. По первому видно, работает ли помощник, по второму — что в
 * нём чинить.
 *
 * Причины спрашиваем только у «не подходит»: чем именно помогло — данные,
 * которыми никто не пользуется, а лишний экран человек запомнит.
 */
export function AiFeedback({ interactionId }: { interactionId: number | null }) {
  const rate = useAiFeedback();
  const [asked, setAsked] = useState(false);
  const [done, setDone] = useState<'useful' | 'useless' | null>(null);
  const reasons = useFeedbackReasons(asked);

  if (interactionId === null) return null;

  const send = (useful: boolean, reason?: string) => {
    rate.mutate(
      { interaction_id: interactionId, useful, reason: reason ?? null },
      { onError: () => {} },
    );
    setDone(useful ? 'useful' : 'useless');
    setAsked(false);
  };

  if (done && !asked) {
    return (
      <div className="ai-rate" aria-live="polite">
        <span className="caption ai-rate-label">
          {done === 'useful' ? 'Спасибо, учтём.' : 'Спасибо, разберёмся.'}
        </span>
      </div>
    );
  }

  if (asked) {
    return (
      <div className="ai-rate">
        <span className="caption ai-rate-label">Что не так?</span>
        {Object.entries(reasons.data ?? {}).map(([code, label]) => (
          <button
            key={code}
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => send(false, code)}
          >
            {label}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="ai-rate">
      <span className="caption ai-rate-label">Помог ответ?</span>
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => send(true)}>
        Полезно
      </button>
      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAsked(true)}>
        Не подходит
      </button>
    </div>
  );
}

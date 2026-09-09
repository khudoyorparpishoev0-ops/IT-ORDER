import { useEffect, useRef, useState } from 'react';
import { AiButton } from '@/components/AiButton';
import { Modal } from '@/components/Modal';
import { useAiApplied, useAssistantChat } from '@/api/hooks';
import type { AssistantLine, AssistantReply, AssistantTurn } from '@/api/types';

/** Строка формы в том виде, в каком её видит помощник. */
export type FormLine = { title: string; quantity: string; unit: string };

type Props = {
  /** Объект из формы: помощник о нём не спрашивает. */
  projectName: string | null;
  lines: FormLine[];
  onApply: (lines: AssistantLine[]) => void;
  onClose: () => void;
};

/** Подпись и цвет статуса ответа. Точка плюс слово, как у заявок. */
const STATUS: Record<AssistantReply['status'], { label: string; color: string }> = {
  need_clarification: { label: 'Нужно уточнить', color: 'var(--yellow)' },
  ready: { label: 'Заявка готова', color: 'var(--green)' },
  warning: { label: 'Есть замечание', color: 'var(--yellow)' },
  recommendation: { label: 'Есть рекомендация', color: 'var(--blue)' },
};

/**
 * Диалог с помощником по заявке. Помощник спрашивает то, чего не хватает
 * закупу, и в конце показывает готовые позиции. Ничего не подставляется
 * молча: позиции переносит в форму человек кнопкой «Применить».
 */
export function RequestAssistant({ projectName, lines, onApply, onClose }: Props) {
  const chat = useAssistantChat();
  const applied = useAiApplied();
  const [history, setHistory] = useState<AssistantTurn[]>([]);
  const [reply, setReply] = useState<AssistantReply | null>(null);
  const [draft, setDraft] = useState('');
  const [failed, setFailed] = useState(false);
  const [last, setLast] = useState('');
  // Человек отказался от предложенных позиций: карточку убираем, разговор
  // продолжается — «Отмена» отменяет предложение, а не помощника.
  const [dropped, setDropped] = useState(false);
  const started = useRef(false);
  const tail = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const context = {
    project_name: projectName,
    lines: lines
      .filter((l) => l.title.trim())
      .map((l) => ({ title: l.title.trim(), quantity: Number(l.quantity) || null, unit: l.unit.trim() || null })),
  };

  const send = async (text: string) => {
    const asked: AssistantTurn[] = text.trim() ? [...history, { role: 'user', text: text.trim() }] : history;
    setHistory(asked);
    setLast(text);
    setDraft('');
    setFailed(false);
    setDropped(false);
    try {
      const answer = await chat.mutateAsync({ text, history, context });
      setReply(answer);
      if (answer.available && answer.message) {
        setHistory([...asked, { role: 'assistant', text: answer.message }]);
      }
      if (!answer.available) setFailed(true);
    } catch {
      setFailed(true);
    }
  };

  // Первый запрос уходит сам: человек уже нажал кнопку. Пустой текст
  // сервер понимает как «посмотри, что в форме»: при пустой форме
  // отвечает приглашением, при заполненной — проверяет заявку.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void send('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    tail.current?.scrollIntoView({ block: 'end' });
  }, [history.length, chat.isPending]);

  const status = reply && reply.available ? STATUS[reply.status] : null;
  const canApply = Boolean(reply?.available && reply.lines.length && !dropped);

  const apply = () => {
    if (!reply) return;
    // Отметка «ответом воспользовались» служебная: её сбой не должен
    // отнимать у человека позиции, поэтому ошибку глотаем.
    if (reply.interaction_id !== null) applied.mutate(reply.interaction_id, { onError: () => {} });
    onApply(reply.lines);
  };

  // «Изменить» — не отказ: карточка уходит, разговор продолжается с того
  // же места, курсор оказывается в поле ответа.
  const amend = () => {
    setDropped(true);
    input.current?.focus();
  };

  return (
    <Modal
      title="Помощник по заявке"
      onClose={onClose}
      wide
      footer={
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Закрыть
        </button>
      }
    >
      <div className="chat">
        {history.map((turn, i) => (
          <div key={i} className={turn.role === 'user' ? 'chat-row own' : 'chat-row'}>
            <div className="chat-bubble">{turn.text}</div>
          </div>
        ))}
        {chat.isPending && (
          <div className="chat-row">
            <div className="chat-bubble muted" aria-live="polite">
              Думаю…
            </div>
          </div>
        )}
        <div ref={tail} />
      </div>

      {failed && !chat.isPending && (
        <div className="chat-options" role="alert">
          <p className="caption" style={{ margin: 0 }}>
            Помощник не ответил. Заполните заявку сами — форма работает как обычно. Если это
            повторяется, покажите администратору: он проверит помощника командой на сервере.
          </p>
          <div className="chat-chips">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => void send(last)}>
              Повторить
            </button>
          </div>
        </div>
      )}

      {reply?.available && !chat.isPending && (
        <>
          {status && (
            <div className="chat-status">
              <span className="dot" style={{ ['--dot' as string]: status.color }} aria-hidden="true" />
              {status.label}
            </div>
          )}

          {reply.questions.map((q) => (
            <div key={q.field} className="chat-options">
              {q.options.length > 0 && <div className="caption">{q.question}</div>}
              <div className="chat-chips">
                {q.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => void send(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
          ))}

          {canApply && (
            <div className="chat-lines">
              <div className="rubric">Позиции заявки</div>
              {reply.lines.map((line, i) => (
                <div key={i} className="chat-line">
                  <div style={{ fontWeight: 600 }}>{line.title}</div>
                  <div className="caption">
                    {line.quantity} {line.unit ?? ''}
                    {line.purpose ? ` · ${line.purpose}` : ''}
                  </div>
                </div>
              ))}
              {/* Три исхода, и все три названы словами: перенести в заявку,
                  поправить в разговоре, отказаться от предложения. Молча
                  подставлять позиции нельзя — отвечать за заявку человеку. */}
              <div className="chat-actions">
                <button type="button" className="btn btn-primary" onClick={apply}>
                  Применить в заявку
                </button>
                <button type="button" className="btn btn-secondary" onClick={amend}>
                  Изменить
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setDropped(true)}>
                  Отмена
                </button>
              </div>
            </div>
          )}

          {[...reply.warnings, ...reply.recommendations].map((note) => (
            <p key={note} className="caption" style={{ margin: 0 }}>
              {note}
            </p>
          ))}
        </>
      )}

      <form
        className="chat-ask"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim() && !chat.isPending) void send(draft);
        }}
      >
        <label className="sr-only" htmlFor="assistant-input">
          Ответ помощнику
        </label>
        <input
          id="assistant-input"
          ref={input}
          className="field"
          value={draft}
          placeholder={dropped ? 'Напишите, что поправить…' : 'Ответьте или уточните…'}
          onChange={(e) => setDraft(e.target.value)}
          disabled={chat.isPending}
        />
        <AiButton
          type="submit"
          active={Boolean(draft.trim())}
          busy={chat.isPending}
          label="Спросить"
          disabled={!draft.trim()}
        />
      </form>
    </Modal>
  );
}

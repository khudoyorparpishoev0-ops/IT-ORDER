import { useState } from 'react';
import { Field } from './Field';
import { Modal } from './Modal';

/**
 * Подтверждение опасного действия кодом второго фактора.
 *
 * Сессия администратора живёт часами: незакрытый ноутбук, чужой человек
 * за столом — и права администратора у того, кто не вводил ни одного
 * пароля. Смена чужого пароля и сброс чужого второго фактора — это
 * захват учётной записи, поэтому здесь спрашиваем то, чего вместе с
 * сессией не украдёшь: код из приложения на телефоне.
 *
 * Код восстановления тоже подходит: телефон теряют, а доступ нужен и в
 * этот день. Проверяет всё сервер — окно только собирает ввод.
 */
export function CodeConfirm({
  title,
  text,
  confirmLabel,
  danger = false,
  busy = false,
  error,
  onConfirm,
  onClose,
}: {
  title: string;
  text: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  error?: string | null;
  onConfirm: (code: string) => void;
  onClose: () => void;
}) {
  const [code, setCode] = useState('');
  const ready = code.trim().length >= 6;

  return (
    <Modal
      title={title}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={() => onConfirm(code.trim())}
            disabled={busy || !ready}
          >
            {busy ? 'Проверяем…' : confirmLabel}
          </button>
        </>
      }
    >
      <div style={{ display: 'grid', gap: 16 }}>
        <p style={{ margin: 0 }}>{text}</p>

        <Field
          label="Код из вашего приложения"
          required
          error={error}
          note="Или код восстановления, если телефона под рукой нет."
        >
          {(id) => (
            <input
              id={id}
              className={`field num${error ? ' field-error' : ''}`}
              // Не «number»: код с ведущим нулём такой браузер обрежет,
              // а на телефоне покажет стрелки прибавления вместо цифр.
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              value={code}
              maxLength={32}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && ready && !busy) onConfirm(code.trim());
              }}
              aria-invalid={Boolean(error)}
            />
          )}
        </Field>
      </div>
    </Modal>
  );
}

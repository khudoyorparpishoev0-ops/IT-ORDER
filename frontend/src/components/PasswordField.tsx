import { useState } from 'react';
import { Field } from './Field';
import { Icon } from './Icon';

/**
 * Поле пароля с кнопкой «показать».
 *
 * Пароль набирают вслепую, а требования к нему длинные — и человек не
 * видит, что ошибся, пока вход не откажет. Особенно это мешает на
 * телефоне, где автозамена правит набранное молча.
 *
 * Показанный пароль — состояние поля, а не настройка: каждое поле
 * открывается само по себе и закрывается при уходе с экрана. Кнопка
 * лежит внутри поля и не сдвигает его: перекладывать вёрстку из-за
 * нажатия нельзя.
 */
export function PasswordField({
  label,
  note,
  error,
  required = false,
  autoComplete = 'current-password',
  autoFocus = false,
  value,
  onChange,
}: {
  label: string;
  note?: string;
  error?: string | null;
  required?: boolean;
  autoComplete?: string;
  autoFocus?: boolean;
  value: string;
  onChange: (value: string) => void;
}) {
  const [shown, setShown] = useState(false);

  return (
    <Field label={label} note={note} error={error} required={required}>
      {(id) => (
        <div className="password-field">
          <input
            id={id}
            className={`field${error ? ' field-error' : ''}`}
            type={shown ? 'text' : 'password'}
            autoComplete={autoComplete}
            autoFocus={autoFocus}
            required={required}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            aria-invalid={Boolean(error)}
          />
          <button
            type="button"
            className="password-eye"
            // Кнопку не должен подхватывать менеджер паролей и не должен
            // ловить Enter вместо кнопки входа.
            tabIndex={-1}
            aria-label={shown ? 'Скрыть пароль' : 'Показать пароль'}
            title={shown ? 'Скрыть пароль' : 'Показать пароль'}
            onClick={() => setShown((v) => !v)}
          >
            <Icon name={shown ? 'ti-eye-off' : 'ti-eye'} size={18} />
          </button>
        </div>
      )}
    </Field>
  );
}

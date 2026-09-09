import { useId } from 'react';
import type { ReactNode } from 'react';

/**
 * Поле с подписью и пояснением. Подпись связана с полем через id, а не
 * обёрнута вокруг него: иначе в доступное имя поля попадают и пояснение,
 * и кнопки рядом — экранный диктор читает мешанину, а тесты не находят
 * поле по названию.
 */
export function Field({
  label,
  note,
  required = false,
  error,
  children,
}: {
  label: string;
  note?: string;
  /** Обязательное поле помечается звёздочкой. */
  required?: boolean;
  /** Текст ошибки под полем красным. */
  error?: string | null;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div>
      <label className="label field-label" htmlFor={id}>
        {label}
        {required && (
          <span aria-hidden="true" style={{ color: 'var(--red)', marginLeft: 4 }}>
            *
          </span>
        )}
      </label>
      {children(id)}
      {error ? (
        <div className="field-error-text" role="alert">
          {error}
        </div>
      ) : (
        note && (
          <div className="caption" style={{ marginTop: 4 }}>
            {note}
          </div>
        )
      )}
    </div>
  );
}

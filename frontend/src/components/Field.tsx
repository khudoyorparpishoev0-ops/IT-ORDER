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
  children,
}: {
  label: string;
  note?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div>
      <label className="caption" htmlFor={id} style={{ display: 'block', marginBottom: 4 }}>
        {label}
      </label>
      {children(id)}
      {note && (
        <div className="caption" style={{ marginTop: 4 }}>
          {note}
        </div>
      )}
    </div>
  );
}

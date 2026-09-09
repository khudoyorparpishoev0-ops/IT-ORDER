import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Icon } from './Icon';

/**
 * Модальное окно по UI-киту: панель 440 px (wide — 640), шапка 56 px с
 * заголовком и крестиком, тело, футер с кнопками справа. Единственное
 * место с тенью уровня 2. Закрытие по Escape и клику мимо.
 *
 * `dirty` защищает заполненную форму: случайный клик мимо и Escape не
 * стирают введённое молча — окно сперва спрашивает.
 */
export function Modal({
  title,
  onClose,
  dirty = false,
  wide = false,
  footer,
  children,
}: {
  title: string;
  onClose: () => void;
  dirty?: boolean;
  wide?: boolean;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const [asking, setAsking] = useState(false);
  const startedOutside = useRef(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  const requestClose = () => {
    if (dirty) {
      setAsking(true);
      return;
    }
    onClose();
  };

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (asking) {
        setAsking(false);
        return;
      }
      requestClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });

  return (
    <div
      className="modal-scrim"
      onMouseDown={(e) => {
        startedOutside.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && startedOutside.current) requestClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`modal${wide ? ' wide' : ''}`}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div className="h3">{title}</div>
          <button
            ref={closeRef}
            type="button"
            className="btn btn-icon btn-sm"
            onClick={requestClose}
            aria-label="Закрыть"
          >
            <Icon name="ti-x" size={18} />
          </button>
        </div>
        <div className="modal-body">
          {asking && (
            <div
              role="alertdialog"
              aria-label="Закрыть без сохранения?"
              className="card card-accent"
              style={{ padding: 12, display: 'grid', gap: 12 }}
            >
              <span className="small">Закрыть без сохранения? Введённое не сохранится.</span>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" className="btn btn-danger btn-sm" onClick={onClose}>
                  Закрыть без сохранения
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setAsking(false)}
                  autoFocus
                >
                  Вернуться к форме
                </button>
              </div>
            </div>
          )}
          {children}
        </div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

/**
 * Модальное окно: затемнение, карточка по центру, закрытие по Escape и по
 * клику мимо. Единственное место с тенью — брендбук разрешает её только
 * оверлеям.
 *
 * `dirty` защищает заполненную форму: случайный клик мимо окна и Escape
 * (его же нажимают, чтобы закрыть выпадающий список) больше не стирают
 * введённое молча — окно сперва спрашивает. Без этого человек терял
 * заполненную карточку и не понимал, почему «окно просто закрылось».
 */
export function Overlay({
  label,
  onClose,
  dirty = false,
  children,
}: {
  label: string;
  onClose: () => void;
  /** true — в форме есть несохранённое, закрывать только с подтверждением. */
  dirty?: boolean;
  children: ReactNode;
}) {
  const [asking, setAsking] = useState(false);
  // Клик считается «мимо окна», только если он и начался снаружи: иначе
  // выделение текста внутри с отпусканием мыши на фоне закрывает окно.
  const startedOutside = useRef(false);

  const requestClose = () => {
    if (dirty) {
      setAsking(true);
      return;
    }
    onClose();
  };

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
      onMouseDown={(e) => {
        startedOutside.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && startedOutside.current) requestClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        background: 'rgba(16,22,19,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 600,
          maxHeight: '86vh',
          overflowY: 'auto',
          background: 'var(--paper)',
          borderRadius: 'var(--r-card)',
          boxShadow: 'var(--sh2)',
          padding: 'var(--pad)',
        }}
      >
        {asking && (
          <div
            role="alertdialog"
            aria-label="Закрыть без сохранения?"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              flexWrap: 'wrap',
              marginBottom: 24,
              padding: 12,
              border: '1px solid var(--dot-warn)',
              borderRadius: 'var(--r-field)',
              background: 'var(--st-warn-bg)',
              color: 'var(--st-warn-fg)',
            }}
          >
            <span>Закрыть без сохранения? Введённое не сохранится.</span>
            {/* Название длиннее обычного намеренно: рядом есть крестик
                «Закрыть», и две одинаковые подписи в одном окне читаются
                как одно и то же действие. */}
            <button type="button" className="btn btn-danger" onClick={onClose}>
              Закрыть без сохранения
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setAsking(false)}
              autoFocus
            >
              Вернуться к форме
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

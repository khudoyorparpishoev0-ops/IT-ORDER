import { useEffect } from 'react';
import type { ReactNode } from 'react';

/**
 * Модальное окно: затемнение, карточка по центру, закрытие по Escape и по
 * клику мимо. Единственное место с тенью — брендбук разрешает её только
 * оверлеям.
 */
export function Overlay({
  label,
  onClose,
  children,
}: {
  label: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
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
        {children}
      </div>
    </div>
  );
}

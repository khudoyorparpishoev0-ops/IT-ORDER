import { useEffect } from 'react';

export type ToastData = { text: string; color: string };

const AUTO_HIDE_MS = 3200;

export function Toast({ toast, onHide }: { toast: ToastData | null; onHide: () => void }) {
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(onHide, AUTO_HIDE_MS);
    return () => clearTimeout(t);
  }, [toast, onHide]);

  if (!toast) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'fixed',
        top: 80,
        right: 24,
        left: 'auto',
        zIndex: 60,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 16px',
        background: 'var(--paper)',
        border: '1px solid var(--line)',
        borderLeft: `2px solid ${toast.color}`,
        borderRadius: 'var(--r-card)',
        boxShadow: 'var(--sh2)',
        animation: 'toastIn 150ms ease-out',
        maxWidth: 'calc(100vw - 48px)',
      }}
    >
      <span
        aria-hidden="true"
        style={{ width: 8, height: 8, background: toast.color, flex: 'none' }}
      />
      <span>{toast.text}</span>
    </div>
  );
}

import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Icon, IconSprite } from '@/components/Icon';
import { IthonaLogo } from '@/components/Logo';
import { Toast } from '@/components/Toast';
import { Sidebar } from './Sidebar';
import { useShell } from './ShellContext';
import './shell.css';

export function AppShell() {
  const { toast, hideToast } = useShell();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <>
      <IconSprite />
      <div className="shell" data-menu-open={menuOpen}>
        <Sidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />

        {menuOpen && (
          <button
            type="button"
            className="shell-scrim"
            aria-label="Закрыть меню"
            onClick={() => setMenuOpen(false)}
          />
        )}

        <div className="shell-main">
          {/* Полоса сверху видна только на телефоне: сайдбар там скрыт, и без
              неё непонятно, где ты находишься и чем открыть разделы. */}
          <header className="shell-topbar">
            <button
              type="button"
              className="btn btn-secondary shell-burger"
              onClick={() => setMenuOpen((v) => !v)}
              aria-expanded={menuOpen}
              aria-label="Меню разделов"
            >
              <Icon name="ti-menu-2" />
            </button>
            <IthonaLogo height={22} style={{ color: 'var(--logo)' }} />
          </header>

          <main className="shell-content">
            <Outlet />
          </main>
        </div>
      </div>

      <Toast toast={toast} onHide={hideToast} />
    </>
  );
}

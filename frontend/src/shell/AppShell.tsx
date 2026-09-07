import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Icon, IconSprite } from '@/components/Icon';
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
          <button
            type="button"
            className="btn btn-secondary shell-burger"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-label="Меню разделов"
          >
            <Icon name="ti-menu-2" />
          </button>

          <main className="shell-content">
            <Outlet />
          </main>
        </div>
      </div>

      <Toast toast={toast} onHide={hideToast} />
    </>
  );
}

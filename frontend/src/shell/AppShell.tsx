import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon, IconSprite } from '@/components/Icon';
import { IthonaLogo } from '@/components/Logo';
import { Toast } from '@/components/Toast';
import { Sidebar } from './Sidebar';
import { useShell } from './ShellContext';
import './shell.css';

export function AppShell() {
  const { toast, hideToast, theme, setTheme } = useShell();
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [query, setQuery] = useState(() => params.get('q') ?? '');

  // Смена экрана сбрасывает прокрутку наверх и закрывает шторку.
  useEffect(() => {
    window.scrollTo(0, 0);
    setMenuOpen(false);
  }, [location.pathname]);

  // Поле поиска отражает адрес: очистили фильтр в списке — очистилось и здесь.
  useEffect(() => {
    if (location.pathname === '/requests') setQuery(params.get('q') ?? '');
  }, [location.pathname, params]);

  const search = (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    navigate(q ? `/requests?q=${encodeURIComponent(q)}&all=1` : '/requests');
  };

  return (
    <>
      <IconSprite />
      <div className="shell" data-menu-open={menuOpen}>
        <Sidebar onNavigate={() => setMenuOpen(false)} />

        {menuOpen && (
          <button
            type="button"
            className="shell-scrim"
            aria-label="Закрыть меню"
            onClick={() => setMenuOpen(false)}
          />
        )}

        <div className="shell-main">
          <header className="topbar">
            <button
              type="button"
              className="btn btn-icon btn-sm topbar-burger"
              onClick={() => setMenuOpen((v) => !v)}
              aria-expanded={menuOpen}
              aria-label="Меню разделов"
              style={{ width: 44, height: 44 }}
            >
              <Icon name="ti-menu-2" />
            </button>
            <div className="topbar-logo">
              <IthonaLogo height={22} />
            </div>
            <form className="topbar-search" role="search" onSubmit={search}>
              <Icon name="ti-search" size={18} className="icon" />
              <label className="sr-only" htmlFor="global-search">
                Поиск по заявкам
              </label>
              <input
                id="global-search"
                className="field"
                type="search"
                placeholder="Поиск по номеру, объекту, наименованию"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </form>
            <div className="topbar-spacer" />
            <div className="theme-switch" role="group" aria-label="Тема оформления">
              <button
                type="button"
                aria-pressed={theme === 'light'}
                onClick={() => setTheme('light')}
              >
                Светлая
              </button>
              <button
                type="button"
                aria-pressed={theme === 'dark'}
                onClick={() => setTheme('dark')}
              >
                Тёмная
              </button>
            </div>
            <button
              type="button"
              className="btn btn-icon btn-sm topbar-burger"
              aria-label="Поиск по заявкам"
              style={{ width: 44, height: 44 }}
              onClick={() => navigate('/requests')}
            >
              <Icon name="ti-search" />
            </button>
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

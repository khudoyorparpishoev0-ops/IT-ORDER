import { NavLink } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { APP_VERSION, NAV, ROLE_LABEL, VARIANTS } from './config';
import { useShell } from './ShellContext';
import { useAuth } from '@/api/auth';

type Props = { open: boolean; onNavigate: () => void };

export function Sidebar({ open, onNavigate }: Props) {
  const { variant, theme, toggleTheme } = useShell();
  const { user, can, logout } = useAuth();
  const lightShell = VARIANTS[variant].lightSidebar;

  const bg = lightShell ? 'var(--paper)' : 'var(--forest)';
  const fg = lightShell ? 'var(--ink)' : '#FFFFFF';
  const idleFg = lightShell ? 'var(--slate)' : 'rgba(255,255,255,0.78)';
  const activeBg = lightShell ? 'var(--st-ok-bg)' : '#186B36';
  const activeFg = lightShell ? 'var(--st-ok-fg)' : '#FFFFFF';
  const divider = lightShell ? '1px solid var(--line)' : '1px solid rgba(255,255,255,0.2)';
  const btnBorder = lightShell ? '1px solid var(--grey)' : '1px solid rgba(255,255,255,0.28)';

  return (
    <aside
      data-open={open}
      style={{
        flex: '0 0 var(--side-w)',
        width: 'var(--side-w)',
        background: bg,
        color: fg,
        borderRight: lightShell ? '1px solid var(--line)' : 'none',
        display: 'flex',
        flexDirection: 'column',
        position: 'sticky',
        top: 0,
        height: '100vh',
      }}
    >
      <div style={{ padding: '24px 16px', borderBottom: divider }}>
        {/* Стенд-ин логотипа. Заменить официальным SVG из бренд-пакета IT-HONA. */}
        <div style={{ fontWeight: 800, letterSpacing: '0.06em', fontSize: 19 }}>IT-HONA</div>
        <div
          className="mono"
          style={{ fontSize: 11, letterSpacing: '0.16em', opacity: 0.7, marginTop: 2 }}
        >
          CORE
        </div>
      </div>

      <nav aria-label="Разделы" style={{ padding: 8, flex: 1, overflowY: 'auto' }}>
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 2 }}>
          {NAV.filter((item) => !item.need || can(item.need)).map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === '/'}
                onClick={onNavigate}
                style={({ isActive }) => ({
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  height: 44,
                  padding: '0 12px',
                  borderRadius: 'var(--r-field)',
                  fontSize: 15,
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? activeFg : idleFg,
                  background: isActive ? activeBg : 'transparent',
                  textDecoration: 'none',
                  transition: 'background 150ms ease-out, color 150ms ease-out',
                })}
              >
                <Icon name={item.icon} />
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div style={{ padding: 16, borderTop: divider, display: 'grid', gap: 12 }}>
        <NavLink
          to="/system"
          onClick={onNavigate}
          className="mono"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: 36,
            border: btnBorder,
            borderRadius: 'var(--r-field)',
            fontSize: 11,
            letterSpacing: '0.16em',
            color: 'inherit',
            textDecoration: 'none',
          }}
        >
          ДИЗАЙН-СИСТЕМА
        </NavLink>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}
            style={{
              width: 36,
              height: 36,
              flex: 'none',
              display: 'grid',
              placeItems: 'center',
              border: btnBorder,
              borderRadius: 'var(--r-field)',
              background: 'transparent',
              color: 'inherit',
              cursor: 'pointer',
            }}
          >
            <Icon name={theme === 'dark' ? 'ti-sun' : 'ti-moon'} size={18} />
          </button>
          <div
            aria-hidden="true"
            style={{
              width: 36,
              height: 36,
              flex: 'none',
              display: 'grid',
              placeItems: 'center',
              background: lightShell ? 'var(--st-ok-bg)' : '#186B36',
              color: lightShell ? 'var(--st-ok-fg)' : '#FFFFFF',
              borderRadius: 'var(--r-field)',
              fontWeight: 700,
              fontSize: 13,
            }}
          >
            {initials(user?.full_name)}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {user?.full_name ?? '—'}
            </div>
            <div className="mono" style={{ fontSize: 11, opacity: 0.7 }}>
              {user ? (ROLE_LABEL[user.role] ?? user.role) : ''}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            type="button"
            onClick={() => void logout()}
            style={{
              flex: 1,
              height: 36,
              border: btnBorder,
              borderRadius: 'var(--r-field)',
              background: 'transparent',
              color: 'inherit',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Выйти
          </button>
          <span className="mono" style={{ fontSize: 11, opacity: 0.7 }}>
            {APP_VERSION}
          </span>
        </div>
      </div>
    </aside>
  );
}

/** Инициалы для квадратного аватара. */
function initials(name?: string): string {
  if (!name) return '—';
  return name
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0] ?? '')
    .join('')
    .toUpperCase();
}

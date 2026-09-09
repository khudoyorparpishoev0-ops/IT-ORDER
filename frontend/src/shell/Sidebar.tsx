import { NavLink } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { IthonaLogo } from '@/components/Logo';
import { APP_VERSION, NAV, ROLE_LABEL } from './config';
import { useAuth } from '@/api/auth';
import { useQueueInfo } from '@/api/hooks';

type Props = { onNavigate: () => void };

/**
 * Сайдбар по UI-киту: forest, пункты 40 px, активный — зелёная плашка.
 * Разделы без права не попадают в разметку вовсе. Внизу — сотрудник и
 * выход; на телефоне тот же список живёт в шторке.
 */
export function Sidebar({ onNavigate }: Props) {
  const { user, can, logout } = useAuth();
  const queue = useQueueInfo(can('decide_request'));
  const queueCount = (queue.data?.count ?? 0) + (queue.data?.priced_count ?? 0);

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <IthonaLogo height={28} />
      </div>

      <nav className="sidebar-nav" aria-label="Разделы">
        <ul>
          {NAV.filter((item) => !item.need || can(item.need)).map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === '/'}
                onClick={onNavigate}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                <Icon name={item.icon} />
                {item.label}
                {item.counter === 'queue' && queueCount > 0 && (
                  <span className="nav-count" aria-label={`В очереди: ${queueCount}`}>
                    {queueCount}
                  </span>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar-foot">
        <NavLink to="/system" onClick={onNavigate} className="sidebar-link">
          <Icon name="ti-layout-dashboard" size={18} />
          Дизайн-система
        </NavLink>
        <div className="sidebar-user">
          <div className="sidebar-avatar" aria-hidden="true">
            {initials(user?.full_name)}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="sidebar-name">{user?.full_name ?? '—'}</div>
            <div className="sidebar-role">
              {user ? (ROLE_LABEL[user.role] ?? user.role) : ''}
            </div>
          </div>
          <button
            type="button"
            className="sidebar-link"
            style={{ padding: '0 8px' }}
            onClick={() => void logout()}
            aria-label="Выйти"
            title={`Выйти · ${APP_VERSION} · сборка ${__BUILD_DATE__}`}
          >
            <Icon name="ti-logout" size={18} />
          </button>
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

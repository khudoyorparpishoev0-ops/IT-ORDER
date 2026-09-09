import { NavLink } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import type { IconName } from '@/components/Icon';
import { useAuth } from '@/api/auth';
import { useQueueInfo } from '@/api/hooks';

type Props = { onMore: () => void };

/**
 * Нижняя панель навигации на телефоне: Панель · Заявки · Создать ·
 * Очередь · Ещё. Только частые действия — полный список разделов живёт
 * в шторке, её открывает «Ещё». «Очередь» ведёт туда, где у роли лежат
 * заявки: согласование, закуп или финансы; у рядового сотрудника очереди
 * нет, и пункт не показывается.
 */
export function TabBar({ onMore }: Props) {
  const { can } = useAuth();
  const canDecide = can('decide_request');
  const queue = useQueueInfo(canDecide);
  const queueCount = (queue.data?.count ?? 0) + (queue.data?.priced_count ?? 0);

  const queueTab: { to: string; icon: IconName } | null = canDecide
    ? { to: '/approvals', icon: 'ti-checklist' }
    : can('source_request')
      ? { to: '/sourcing', icon: 'ti-shopping-cart' }
      : can('pay_request')
        ? { to: '/finance', icon: 'ti-wallet' }
        : null;

  return (
    <nav className="tabbar" aria-label="Быстрая навигация">
      <NavLink to="/" end className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
        <Icon name="ti-home" />
        Панель
      </NavLink>
      <NavLink
        to="/requests"
        className={({ isActive }) => `tab${isActive ? ' active' : ''}`}
      >
        <Icon name="ti-file-text" />
        Заявки
      </NavLink>
      <NavLink to="/requests/new" className="tab" aria-label="Создать заявку">
        <span className="tab-create">
          <Icon name="ti-plus" />
        </span>
      </NavLink>
      {queueTab && (
        <NavLink to={queueTab.to} className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
          <Icon name={queueTab.icon} />
          Очередь
          {canDecide && queueCount > 0 && (
            <span className="tab-badge" aria-label={`В очереди: ${queueCount}`}>
              {queueCount}
            </span>
          )}
        </NavLink>
      )}
      <button type="button" className="tab" onClick={onMore} aria-label="Ещё разделы">
        <Icon name="ti-menu-2" />
        Ещё
      </button>
    </nav>
  );
}

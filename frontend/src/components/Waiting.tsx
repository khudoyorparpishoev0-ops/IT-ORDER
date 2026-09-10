import { Icon } from '@/components/Icon';
import { DELAY_DAYS, HOLDER, STATUS } from '@/data/status';
import { plural } from '@/data/format';
import { ROLE_LABEL } from '@/shell/config';
import type { RequestDetail, RequestListItem } from '@/api/types';

/**
 * Блок «Сейчас ждёт»: кто держит заявку и сколько дней. После порога
 * рубрика меняется на «задержка», рамка становится жёлтой — это не
 * ошибка, заявка просто задерживается.
 *
 * В карточке под этим перечислены поимённо те, кто может сделать
 * следующий шаг, и главное — открывал ли каждый из них заявку. «У
 * бухгалтерии третий день» и «у бухгалтерии третий день, и туда никто
 * не заходил» — разные новости: в первом случае человек думает, во
 * втором он про заявку не знает.
 */
export function Waiting({ request }: { request: RequestListItem | RequestDetail }) {
  if (request.awaiting_stage === 'closed') return null;
  const d = request.awaiting_days ?? 0;
  const delayed = d >= DELAY_DAYS;
  const watch = 'awaiting_watch' in request ? request.awaiting_watch : [];
  const people = 'awaiting_people' in request ? request.awaiting_people : [];
  return (
    <div
      className={`waiting${delayed ? ' delayed' : ''}`}
      style={{ ['--st' as string]: STATUS[request.status].color }}
    >
      <div className="label">{delayed ? 'Сейчас ждёт · задержка' : 'Сейчас ждёт'}</div>
      <div className="waiting-who">{HOLDER[request.awaiting_stage] || request.awaiting_label}</div>
      <div className="small" style={{ color: 'var(--slate)' }}>
        {d > 0 ? `На этапе ${d} ${plural(d, 'день', 'дня', 'дней')}` : 'Поступила сегодня'}
        {watch.length === 0 && people.length > 0 && ` · ${people.join(', ')}`}
      </div>

      {watch.length > 0 && (
        <ul className="watch-list">
          {watch.map((person) => (
            <li key={person.employee_id} className="watch-row">
              <Icon
                name="ti-eye"
                size={14}
                style={{ color: person.viewed_at ? 'var(--green)' : 'var(--grey)' }}
              />
              <div style={{ minWidth: 0 }}>
                <div className="watch-name">{person.full_name}</div>
                <div className="caption">
                  {ROLE_LABEL[person.role] ?? person.role} ·{' '}
                  {person.viewed_at ? (
                    <>
                      открывал {person.viewed_at}
                      {person.times > 1 && `, ${person.times} ${plural(person.times, 'раз', 'раза', 'раз')}`}
                    </>
                  ) : (
                    'ещё не открывал'
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Короткая форма для колонки списка: «Отдел закупа · 2 дня». */
export function waitingShort(request: RequestListItem): string {
  if (request.awaiting_stage === 'closed') return '—';
  const who = HOLDER[request.awaiting_stage] || request.awaiting_label;
  const d = request.awaiting_days ?? 0;
  return d > 0 ? `${who} · ${d} ${plural(d, 'день', 'дня', 'дней')}` : `${who} · сегодня`;
}

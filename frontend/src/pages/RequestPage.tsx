import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ConfirmModal } from '@/components/ConfirmModal';
import { DecisionModal } from '@/components/DecisionModal';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { PaymentModal } from '@/components/PaymentModal';
import { QueryState } from '@/components/QueryState';
import { SourcingForm } from '@/components/SourcingForm';
import { StatusBadge } from '@/components/StatusBadge';
import { Timeline } from '@/components/Timeline';
import { Waiting } from '@/components/Waiting';
import { Workflow } from '@/components/Workflow';
import { useAuth } from '@/api/auth';
import {
  useDeleteRequest,
  useHealth,
  useMarkViewed,
  useRequest,
  useSubmitRequest,
} from '@/api/hooks';
import { useDownload } from '@/hooks/useDownload';
import { PAYMENT_METHOD } from '@/data/status';
import { formatDateTime, money } from '@/data/format';
import { useShell } from '@/shell/ShellContext';
import type { RequestDetail } from '@/api/types';

/**
 * Карточка заявки — одна страница для всех ролей. Что на ней можно
 * сделать, решают статус и права: руководитель согласует и отклоняет,
 * закуп оценивает позиции, бухгалтерия проводит выплату, автор двигает
 * черновик. Действий, которых у человека нет, на экране нет вовсе.
 */
export function RequestPage() {
  const { id } = useParams();
  const requestId = Number(id);
  const navigate = useNavigate();
  const { user, can } = useAuth();
  const { flash } = useShell();
  const query = useRequest(Number.isFinite(requestId) ? requestId : null);
  const { download, busy } = useDownload();
  const submitDraft = useSubmitRequest();
  const deleteDraft = useDeleteRequest();
  const markViewed = useMarkViewed();
  const [modal, setModal] = useState<'approve' | 'reject' | 'pay' | 'delete' | null>(null);

  const detail = query.data;

  // Отмечаем открытие один раз на заявку: кто открыл — решает сервер по
  // сессии, панель сообщает только сам факт. Ошибку глотаем молча —
  // человек пришёл читать заявку, а не разбираться с учётом просмотров.
  const seen = detail?.id;
  const mark = markViewed.mutate;
  useEffect(() => {
    if (seen) mark(seen, { onError: () => undefined });
  }, [seen, mark]);

  return (
    <QueryState
      isLoading={query.isLoading}
      error={query.error}
      isEmpty={!query.isLoading && !detail}
      emptyTitle="Заявка не найдена"
      emptyNote="Проверьте номер или вернитесь к списку заявок."
      emptyAction={
        <Link to="/requests" className="btn btn-secondary">
          Все заявки
        </Link>
      }
      onRetry={() => query.refetch()}
    >
      {detail && (
        <Body
          detail={detail}
          userId={user?.id ?? 0}
          userName={user?.full_name ?? ''}
          can={can}
          modal={modal}
          setModal={setModal}
          busy={busy}
          onPdf={() => download('pdf', `/api/exports/requests/${detail.id}.pdf`)}
          onSend={async () => {
            try {
              const saved = await submitDraft.mutateAsync(detail.id);
              flash(`Заявка ${saved.number} отправлена на согласование`, 'var(--dot-ok)');
            } catch (err) {
              flash(err instanceof Error ? err.message : 'Не удалось отправить', 'var(--dot-err)');
            }
          }}
          sending={submitDraft.isPending}
          onDelete={async () => {
            try {
              await deleteDraft.mutateAsync(detail.id);
              flash(`Черновик ${detail.number} удалён`, 'var(--dot-off)');
              navigate('/requests');
            } catch (err) {
              flash(err instanceof Error ? err.message : 'Не удалось удалить', 'var(--dot-err)');
              setModal(null);
            }
          }}
          deleting={deleteDraft.isPending}
        />
      )}
    </QueryState>
  );
}

type BodyProps = {
  detail: RequestDetail;
  userId: number;
  userName: string;
  can: (p: 'decide_request' | 'source_request' | 'pay_request' | 'create_request_for_others' | 'view_reports') => boolean;
  modal: 'approve' | 'reject' | 'pay' | 'delete' | null;
  setModal: (m: 'approve' | 'reject' | 'pay' | 'delete' | null) => void;
  busy: string | null;
  onPdf: () => void;
  onSend: () => void;
  sending: boolean;
  onDelete: () => void;
  deleting: boolean;
};

function Body({ detail, userId, userName, can, modal, setModal, busy, onPdf, onSend, sending, onDelete, deleting }: BodyProps) {
  const navigate = useNavigate();
  // Пояс компании: расчёты идут в нём, и браузер бухгалтера в другом
  // часовом поясе не должен показывать другое время выплаты.
  const health = useHealth();
  const own = detail.employee_id === userId;
  const decidable = detail.status === 'pending' || detail.status === 'priced';
  const canDecide = decidable && can('decide_request');
  const canSource = detail.status === 'sourcing' && can('source_request');
  const canPay = detail.status === 'approved' && can('pay_request');
  const decidedBySelf = detail.decided_by === userName;
  const ownDraft = detail.status === 'draft' && (own || can('create_request_for_others'));
  const hasActions = ownDraft || (canDecide && !own) || (canPay && !own && !decidedBySelf);

  const actions = (
    <>
      {ownDraft && (
        <>
          <button type="button" className="btn btn-danger" onClick={() => setModal('delete')}>
            Удалить
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(`/requests/${detail.id}/edit`)}>
            Изменить
          </button>
          <button type="button" className="btn btn-primary" disabled={sending} onClick={onSend}>
            {sending ? 'Отправляем…' : 'Отправить на согласование'}
          </button>
        </>
      )}
      {canDecide && !own && (
        <>
          <button type="button" className="btn btn-danger" onClick={() => setModal('reject')}>
            Отклонить
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setModal('approve')}>
            {detail.status === 'priced' ? 'Утвердить сумму' : 'Согласовать'}
          </button>
        </>
      )}
      {canPay && !own && !decidedBySelf && (
        <button type="button" className="btn btn-primary" onClick={() => setModal('pay')}>
          Провести выплату
        </button>
      )}
      <button type="button" className="btn btn-icon" aria-label="Скачать PDF" title="Скачать PDF" disabled={busy !== null} onClick={onPdf}>
        <Icon name="ti-file-type-pdf" size={18} />
      </button>
    </>
  );

  const notice = canDecide && own
    ? 'Собственную заявку согласовать нельзя — решение примет другой руководитель.'
    : canPay && own
      ? 'Выплату по собственной заявке проводит кто-то другой.'
      : canPay && decidedBySelf
        ? 'Эту заявку одобрили вы. Выплату проводит кто-то другой — так устроено разделение обязанностей.'
        : null;

  const amountCell = detail.status === 'fulfilled'
    ? <span className="num">0,00</span>
    : detail.priced
      ? <span className="num">{money(detail.amount)}</span>
      : <span className="unpriced">не оценена</span>;

  return (
    <>
      <PageHeader
        back={
          <Link to="/requests" className="small" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--slate)', fontWeight: 500 }}>
            <Icon name="ti-chevron-left" size={18} />
            Все заявки
          </Link>
        }
        above={
          <>
            <span className="num">{detail.number}</span>
            <StatusBadge status={detail.status} />
          </>
        }
        title={detail.title}
        lead={`${detail.project_name} · создана ${detail.date} · автор ${detail.employee_name}`}
        actions={<div className="page-actions-desktop">{actions}</div>}
      />

      {notice && (
        <p className="caption" style={{ margin: 0 }}>
          {notice}
        </p>
      )}

      <section className="card">
        <Workflow detail={detail} />
      </section>

      <div className="grid-2-1">
        <div className="stack">
          {canSource ? (
            <SourcingForm detail={detail} />
          ) : (
            <section className="panel">
              <div className="panel-head">
                <h2 className="h3">Позиции заявки</h2>
              </div>
              <div className="table-wrap">
                <table className="tbl fit" style={{ ['--tbl-min' as string]: '480px' }}>
                  <thead>
                    <tr>
                      <th>Позиция</th>
                      <th className="right">Кол-во</th>
                      <th className="right">Цена, TJS</th>
                      <th className="right">Сумма, TJS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.lines.map((line) => (
                      <tr key={line.id}>
                        <td>{line.title}</td>
                        <td className="right mono" style={{ fontSize: 14 }}>
                          {line.quantity}
                          {line.unit ? ` ${line.unit}` : ''}
                        </td>
                        <td className="right">
                          {line.from_stock ? <span className="unpriced">со склада</span> : line.price === null ? <span className="unpriced">—</span> : <span className="mono" style={{ fontSize: 14 }}>{money(line.price)}</span>}
                        </td>
                        <td className="right">
                          {line.from_stock ? <span className="unpriced">0,00</span> : line.total === null ? <span className="unpriced">не оценено</span> : <span className="num">{money(line.total)}</span>}
                        </td>
                      </tr>
                    ))}
                    <tr className="total-row">
                      <td colSpan={3} style={{ textAlign: 'right' }}>Итого</td>
                      <td className="right num-lg">{amountCell}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {detail.details_summary.length > 0 && (
            <section className="card" style={{ display: 'grid', gap: 12 }}>
              {/* Поля категории словами. Показываем в широкой колонке
                  рядом со сметой: для питания и командировки это и есть
                  содержание заявки, а смета — одна выведенная строка. */}
              <div className="label">Подробности расхода</div>
              <dl className="tl-details" style={{ margin: 0, background: 'transparent', borderLeft: 0, padding: 0 }}>
                {detail.details_summary.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          {(detail.sourcing_comment || detail.decision_comment) && (
            <section className="card" style={{ display: 'grid', gap: 12 }}>
              <h2 className="h3">Комментарии</h2>
              {detail.sourcing_comment && (
                <div>
                  <div className="label">Отдел закупа{detail.sourced_by ? ` · ${detail.sourced_by}` : ''}</div>
                  <p style={{ margin: '4px 0 0' }}>{detail.sourcing_comment}</p>
                </div>
              )}
              {detail.decision_comment && (
                <div>
                  <div className="label">
                    {detail.status === 'rejected' ? 'Причина отклонения' : 'Решение'}
                    {detail.decided_by ? ` · ${detail.decided_by}` : ''}
                  </div>
                  <p style={{ margin: '4px 0 0' }}>{detail.decision_comment}</p>
                </div>
              )}
            </section>
          )}

          {/* История — в широкой колонке: «было → стало» в узком
              столбце переносится по слогам и перестаёт читаться. */}
          <Timeline
            events={detail.events}
            viewers={detail.viewers}
            stays={detail.stays}
          />
        </div>

        <div className="stack">
          <Waiting request={detail} />

          <section className="card" style={{ display: 'grid', gap: 12 }}>
            <div className="label">Реквизиты</div>
            <Row k="Объект" v={detail.project_name} />
            <Row k="Создана" v={<span className="num">{detail.date}</span>} />
            <Row k="Позиций" v={<span className="num">{detail.lines.length}</span>} />
            <Row k="Сумма" v={amountCell} />
            {detail.payment && (
              <>
                <Row
                  k="Выплата"
                  v={
                    <span className="num">
                      {formatDateTime(detail.payment.paid_at, health.data?.timezone)}
                    </span>
                  }
                />
                <Row k="Способ" v={PAYMENT_METHOD[detail.payment.method]} />
                <Row k="Документ" v={<span className="num">{detail.payment.document}</span>} />
              </>
            )}
          </section>

        </div>
      </div>

      {/* На телефоне действия — липкой панелью внизу; одна кнопка PDF
          панели не заслуживает и стоит обычной строкой. */}
      <div className={hasActions ? 'sticky-actions page-actions-mobile' : 'page-actions-mobile'}>{actions}</div>

      {(modal === 'approve' || modal === 'reject') && (
        <DecisionModal request={detail} approve={modal === 'approve'} onClose={() => setModal(null)} />
      )}
      {modal === 'pay' && <PaymentModal request={detail} onClose={() => setModal(null)} />}
      {modal === 'delete' && (
        <ConfirmModal
          title="Удалить черновик"
          text={`Черновик ${detail.number} будет удалён безвозвратно. Номер в оборот не вернётся.`}
          confirmLabel={deleting ? 'Удаляем…' : 'Удалить'}
          danger
          busy={deleting}
          onConfirm={onDelete}
          onClose={() => setModal(null)}
        />
      )}
    </>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'baseline' }}>
      <span className="small" style={{ color: 'var(--slate)' }}>{k}</span>
      <span style={{ textAlign: 'right' }}>{v}</span>
    </div>
  );
}




import { useMemo, useState } from 'react';
import { Icon } from '@/components/Icon';
import { Kpi } from '@/components/Kpi';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useAuth } from '@/api/auth';
import {
  useStockBalances,
  useStockDocuments,
  useStockItems,
  useStockMoves,
  useStockOverview,
  useWarehouses,
} from '@/api/hooks';
import type { StockDocKind } from '@/api/types';
import { formatDateTime, money, plural, quantity, withUnit } from '@/data/format';
import { useShell } from '@/shell/ShellContext';
import { DocumentModal } from './stock/DocumentModal';
import type { DocKind } from './stock/DocumentModal';
import { ItemModal } from './stock/ItemModal';
import { DocumentCard } from './stock/DocumentCard';
import { WarehouseModal } from './stock/WarehouseModal';

type Tab = 'balances' | 'documents' | 'moves' | 'items' | 'warehouses';

const DOC_LABEL: Record<StockDocKind, string> = {
  RECEIPT: 'Приход',
  ISSUE: 'Выдача',
  RETURN: 'Возврат',
};

const MOVE_LABEL: Record<string, string> = {
  RECEIPT: 'Приход',
  ISSUE: 'Выдача',
  RETURN: 'Возврат',
  REVERSAL: 'Отмена',
};

/**
 * Склад: что есть, где лежит и что с этим происходило.
 *
 * Цифру остатка здесь нельзя ни ввести, ни поправить — и это не защита
 * от пользователя, а устройство модуля: остаток есть следствие прихода,
 * выдачи и возврата. Хочешь изменить остаток — оформи документ, и по
 * ленте всегда будет видно, откуда он такой взялся.
 */
export function Stock() {
  const { can } = useAuth();
  const { flash } = useShell();
  const manages = can('manage_stock');
  const seesCost = can('view_stock_cost');
  const managesReference = can('manage_reference');

  const [tab, setTab] = useState<Tab>('balances');
  const [warehouseId, setWarehouseId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [creating, setCreating] = useState<DocKind | null>(null);
  const [openItem, setOpenItem] = useState<number | 'new' | null>(null);
  const [openDocument, setOpenDocument] = useState<number | null>(null);
  const [openWarehouse, setOpenWarehouse] = useState<number | 'new' | null>(null);

  const overview = useStockOverview();
  const warehouses = useWarehouses();
  const balances = useStockBalances({ warehouseId, search }, tab === 'balances');
  const documents = useStockDocuments({ warehouseId, search }, tab === 'documents');
  const moves = useStockMoves({ warehouseId, limit: 200 }, tab === 'moves');
  const items = useStockItems({ search }, tab === 'items');

  const active = useMemo(
    () => (warehouses.data ?? []).filter((warehouse) => warehouse.active),
    [warehouses.data],
  );

  const tabs: { key: Tab; label: string }[] = [
    { key: 'balances', label: 'Остатки' },
    { key: 'documents', label: 'Документы' },
    { key: 'moves', label: 'Движения' },
    { key: 'items', label: 'Номенклатура' },
    ...(managesReference ? ([{ key: 'warehouses' as Tab, label: 'Склады' }]) : []),
  ];

  const stats = overview.data;

  return (
    <>
      <PageHeader
        title="Склад"
        lead={
          stats
            ? `${stats.items} ${plural(stats.items, 'позиция', 'позиции', 'позиций')} на ${stats.warehouses} ${plural(stats.warehouses, 'складе', 'складах', 'складах')}`
            : undefined
        }
        actions={
          manages ? (
            <>
              <button
                type="button"
                className="btn btn-primary"
                disabled={active.length === 0}
                onClick={() => setCreating('receipts')}
              >
                <Icon name="ti-plus" size={18} />
                Приход
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={active.length === 0}
                onClick={() => setCreating('issues')}
              >
                Выдача
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={active.length === 0}
                onClick={() => setCreating('returns')}
              >
                Возврат
              </button>
            </>
          ) : undefined
        }
      />

      {stats && (
        <div className="kpi-grid">
          <Kpi label="Складов" value={stats.warehouses} />
          <Kpi label="Позиций" value={stats.items} />
          <Kpi
            label="Заканчивается"
            value={stats.low_items}
            dot={stats.low_items > 0 ? 'var(--yellow)' : undefined}
            note={stats.low_items > 0 ? 'остаток ниже минимального' : 'запаса хватает'}
          />
          {seesCost ? (
            <Kpi
              label="Оценка запаса, TJS"
              value={money(stats.value)}
              note="по последней цене прихода"
            />
          ) : (
            <Kpi label="Движений сегодня" value={stats.moves_today} />
          )}
        </div>
      )}

      <div className="filter-row" style={{ marginTop: 24 }}>
        {tabs.map((entry) => (
          <button
            key={entry.key}
            type="button"
            className="filter"
            aria-pressed={tab === entry.key}
            onClick={() => setTab(entry.key)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div className="filter-row">
        <label className="sr-only" htmlFor="stock-search">
          Поиск по названию
        </label>
        <input
          id="stock-search"
          className="field"
          type="search"
          placeholder="Название позиции"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ height: 36, fontSize: 14, flex: '1 1 200px', maxWidth: 280 }}
        />
        <label className="sr-only" htmlFor="stock-warehouse">
          Склад
        </label>
        <select
          id="stock-warehouse"
          className="field"
          value={warehouseId ?? ''}
          onChange={(e) => setWarehouseId(e.target.value === '' ? null : Number(e.target.value))}
          style={{ height: 36, fontSize: 14, maxWidth: 240 }}
        >
          <option value="">Все склады</option>
          {(warehouses.data ?? []).map((warehouse) => (
            <option key={warehouse.id} value={warehouse.id}>
              {warehouse.name}
            </option>
          ))}
        </select>
      </div>

      {tab === 'balances' && (
        <QueryState
          isLoading={balances.isLoading}
          error={balances.error}
          isEmpty={(balances.data ?? []).length === 0}
          emptyTitle={search ? 'Ничего не найдено' : 'На складе пусто'}
          emptyNote={
            search
              ? 'Проверьте написание или очистите поиск.'
              : 'Остаток появляется после первого прихода — вручную его не задать.'
          }
          onRetry={() => balances.refetch()}
        >
          <div className="panel">
            <div className="table-wrap">
              <table className="tbl cards" style={{ ['--tbl-min' as string]: '620px' }}>
                <thead>
                  <tr>
                    <th style={{ width: '44%' }}>Позиция</th>
                    <th style={{ width: '28%' }}>Склад</th>
                    <th className="right" style={{ width: '28%' }}>
                      Остаток
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {(balances.data ?? []).map((row) => (
                    <tr
                      key={`${row.warehouse_id}-${row.item_id}`}
                      className="clickable"
                      tabIndex={0}
                      onClick={() => setOpenItem(row.item_id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setOpenItem(row.item_id);
                        }
                      }}
                    >
                      <td data-label="Позиция">
                        {row.item_name}
                        {row.low && (
                          <span
                            className="dot"
                            style={{ ['--dot' as string]: 'var(--yellow)', marginLeft: 8 }}
                            aria-label="Остаток ниже минимального"
                          />
                        )}
                      </td>
                      <td data-label="Склад">{row.warehouse_name}</td>
                      <td className="right mono" data-label="Остаток">
                        {withUnit(row.quantity, row.unit)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </QueryState>
      )}

      {tab === 'documents' && (
        <QueryState
          isLoading={documents.isLoading}
          error={documents.error}
          isEmpty={(documents.data ?? []).length === 0}
          emptyTitle="Документов пока нет"
          emptyNote="Приход, выдача и возврат появляются здесь сразу после проведения."
          onRetry={() => documents.refetch()}
        >
          <div className="panel">
            <div className="table-wrap">
              <table className="tbl cards" style={{ ['--tbl-min' as string]: '760px' }}>
                <thead>
                  <tr>
                    <th style={{ width: '14%' }}>Номер</th>
                    <th style={{ width: '14%' }}>Вид</th>
                    <th style={{ width: '22%' }}>Склад</th>
                    <th style={{ width: '22%' }}>Кто оформил</th>
                    <th style={{ width: '14%' }}>Когда</th>
                    <th className="right" style={{ width: '14%' }}>
                      {seesCost ? 'Сумма, TJS' : 'Позиций'}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {(documents.data ?? []).map((document) => (
                    <tr
                      key={document.id}
                      className="clickable"
                      tabIndex={0}
                      onClick={() => setOpenDocument(document.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setOpenDocument(document.id);
                        }
                      }}
                    >
                      <td className="mono" data-label="Номер">
                        {document.number}
                      </td>
                      <td data-label="Вид">
                        {DOC_LABEL[document.kind]}
                        {document.status === 'CANCELLED' && (
                          <span className="caption"> · отменён</span>
                        )}
                      </td>
                      <td data-label="Склад">{document.warehouse_name}</td>
                      <td data-label="Кто оформил">{document.created_by ?? '—'}</td>
                      <td data-label="Когда">{formatDateTime(document.created_at)}</td>
                      <td className="right mono" data-label={seesCost ? 'Сумма' : 'Позиций'}>
                        {seesCost ? money(document.total) : document.lines_count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </QueryState>
      )}

      {tab === 'moves' && (
        <QueryState
          isLoading={moves.isLoading}
          error={moves.error}
          isEmpty={(moves.data ?? []).length === 0}
          emptyTitle="Движений пока нет"
          emptyNote="Здесь видно каждое изменение остатка и того, кто его сделал."
          onRetry={() => moves.refetch()}
        >
          <div className="panel">
            <div className="table-wrap">
              <table className="tbl cards" style={{ ['--tbl-min' as string]: '760px' }}>
                <thead>
                  <tr>
                    <th style={{ width: '16%' }}>Когда</th>
                    <th style={{ width: '14%' }}>Что</th>
                    <th style={{ width: '30%' }}>Позиция</th>
                    <th style={{ width: '20%' }}>Кто</th>
                    <th className="right" style={{ width: '20%' }}>
                      Количество
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {(moves.data ?? []).map((move) => (
                    <tr key={move.id}>
                      <td data-label="Когда">{formatDateTime(move.created_at)}</td>
                      <td data-label="Что">
                        {MOVE_LABEL[move.kind] ?? move.kind}
                        <span className="caption"> · {move.document_number}</span>
                      </td>
                      <td data-label="Позиция">{move.item_name}</td>
                      <td data-label="Кто">{move.actor ?? '—'}</td>
                      <td className="right mono" data-label="Количество">
                        {Number(move.quantity) > 0 ? '+' : ''}
                        {withUnit(move.quantity, move.unit)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </QueryState>
      )}

      {tab === 'items' && (
        <>
          {manages && (
            <button
              type="button"
              className="btn btn-dashed"
              style={{ marginBottom: 16 }}
              onClick={() => setOpenItem('new')}
            >
              <Icon name="ti-plus" size={18} />
              Завести позицию
            </button>
          )}
          <QueryState
            isLoading={items.isLoading}
            error={items.error}
            isEmpty={(items.data ?? []).length === 0}
            emptyTitle={search ? 'Ничего не найдено' : 'Номенклатура пуста'}
            emptyNote="Позиции заводятся сами при первом приходе — заранее заполнять справочник не нужно."
            onRetry={() => items.refetch()}
          >
            <div className="panel">
              <div className="table-wrap">
                <table className="tbl cards" style={{ ['--tbl-min' as string]: '640px' }}>
                  <thead>
                    <tr>
                      <th style={{ width: '44%' }}>Позиция</th>
                      <th style={{ width: '14%' }}>Единица</th>
                      <th className="right" style={{ width: '21%' }}>
                        Всего
                      </th>
                      <th className="right" style={{ width: '21%' }}>
                        Минимум
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(items.data ?? []).map((item) => (
                      <tr
                        key={item.id}
                        className="clickable"
                        tabIndex={0}
                        onClick={() => setOpenItem(item.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setOpenItem(item.id);
                          }
                        }}
                      >
                        <td data-label="Позиция">
                          {item.name}
                          {!item.active && <span className="caption"> · отключена</span>}
                        </td>
                        <td data-label="Единица">{item.unit}</td>
                        <td className="right mono" data-label="Всего">
                          {quantity(item.quantity)}
                        </td>
                        <td className="right mono" data-label="Минимум">
                          {Number(item.min_quantity) > 0 ? quantity(item.min_quantity) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </QueryState>
        </>
      )}

      {tab === 'warehouses' && managesReference && (
        <>
          <button
            type="button"
            className="btn btn-dashed"
            style={{ marginBottom: 16 }}
            onClick={() => setOpenWarehouse('new')}
          >
            <Icon name="ti-plus" size={18} />
            Завести склад
          </button>
          <QueryState
            isLoading={warehouses.isLoading}
            error={warehouses.error}
            isEmpty={(warehouses.data ?? []).length === 0}
            emptyTitle="Складов нет"
            emptyNote="Заведите хотя бы один — без него нечего приходовать."
            onRetry={() => warehouses.refetch()}
          >
            <div className="panel">
              <div className="table-wrap">
                <table className="tbl cards" style={{ ['--tbl-min' as string]: '640px' }}>
                  <thead>
                    <tr>
                      <th style={{ width: '32%' }}>Склад</th>
                      <th style={{ width: '26%' }}>Объект</th>
                      <th style={{ width: '26%' }}>Ответственный</th>
                      <th className="right" style={{ width: '16%' }}>
                        Позиций
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(warehouses.data ?? []).map((warehouse) => (
                      <tr
                        key={warehouse.id}
                        className="clickable"
                        tabIndex={0}
                        onClick={() => setOpenWarehouse(warehouse.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setOpenWarehouse(warehouse.id);
                          }
                        }}
                      >
                        <td data-label="Склад">
                          {warehouse.name}
                          {!warehouse.active && <span className="caption"> · отключён</span>}
                        </td>
                        <td data-label="Объект">{warehouse.project_name ?? 'центральный'}</td>
                        <td data-label="Ответственный">{warehouse.keeper_name ?? '—'}</td>
                        <td className="right mono" data-label="Позиций">
                          {warehouse.items_count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </QueryState>
        </>
      )}

      <p className="caption" style={{ marginTop: 16, maxWidth: '70ch' }}>
        Остаток не задаётся вручную: его меняют приход, выдача и возврат. Ошибка
        исправляется отменой документа — проведённое движение остаётся в ленте,
        иначе по складу нельзя доказать ничего.
      </p>

      {creating && (
        <DocumentModal
          kind={creating}
          warehouses={active}
          onClose={() => setCreating(null)}
          onDone={(text) => flash(text, 'var(--dot-ok)')}
        />
      )}
      {openItem !== null && (
        <ItemModal
          itemId={openItem === 'new' ? null : openItem}
          onClose={() => setOpenItem(null)}
          onFlash={flash}
        />
      )}
      {openDocument !== null && (
        <DocumentCard
          documentId={openDocument}
          onClose={() => setOpenDocument(null)}
          onFlash={flash}
        />
      )}
      {openWarehouse !== null && (
        <WarehouseModal
          warehouseId={openWarehouse === 'new' ? null : openWarehouse}
          onClose={() => setOpenWarehouse(null)}
          onFlash={flash}
        />
      )}
    </>
  );
}

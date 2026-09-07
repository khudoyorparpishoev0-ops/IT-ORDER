import { Icon } from '@/components/Icon';
import { IthonaLogo, IthonaMark } from '@/components/Logo';
import type { IconName } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { STATUS_ORDER } from '@/data/status';

/**
 * Страница-эталон. Служит визуальным regression-тестом: если правка
 * компонента ломает правило брендбука, это видно здесь.
 * В продукт можно вынести в Storybook.
 */

const PALETTE = [
  { name: 'HONA Green', hex: '#22A74E', use: 'Акцент, активные состояния, 10% носителя' },
  { name: 'Deep Forest', hex: '#0E3B21', use: 'Фон навигации, шапки таблиц, обложки' },
  { name: 'Ink', hex: '#101613', use: 'Текст' },
];

const NEUTRALS = [
  { name: 'PAPER', hex: '#FFFFFF' },
  { name: 'MIST', hex: '#F5F7F5' },
  { name: 'LINE', hex: '#E3E7E3' },
  { name: 'GREY', hex: '#9AA39C' },
  { name: 'SLATE', hex: '#5A655D' },
  { name: 'GRAPHITE', hex: '#3A443D' },
];

const SPECS = [
  { k: 'Высота шапки', v: '64 px' },
  { k: 'Ширина контента', v: '1240 px' },
  { k: 'Межколонник · поля', v: '24 · 32/16 px' },
  { k: 'Шаг отступов', v: '4·8·12·16·24·32·48·64' },
  { k: 'Радиусы', v: '0 / 2 / 4 px' },
  { k: 'Строка таблицы', v: '44 px' },
  { k: 'Кнопка · моб. кнопка', v: '44 / 48 px' },
  { k: 'Обводки', v: '1 px Line · 2 px Green' },
  { k: 'Анимация', v: '150 мс ease-out' },
];

const DARK_TOKENS = [
  { name: 'Фон страницы', l: '#FFFFFF', d: '#0B120E' },
  { name: 'Поверхность', l: '#F5F7F5', d: '#151E18' },
  { name: 'Линия', l: '#E3E7E3', d: '#26332B' },
  { name: 'Текст', l: '#101613', d: '#EDF2EE' },
  { name: 'Текст втор.', l: '#5A655D', d: '#8E9A91' },
  { name: 'Акцент', l: '#22A74E', d: '#33C561' },
];

const ICONS: IconName[] = [
  'ti-layout-dashboard',
  'ti-file-text',
  'ti-circle-check',
  'ti-circle-x',
  'ti-clock-hour-4',
  'ti-wallet',
  'ti-users',
  'ti-chart-bar',
  'ti-settings',
  'ti-help-circle',
  'ti-download',
  'ti-search',
  'ti-filter',
  'ti-plus',
  'ti-server-2',
  'ti-device-cctv',
];

export function DesignSystem() {
  return (
    <>
      <PageHeader
        kicker="ЭТАЛОН"
        title="Дизайн-система"
        lead="Токены и компоненты HONA ORDER по брендбуку IT-HONA rev. 1.0"
      />

      <div style={{ display: 'grid', gap: 'var(--gap)' }}>
        <section className="card">
          <div className="label">ЛОГОТИП</div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 32,
              flexWrap: 'wrap',
              marginTop: 16,
            }}
          >
            <IthonaLogo height={40} style={{ color: 'var(--logo)' }} />
            <IthonaMark size={40} style={{ color: 'var(--logo)' }} />
            <div
              style={{
                background: 'var(--forest)',
                padding: '16px 24px',
                borderRadius: 'var(--r-card)',
                display: 'flex',
                alignItems: 'center',
                gap: 24,
              }}
            >
              <IthonaLogo height={32} style={{ color: '#FFFFFF' }} />
              <IthonaMark size={32} style={{ color: '#FFFFFF' }} />
            </div>
          </div>
          <p className="caption" style={{ margin: '16px 0 0' }}>
            Монохром: фирменный зелёный на светлом, белая выворотка на тёмном и
            на зелёном. Знак без слова — там, где имя уже названо рядом: иконка
            приложения, favicon, маркировка. Пропорции и отступ между знаком и
            словом заданы в компоненте и меняться не должны.
          </p>
        </section>

        <section className="card">
          <div className="label">ПАЛИТРА</div>
          <div className="grid-auto" style={{ marginTop: 16 }}>
            {PALETTE.map((c) => (
              <div key={c.name}>
                <div style={{ height: 64, background: c.hex, border: '1px solid var(--line)' }} />
                <div style={{ marginTop: 8, fontWeight: 600 }}>{c.name}</div>
                <div className="meta">{c.hex}</div>
                <div className="caption">{c.use}</div>
              </div>
            ))}
          </div>

          <div className="label" style={{ marginTop: 24 }}>
            НЕЙТРАЛЬНАЯ ШКАЛА
          </div>
          <div style={{ display: 'flex', marginTop: 16, flexWrap: 'wrap' }}>
            {NEUTRALS.map((n) => (
              <div key={n.name} style={{ flex: '1 1 120px' }}>
                <div style={{ height: 48, background: n.hex, border: '1px solid var(--line)' }} />
                <div className="meta" style={{ marginTop: 4 }}>
                  {n.name} {n.hex}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="label">ТИПОГРАФИКА</div>
          <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
            <div className="h1">Заголовок экрана · 30/700</div>
            <div className="lead">Лид · 26/300</div>
            <div className="h3">Заголовок блока · 19/700</div>
            <div>Основной текст · 16/400</div>
            <div className="caption">Подпись · 13/400</div>
            <div className="label">LABEL MONO · 11/600 · 0.16EM</div>
            <div className="num">1 250 000,00 · число в таблице 14/600</div>
            <div className="metric">156 000,00</div>
          </div>
        </section>

        <section className="card">
          <div className="label">КНОПКИ</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 16 }}>
            <button type="button" className="btn btn-primary">
              Primary
            </button>
            <button type="button" className="btn btn-secondary">
              Secondary
            </button>
            <button type="button" className="btn btn-danger">
              Danger
            </button>
            <button type="button" className="btn btn-ghost">
              Ghost
            </button>
            <button type="button" className="btn btn-primary" disabled>
              Disabled
            </button>
          </div>

          <div className="label" style={{ marginTop: 24 }}>
            ПОЛЯ
          </div>
          <div className="grid-auto" style={{ marginTop: 16 }}>
            <input className="field" placeholder="Обычное поле" />
            <div>
              <input className="field field-error" defaultValue="Ошибка" aria-invalid />
              <div className="field-error-text">Поле обязательно</div>
            </div>
          </div>

          <div className="label" style={{ marginTop: 24 }}>
            СТАТУС-ПЛАШКИ
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 16 }}>
            {STATUS_ORDER.map((s) => (
              <StatusBadge key={s} status={s} />
            ))}
          </div>
        </section>

        <section className="card">
          <div className="label">ФОРМА</div>
          <div className="grid-auto" style={{ marginTop: 16 }}>
            <div>
              <div className="caption">Радиусы 0 / 2 / 4</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                {[0, 2, 4].map((r) => (
                  <div
                    key={r}
                    style={{
                      width: 64,
                      height: 44,
                      background: 'var(--mist)',
                      border: '1px solid var(--line)',
                      borderRadius: r,
                      display: 'grid',
                      placeItems: 'center',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                    }}
                  >
                    {r}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="caption">Срез угла 60°</div>
              <div
                className="clip-corner"
                style={{
                  marginTop: 8,
                  height: 88,
                  background: 'var(--forest)',
                  color: '#FFFFFF',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                clip-path 60°
              </div>
            </div>
            <div>
              <div className="caption">Штриховка 60°</div>
              <div
                className="hatch"
                style={{ marginTop: 8, height: 88, border: '1px solid var(--line)' }}
              />
            </div>
          </div>
        </section>

        <section className="card">
          <div className="label">ИКОНКИ · 24 PX</div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 16 }}>
            {ICONS.map((n) => (
              <Icon key={n} name={n} size={24} />
            ))}
          </div>
        </section>

        <div className="grid-auto">
          <section className="panel">
            <div style={{ padding: 'var(--pad)' }}>
              <div className="label">РАЗМЕРЫ</div>
            </div>
            <div className="table-wrap">
              <table className="tbl">
                <tbody>
                  {SPECS.map((s) => (
                    <tr key={s.k}>
                      <td>{s.k}</td>
                      <td className="right num">{s.v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div style={{ padding: 'var(--pad)' }}>
              <div className="label">ТОКЕНЫ ТЁМНОЙ ТЕМЫ</div>
            </div>
            <div className="table-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>ТОКЕН</th>
                    <th className="right">LIGHT</th>
                    <th className="right">DARK</th>
                  </tr>
                </thead>
                <tbody>
                  {DARK_TOKENS.map((t) => (
                    <tr key={t.name}>
                      <td>{t.name}</td>
                      <td className="right num">{t.l}</td>
                      <td className="right num">{t.d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

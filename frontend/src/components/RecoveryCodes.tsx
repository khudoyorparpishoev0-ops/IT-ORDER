import { useState } from 'react';
import { Icon } from './Icon';

type Props = {
  codes: string[];
  onDone?: () => void;
};

/**
 * Коды восстановления. Показываются один раз: в базе хранятся только хэши,
 * повторно их не покажет даже администратор.
 */
export function RecoveryCodes({ codes, onDone }: Props) {
  const [copied, setCopied] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(codes.join('\n'));
      setCopied(true);
    } catch {
      // Буфер обмена может быть недоступен без https или по настройкам
      // браузера — коды и так на экране, их можно переписать.
      setCopied(false);
    }
  };

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div>
        <h2 className="h3">Коды восстановления</h2>
        <p className="caption" style={{ margin: '4px 0 0' }}>
          Сохраните их в надёжном месте. Каждый код срабатывает один раз и
          заменяет код из приложения, если телефон потерян.{' '}
          <strong>Показываются только сейчас</strong> — в системе хранятся лишь
          отпечатки, восстановить список нельзя.
        </p>
      </div>

      <ul
        className="num"
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 16,
          background: 'var(--zebra)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-field)',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 8,
          userSelect: 'all',
        }}
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-secondary" onClick={copy}>
          {copied ? 'Скопировано' : 'Копировать'}
        </button>
      </div>

      <div className="check-row" onClick={() => setConfirmed((v) => !v)}>
        <button
          type="button"
          role="checkbox"
          aria-checked={confirmed}
          aria-label="Я сохранил коды"
          className="check"
          onClick={(e) => {
            e.stopPropagation();
            setConfirmed((v) => !v);
          }}
        >
          <Icon name="ti-check" size={14} style={{ opacity: confirmed ? 1 : 0 }} />
        </button>
        <span className="small">Я сохранил коды</span>
      </div>

      <div>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!confirmed}
          onClick={() => onDone?.()}
        >
          Продолжить
        </button>
      </div>
    </div>
  );
}

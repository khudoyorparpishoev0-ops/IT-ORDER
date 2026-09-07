import { useState } from 'react';

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
    <div>
      <div className="accent-rule" />
      <h2 className="h3" style={{ marginBottom: 4 }}>
        Коды восстановления
      </h2>
      <p className="caption" style={{ margin: '0 0 16px' }}>
        Сохраните их в надёжном месте. Каждый код срабатывает один раз и
        заменяет код из приложения, если телефон потерян.{' '}
        <strong>Показываются только сейчас</strong> — в системе хранятся лишь
        отпечатки, восстановить список нельзя.
      </p>

      <ul
        className="num"
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 'var(--pad)',
          background: 'var(--mist)',
          border: '1px solid var(--line)',
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

      <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-secondary" onClick={copy}>
          {copied ? 'Скопировано' : 'Копировать'}
        </button>
      </div>

      <label
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          minHeight: 44,
          marginTop: 16,
          cursor: 'pointer',
        }}
      >
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          style={{ width: 20, height: 20 }}
        />
        Я сохранил коды
      </label>

      <button
        type="button"
        className="btn btn-primary"
        style={{ marginTop: 8 }}
        disabled={!confirmed}
        onClick={() => onDone?.()}
      >
        Продолжить
      </button>
    </div>
  );
}

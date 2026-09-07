import { useEffect, useState } from 'react';
import { useAuth } from '@/api/auth';
import type { TotpSetup as SetupData } from '@/api/types';
import { RecoveryCodes } from './RecoveryCodes';

type Props = {
  /** Показывается кнопкой «Отмена». На обязательной настройке — выход. */
  onCancel?: () => void;
  onDone?: () => void;
};

/**
 * Настройка второго фактора: QR, проверочный код, коды восстановления.
 *
 * Второй фактор включается только после успешного кода — иначе ошибка
 * при настройке заперла бы человека снаружи.
 */
export function TotpSetup({ onCancel, onDone }: Props) {
  const { startTotpSetup, confirmTotpSetup } = useAuth();
  const [setup, setSetup] = useState<SetupData | null>(null);
  const [code, setCode] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  useEffect(() => {
    let cancelled = false;
    startTotpSetup()
      .then((data) => {
        if (!cancelled) setSetup(data);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'Не удалось начать настройку'),
      );
    return () => {
      cancelled = true;
    };
    // Секрет запрашиваем один раз на монтирование: повторный запрос выдал бы
    // новый секрет и обесценил уже отсканированный QR.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const confirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      setCodes(await confirmTotpSetup(code.trim()));
    } catch (err) {
      setCode('');
      setError(err instanceof Error ? err.message : 'Код не подошёл');
    } finally {
      setBusy(false);
    }
  };

  if (codes) {
    return <RecoveryCodes codes={codes} onDone={onDone} />;
  }

  if (error && !setup) {
    return (
      <div className="field-error-text" role="alert">
        {error}
      </div>
    );
  }

  if (!setup) {
    return <div className="label">ГОТОВИМ КЛЮЧ</div>;
  }

  return (
    <form onSubmit={confirm} noValidate>
      <ol style={{ margin: 0, paddingLeft: 20, display: 'grid', gap: 16 }}>
        <li>
          Установите приложение-аутентификатор: Google Authenticator, Aegis, 1Password
          или любое другое.
        </li>
        <li>
          Отсканируйте код:
          <div
            style={{
              marginTop: 12,
              width: 180,
              height: 180,
              background: '#FFFFFF',
              border: '1px solid var(--line)',
              padding: 8,
            }}
            // Разметка приходит от нашего же сервера: это QR, сгенерированный
            // из ссылки otpauth, а не пользовательский ввод.
            dangerouslySetInnerHTML={{ __html: setup.qr_svg }}
          />
          <button
            type="button"
            className="btn btn-ghost"
            style={{ paddingLeft: 0 }}
            onClick={() => setShowSecret((v) => !v)}
          >
            {showSecret ? 'Скрыть ключ' : 'Не сканируется — ввести ключ вручную'}
          </button>
          {showSecret && (
            <div
              className="num"
              style={{
                userSelect: 'all',
                padding: '8px 12px',
                background: 'var(--mist)',
                border: '1px solid var(--line)',
                wordBreak: 'break-all',
              }}
            >
              {setup.secret}
            </div>
          )}
        </li>
        <li>
          <label style={{ display: 'block' }}>
            <div className="caption" style={{ marginBottom: 4 }}>
              Введите код из приложения
            </div>
            <input
              className={`field${error ? ' field-error' : ''}`}
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              aria-invalid={Boolean(error)}
              placeholder="000000"
              style={{
                fontFamily: 'var(--font-mono)',
                letterSpacing: '0.2em',
                maxWidth: 200,
              }}
            />
          </label>
        </li>
      </ol>

      {error && (
        <div className="field-error-text" role="alert" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 24, flexWrap: 'wrap' }}>
        <button type="submit" className="btn btn-primary" disabled={busy || !code}>
          {busy ? 'Проверяем…' : 'Включить'}
        </button>
        {onCancel && (
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            Отмена
          </button>
        )}
      </div>
    </form>
  );
}
